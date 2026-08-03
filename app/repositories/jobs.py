from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DashboardRefreshJob
from app.domain.jobs import ACTIVE_STATUSES, RefreshJobStatus


class DashboardRefreshJobRepository:
    """Centraliza las operaciones de PostgreSQL sobre dashboard_refresh_jobs."""

    def __init__(self, session: AsyncSession):
        """Guarda la sesion async de SQLAlchemy usada por todos los metodos."""

        self.session = session

    async def create_or_get_existing(
        self,
        *,
        project_id: str,
        page_id: str,
        base_snapshot_id: str,
        idempotency_key: str,
        trigger_type: str,
    ) -> tuple[DashboardRefreshJob, bool, bool]:
        """Crea un job, devuelve uno existente o reencola uno fallido."""

        job = DashboardRefreshJob(
            project_id=project_id,
            page_id=page_id,
            base_snapshot_id=base_snapshot_id,
            idempotency_key=idempotency_key,
            trigger_type=trigger_type,
            status=RefreshJobStatus.QUEUED.value,
        )
        self.session.add(job)
        try:
            await self.session.commit()
            await self.session.refresh(job)
            return job, False, True
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.status == RefreshJobStatus.FAILED.value:
                    requeued = await self.requeue_terminal_job(existing.id, trigger_type=trigger_type)
                    if requeued is not None:
                        return requeued, True, True
                return existing, True, False
            active = await self.get_active_for_page(project_id, page_id)
            if active is not None:
                return active, True, False
            raise

    async def get(self, job_id: uuid.UUID) -> DashboardRefreshJob | None:
        """Obtiene un job por su UUID."""

        return await self.session.get(DashboardRefreshJob, job_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> DashboardRefreshJob | None:
        """Busca el job asociado a una clave de idempotencia exacta."""

        result = await self.session.execute(
            select(DashboardRefreshJob).where(DashboardRefreshJob.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def get_active_for_page(
        self, project_id: str, page_id: str
    ) -> DashboardRefreshJob | None:
        """Devuelve el job queued/processing mas antiguo para una pagina."""

        result = await self.session.execute(
            select(DashboardRefreshJob)
            .where(
                DashboardRefreshJob.project_id == project_id,
                DashboardRefreshJob.page_id == page_id,
                DashboardRefreshJob.status.in_(ACTIVE_STATUSES),
            )
            .order_by(DashboardRefreshJob.requested_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def claim_queued_job(
        self, job_id: uuid.UUID, worker_id: str
    ) -> DashboardRefreshJob | None:
        """Toma atomicamente un job queued y lo mueve a processing para un worker."""

        result = await self.session.execute(
            update(DashboardRefreshJob)
            .where(
                DashboardRefreshJob.id == job_id,
                DashboardRefreshJob.status == RefreshJobStatus.QUEUED.value,
            )
            .values(
                status=RefreshJobStatus.PROCESSING.value,
                started_at=datetime.now(UTC),
                worker_id=worker_id,
                attempt_count=DashboardRefreshJob.attempt_count + 1,
                updated_at=datetime.now(UTC),
            )
            .returning(DashboardRefreshJob)
        )
        await self.session.commit()
        return result.scalar_one_or_none()

    async def requeue_terminal_job(
        self, job_id: uuid.UUID, *, trigger_type: str
    ) -> DashboardRefreshJob | None:
        """Reintenta manualmente un job failed limpiando su resultado previo."""

        now = datetime.now(UTC)
        result = await self.session.execute(
            update(DashboardRefreshJob)
            .where(
                DashboardRefreshJob.id == job_id,
                DashboardRefreshJob.status == RefreshJobStatus.FAILED.value,
            )
            .values(
                status=RefreshJobStatus.QUEUED.value,
                trigger_type=trigger_type,
                result_snapshot_id=None,
                updated_widgets=0,
                failed_widgets=0,
                worker_id=None,
                error_code=None,
                error_message=None,
                requested_at=now,
                started_at=None,
                completed_at=None,
                heartbeat_at=None,
                updated_at=now,
            )
            .returning(DashboardRefreshJob)
        )
        await self.session.commit()
        return result.scalar_one_or_none()

    async def mark_skipped(
        self, job_id: uuid.UUID, *, error_code: str, error_message: str | None = None
    ) -> None:
        """Marca un job como omitido cuando no necesita refresco."""

        await self._finish(
            job_id,
            status=RefreshJobStatus.SKIPPED.value,
            error_code=error_code,
            error_message=error_message,
        )

    async def mark_failed(
        self,
        job_id: uuid.UUID,
        *,
        error_code: str,
        error_message: str | None = None,
        failed_widgets: int = 0,
    ) -> None:
        """Marca un job como fallido y conserva el snapshot anterior."""

        await self._finish(
            job_id,
            status=RefreshJobStatus.FAILED.value,
            error_code=error_code,
            error_message=error_message,
            failed_widgets=failed_widgets,
        )

    async def mark_completed(
        self, job_id: uuid.UUID, *, result_snapshot_id: str, updated_widgets: int
    ) -> None:
        """Marca un job como completado y guarda el snapshot resultante."""

        await self._finish(
            job_id,
            status=RefreshJobStatus.COMPLETED.value,
            result_snapshot_id=result_snapshot_id,
            updated_widgets=updated_widgets,
        )

    async def _finish(
        self,
        job_id: uuid.UUID,
        *,
        status: str,
        result_snapshot_id: str | None = None,
        updated_widgets: int | None = None,
        failed_widgets: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Actualiza campos comunes de finalizacion para estados terminales."""

        values: dict[str, object] = {
            "status": status,
            "completed_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "error_code": error_code,
            "error_message": error_message,
        }
        if result_snapshot_id is not None:
            values["result_snapshot_id"] = result_snapshot_id
        if updated_widgets is not None:
            values["updated_widgets"] = updated_widgets
        if failed_widgets is not None:
            values["failed_widgets"] = failed_widgets
        await self.session.execute(
            update(DashboardRefreshJob).where(DashboardRefreshJob.id == job_id).values(**values)
        )
        await self.session.commit()
