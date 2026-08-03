from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_refresh_job_service
from app.api.schemas import (
    RefreshJobCreateRequest,
    RefreshJobCreateResponse,
    RefreshJobError,
    RefreshJobStatusResponse,
)
from app.database.session import check_database_ready
from app.services.refresh_jobs import RefreshJobService

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    await check_database_ready()
    return {"status": "ready"}


@router.post(
    "/refresh-jobs",
    response_model=RefreshJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_refresh_job(
    request: RefreshJobCreateRequest,
    service: Annotated[RefreshJobService, Depends(get_refresh_job_service)],
) -> RefreshJobCreateResponse:
    try:
        job, already_exists = await service.create_job(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "REFRESH_JOB_NOT_QUEUED", "message": str(exc)},
        ) from exc
    return RefreshJobCreateResponse(
        jobId=job.id,
        status=job.status,
        alreadyExists=already_exists,
    )


@router.get("/refresh-jobs/{job_id}", response_model=RefreshJobStatusResponse)
async def get_refresh_job(
    job_id: UUID,
    service: Annotated[RefreshJobService, Depends(get_refresh_job_service)],
) -> RefreshJobStatusResponse:
    job = await service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    error = None
    if job.error_code:
        error = RefreshJobError(code=job.error_code, message=job.error_message)
    return RefreshJobStatusResponse(
        jobId=job.id,
        projectId=job.project_id,
        pageId=job.page_id,
        status=job.status,
        baseSnapshotId=job.base_snapshot_id,
        resultSnapshotId=job.result_snapshot_id,
        requestedAt=job.requested_at,
        startedAt=job.started_at,
        completedAt=job.completed_at,
        error=error,
    )
