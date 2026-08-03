from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RefreshJobCreateRequest(BaseModel):
    project_id: str = Field(..., alias="projectId", min_length=1)
    page_id: str = Field(..., alias="pageId", min_length=1)
    observed_snapshot_id: str = Field(..., alias="observedSnapshotId", min_length=1)
    trigger: str = Field("dashboard_opened", min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class RefreshJobCreateResponse(BaseModel):
    job_id: UUID = Field(..., alias="jobId")
    status: str
    already_exists: bool = Field(..., alias="alreadyExists")

    model_config = ConfigDict(populate_by_name=True)


class RefreshJobError(BaseModel):
    code: str
    message: str | None = None


class RefreshJobStatusResponse(BaseModel):
    job_id: UUID = Field(..., alias="jobId")
    project_id: str = Field(..., alias="projectId")
    page_id: str = Field(..., alias="pageId")
    status: str
    base_snapshot_id: str = Field(..., alias="baseSnapshotId")
    result_snapshot_id: str | None = Field(None, alias="resultSnapshotId")
    requested_at: datetime = Field(..., alias="requestedAt")
    started_at: datetime | None = Field(None, alias="startedAt")
    completed_at: datetime | None = Field(None, alias="completedAt")
    error: RefreshJobError | None = None

    model_config = ConfigDict(populate_by_name=True)

