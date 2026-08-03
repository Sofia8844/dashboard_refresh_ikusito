from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.services.worker import DashboardRefreshWorkerService


@dataclass
class Job:
    id: uuid.UUID
    project_id: str = "project"
    page_id: str = "page"
    base_snapshot_id: str = "snapshot"
    status: str = "queued"


class FakeRepo:
    def __init__(self, job: Job):
        self.job = job
        self.completed = None
        self.skipped = None
        self.failed = None
        self.claims = 0

    async def get(self, job_id):
        return self.job

    async def claim_queued_job(self, job_id, worker_id):
        self.claims += 1
        if self.job.status == "queued":
            self.job.status = "processing"
            return self.job
        return None

    async def mark_skipped(self, job_id, **kwargs):
        self.skipped = kwargs
        self.job.status = "skipped"

    async def mark_completed(self, job_id, **kwargs):
        self.completed = kwargs
        self.job.status = "completed"

    async def mark_failed(self, job_id, **kwargs):
        self.failed = kwargs
        self.job.status = "failed"


class FakeCanvas:
    def __init__(self, next_update, events=None):
        self.snapshot = {
            "id": "latest",
            "document": {
                "nextUpdate": next_update,
                "widgets": [
                    {"id": "w1", "diagramData": {"sql_statement": "select 1", "rows": []}}
                ],
            },
        }
        self.events = events or []
        self.created = None

    async def get_latest_snapshot(self, project_id, page_id):
        return self.snapshot

    async def get_events(self, project_id, page_id):
        return self.events

    async def create_snapshot(self, **kwargs):
        self.created = kwargs
        return "new-snapshot"


class FakeMcp:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.queries = []

    async def execute_sql(self, query):
        if self.fail:
            raise RuntimeError("mcp down")
        self.queries.append(query)
        return [[1]]


def settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        RABBITMQ_URL="amqp://guest:guest@localhost/",
        REFRESH_QUERY_CONCURRENCY=3,
    )


@pytest.mark.asyncio
async def test_worker_skips_when_snapshot_is_current() -> None:
    job = Job(id=uuid.uuid4())
    repo = FakeRepo(job)
    canvas = FakeCanvas((datetime.now(UTC) + timedelta(minutes=5)).isoformat())
    mcp = FakeMcp()
    service = DashboardRefreshWorkerService(
        settings=settings(),
        repository=repo,
        canvas_client=canvas,
        mcp_client=mcp,
    )

    await service.process_message({"jobId": str(job.id)})

    assert repo.skipped["error_code"] == "SNAPSHOT_ALREADY_REFRESHED"
    assert mcp.queries == []
    assert canvas.created is None


@pytest.mark.asyncio
async def test_worker_refreshes_expired_snapshot_all_or_nothing() -> None:
    job = Job(id=uuid.uuid4())
    repo = FakeRepo(job)
    canvas = FakeCanvas((datetime.now(UTC) - timedelta(minutes=5)).isoformat())
    mcp = FakeMcp()
    service = DashboardRefreshWorkerService(
        settings=settings(),
        repository=repo,
        canvas_client=canvas,
        mcp_client=mcp,
    )

    await service.process_message({"jobId": str(job.id)})

    assert mcp.queries == ["select 1"]
    assert canvas.created["document"]["widgets"][0]["diagramData"]["rows"] == [[1]]
    assert repo.completed == {"result_snapshot_id": "new-snapshot", "updated_widgets": 1}


@pytest.mark.asyncio
async def test_worker_acks_completed_redelivery_without_processing() -> None:
    job = Job(id=uuid.uuid4(), status="completed")
    repo = FakeRepo(job)
    canvas = FakeCanvas((datetime.now(UTC) - timedelta(minutes=5)).isoformat())
    service = DashboardRefreshWorkerService(
        settings=settings(),
        repository=repo,
        canvas_client=canvas,
        mcp_client=FakeMcp(),
    )

    await service.process_message({"jobId": str(job.id)})

    assert repo.claims == 0
    assert canvas.created is None


@pytest.mark.asyncio
async def test_worker_marks_failed_without_raising_to_rabbitmq() -> None:
    job = Job(id=uuid.uuid4())
    repo = FakeRepo(job)
    canvas = FakeCanvas((datetime.now(UTC) - timedelta(minutes=5)).isoformat())
    service = DashboardRefreshWorkerService(
        settings=settings(),
        repository=repo,
        canvas_client=canvas,
        mcp_client=FakeMcp(fail=True),
    )

    await service.process_message({"jobId": str(job.id)})

    assert repo.failed == {"error_code": "RuntimeError", "error_message": "mcp down"}
    assert job.status == "failed"
    assert canvas.created is None


@pytest.mark.asyncio
async def test_worker_acks_failed_redelivery_without_processing() -> None:
    job = Job(id=uuid.uuid4(), status="failed")
    repo = FakeRepo(job)
    canvas = FakeCanvas((datetime.now(UTC) - timedelta(minutes=5)).isoformat())
    service = DashboardRefreshWorkerService(
        settings=settings(),
        repository=repo,
        canvas_client=canvas,
        mcp_client=FakeMcp(),
    )

    await service.process_message({"jobId": str(job.id)})

    assert repo.claims == 0
    assert canvas.created is None
