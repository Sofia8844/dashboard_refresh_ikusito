from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class RefreshJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


ACTIVE_STATUSES = (RefreshJobStatus.QUEUED.value, RefreshJobStatus.PROCESSING.value)
TERMINAL_STATUSES = (
    RefreshJobStatus.COMPLETED.value,
    RefreshJobStatus.FAILED.value,
    RefreshJobStatus.SKIPPED.value,
)


def build_idempotency_key(project_id: str, page_id: str, observed_snapshot_id: str) -> str:
    return f"refresh:{project_id}:{page_id}:{observed_snapshot_id}"


@dataclass(slots=True)
class RefreshJobMessage:
    job_id: UUID
    project_id: str
    page_id: str
    base_snapshot_id: str
    trigger: str

    def to_payload(self) -> dict[str, str]:
        return {
            "jobId": str(self.job_id),
            "projectId": self.project_id,
            "pageId": self.page_id,
            "baseSnapshotId": self.base_snapshot_id,
            "trigger": self.trigger,
        }


@dataclass(slots=True)
class RefreshJobView:
    job_id: UUID
    project_id: str
    page_id: str
    status: str
    base_snapshot_id: str
    result_snapshot_id: str | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None

