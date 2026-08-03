from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from app.clients.canvas import CanvasClient
from app.clients.mcp import McpQueryClient
from app.config import Settings
from app.domain.event_reducer import reduce_events
from app.domain.jobs import TERMINAL_STATUSES, RefreshJobStatus
from app.domain.widgets import Path, apply_widget_rows, collect_sql_widgets
from app.repositories.jobs import DashboardRefreshJobRepository


class DashboardRefreshWorkerService:
    """Orquesta el procesamiento completo de un job consumido desde RabbitMQ."""

    def __init__(
        self,
        *,
        settings: Settings,
        repository: DashboardRefreshJobRepository,
        canvas_client: CanvasClient,
        mcp_client: McpQueryClient,
        worker_id: str | None = None,
    ):
        """Recibe dependencias externas y define un identificador unico del worker."""

        self.settings = settings
        self.repository = repository
        self.canvas_client = canvas_client
        self.mcp_client = mcp_client
        self.worker_id = worker_id or f"refresh-worker-{uuid.uuid4()}"

    async def process_message(self, payload: dict[str, Any]) -> None:
        """Procesa un mensaje RabbitMQ, reclama el job y evita reprocesar estados finales."""

        job_id = uuid.UUID(str(payload["jobId"]))
        existing = await self.repository.get(job_id)
        if existing is None:
            return
        if existing.status in TERMINAL_STATUSES:
            return

        claimed = await self.repository.claim_queued_job(job_id, self.worker_id)
        if claimed is None:
            current = await self.repository.get(job_id)
            if current and current.status in (*TERMINAL_STATUSES, RefreshJobStatus.PROCESSING.value):
                return
            raise RuntimeError(f"Job {job_id} could not be claimed")

        try:
            await self._process_claimed_job(claimed)
        except Exception as exc:  # noqa: BLE001
            await self.repository.mark_failed(
                job_id,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            return

    async def _process_claimed_job(self, job: Any) -> None:
        """Refresca una pagina ya reclamada: snapshot, eventos, MCP y snapshot final."""

        latest_snapshot = await self.canvas_client.get_latest_snapshot(job.project_id, job.page_id)
        if not _snapshot_is_expired(latest_snapshot):
            await self.repository.mark_skipped(
                job.id,
                error_code="SNAPSHOT_ALREADY_REFRESHED",
                error_message="The latest snapshot nextUpdate is still in the future.",
            )
            return

        events = await self.canvas_client.get_events(job.project_id, job.page_id)
        resolved = reduce_events(latest_snapshot, events)["resolvedDocument"]
        sql_widgets = collect_sql_widgets(resolved)
        if not sql_widgets:
            await self.repository.mark_skipped(
                job.id,
                error_code="NO_SQL_WIDGETS",
                error_message="The page does not contain widgets with diagramData.sql_statement.",
            )
            return

        widget_results = await self._execute_widget_queries(sql_widgets)
        refreshed_document = apply_widget_rows(
            resolved,
            widget_results,
        )
        snapshot_id = await self.canvas_client.create_snapshot(
            project_id=job.project_id,
            page_id=job.page_id,
            base_snapshot_id=job.base_snapshot_id,
            document=refreshed_document,
        )
        await self.repository.mark_completed(
            job.id,
            result_snapshot_id=snapshot_id,
            updated_widgets=len(widget_results),
        )

    async def _execute_widget_queries(self, sql_widgets: list[tuple[Path, str]]) -> dict[Path, list[Any]]:
        """Ejecuta consultas MCP con concurrencia limitada y devuelve rows por widget."""

        semaphore = asyncio.Semaphore(self.settings.refresh_query_concurrency)

        async def run_one(path: Path, query: str) -> tuple[Path, list[Any]]:
            """Ejecuta una consulta individual respetando el semaforo de concurrencia."""

            async with semaphore:
                rows = await self.mcp_client.execute_sql(query)
                return path, rows

        results = await asyncio.gather(*(run_one(path, query) for path, query in sql_widgets))
        return dict(results)


def _snapshot_is_expired(snapshot: dict[str, Any]) -> bool:
    """Indica si el `nextUpdate` del snapshot ya vencio o no existe."""

    value = _find_key(snapshot, "nextUpdate")
    if value is None:
        return True
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    elif isinstance(value, datetime):
        parsed = value
    else:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return datetime.now(UTC) >= parsed


def _find_key(node: Any, key: str) -> Any:
    """Busca recursivamente una clave dentro de diccionarios y listas anidadas."""

    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None
