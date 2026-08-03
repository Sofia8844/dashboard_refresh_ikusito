from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.api.schemas import RefreshJobCreateRequest
from app.services.refresh_jobs import RefreshJobService


@dataclass
class Job:
    id: uuid.UUID
    project_id: str
    page_id: str
    base_snapshot_id: str
    idempotency_key: str
    trigger_type: str
    status: str = "queued"
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_snapshot_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class FakeRepo:
    def __init__(self, already_exists: bool = False, should_publish: bool | None = None):
        self.already_exists = already_exists
        self.should_publish = not already_exists if should_publish is None else should_publish
        self.failed = False
        self.job = Job(
            id=uuid.uuid4(),
            project_id="project",
            page_id="page",
            base_snapshot_id="snapshot",
            idempotency_key="refresh:project:page:snapshot",
            trigger_type="dashboard_opened",
        )

    async def create_or_get_existing(self, **kwargs):
        self.kwargs = kwargs
        self.job.trigger_type = kwargs["trigger_type"]
        return self.job, self.already_exists, self.should_publish

    async def mark_failed(self, *args, **kwargs):
        self.failed = True


class FakePublisher:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.published = []

    async def publish_refresh_job(self, payload):
        if self.fail:
            raise RuntimeError("rabbit down")
        self.published.append(payload)


@pytest.mark.asyncio
async def test_create_job_publishes_only_new_jobs() -> None:
    repo = FakeRepo(already_exists=False)
    publisher = FakePublisher()
    service = RefreshJobService(repo, publisher)

    job, already_exists = await service.create_job(
        RefreshJobCreateRequest(
            projectId="project",
            pageId="page",
            observedSnapshotId="snapshot",
            trigger="dashboard_opened",
        )
    )

    assert already_exists is False
    assert publisher.published == [
        {
            "jobId": str(job.id),
            "projectId": "project",
            "pageId": "page",
            "baseSnapshotId": "snapshot",
            "trigger": "dashboard_opened",
        }
    ]


@pytest.mark.asyncio
async def test_create_job_does_not_publish_existing_jobs() -> None:
    repo = FakeRepo(already_exists=True)
    publisher = FakePublisher()
    service = RefreshJobService(repo, publisher)

    await service.create_job(
        RefreshJobCreateRequest(
            projectId="project",
            pageId="page",
            observedSnapshotId="snapshot",
            trigger="dashboard_opened",
        )
    )

    assert publisher.published == []


@pytest.mark.asyncio
async def test_create_job_publishes_requeued_failed_jobs() -> None:
    repo = FakeRepo(already_exists=True, should_publish=True)
    repo.job.status = "queued"
    publisher = FakePublisher()
    service = RefreshJobService(repo, publisher)

    job, already_exists = await service.create_job(
        RefreshJobCreateRequest(
            projectId="project",
            pageId="page",
            observedSnapshotId="snapshot",
            trigger="manual-retry",
        )
    )

    assert already_exists is True
    assert publisher.published == [
        {
            "jobId": str(job.id),
            "projectId": "project",
            "pageId": "page",
            "baseSnapshotId": "snapshot",
            "trigger": "manual-retry",
        }
    ]


@pytest.mark.asyncio
async def test_create_job_does_not_publish_existing_skipped_jobs() -> None:
    repo = FakeRepo(already_exists=True, should_publish=False)
    repo.job.status = "skipped"
    publisher = FakePublisher()
    service = RefreshJobService(repo, publisher)

    job, already_exists = await service.create_job(
        RefreshJobCreateRequest(
            projectId="project",
            pageId="page",
            observedSnapshotId="snapshot",
            trigger="dashboard_opened",
        )
    )

    assert already_exists is True
    assert job.status == "skipped"
    assert publisher.published == []


@pytest.mark.asyncio
async def test_create_job_marks_failed_when_publish_fails() -> None:
    repo = FakeRepo(already_exists=False)
    service = RefreshJobService(repo, FakePublisher(fail=True))

    with pytest.raises(RuntimeError):
        await service.create_job(
            RefreshJobCreateRequest(
                projectId="project",
                pageId="page",
                observedSnapshotId="snapshot",
                trigger="dashboard_opened",
            )
        )

    assert repo.failed is True
