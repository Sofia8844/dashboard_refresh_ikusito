from __future__ import annotations

from uuid import UUID

from app.api.schemas import RefreshJobCreateRequest
from app.domain.jobs import RefreshJobMessage, build_idempotency_key
from app.messaging.rabbitmq import RefreshJobPublisher
from app.repositories.jobs import DashboardRefreshJobRepository


class RefreshJobService:
    def __init__(self, repository: DashboardRefreshJobRepository, publisher: RefreshJobPublisher):
        self.repository = repository
        self.publisher = publisher

    async def create_job(self, request: RefreshJobCreateRequest):
        idempotency_key = build_idempotency_key(
            request.project_id, request.page_id, request.observed_snapshot_id
        )
        job, already_exists, should_publish = await self.repository.create_or_get_existing(
            project_id=request.project_id,
            page_id=request.page_id,
            base_snapshot_id=request.observed_snapshot_id,
            idempotency_key=idempotency_key,
            trigger_type=request.trigger,
        )
        if should_publish:
            try:
                await self.publisher.publish_refresh_job(
                    RefreshJobMessage(
                        job_id=job.id,
                        project_id=job.project_id,
                        page_id=job.page_id,
                        base_snapshot_id=job.base_snapshot_id,
                        trigger=job.trigger_type,
                    ).to_payload()
                )
            except Exception as exc:
                await self.repository.mark_failed(
                    job.id,
                    error_code="QUEUE_PUBLISH_FAILED",
                    error_message=str(exc),
                )
                raise
        return job, already_exists

    async def get_job(self, job_id: UUID):
        return await self.repository.get(job_id)
