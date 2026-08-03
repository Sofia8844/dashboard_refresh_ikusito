from __future__ import annotations

from json import JSONDecodeError
from typing import Any

import httpx

from app.config import Settings


class CanvasClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.canvas_api_base_url.rstrip("/")
        self.timeout = settings.request_timeout_seconds
        self.headers = {"X-Timezone": settings.canvas_timezone}
    async def get_latest_snapshot(self, project_id: str, page_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/pages/project/{project_id}/page/{page_id}/latest"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return _read_json(response, "Canvas latest snapshot")

    async def get_events(self, project_id: str, page_id: str) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/events/project/{project_id}/page/{page_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = _read_json(response, "Canvas events")
        if isinstance(payload, list):
            return payload
        events = payload.get("events") if isinstance(payload, dict) else None
        return events if isinstance(events, list) else []

    async def create_snapshot(
        self,
        *,
        project_id: str,
        page_id: str,
        base_snapshot_id: str,
        document: dict[str, Any],
    ) -> str:
        _ = base_snapshot_id
        url = f"{self.base_url}/api/pages/project/{project_id}"
        body = {
            **document,
            "pageId": page_id,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=body,headers=self.headers)
            print("CANVAS CREATE SNAPSHOT RESPONSE:", response.text[:5000])
            response.raise_for_status()
            payload = _read_json(response, "Canvas create snapshot")
        snapshot_id = _extract_snapshot_id(payload)
        if not snapshot_id:
            raise ValueError("Canvas snapshot creation response did not include a snapshot id")
        return snapshot_id


def _extract_snapshot_id(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in ("_id", "id", "snapshotId", "snapshot_id"):
        value = payload.get(key)
        if value:
            return str(value)
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        return _extract_snapshot_id(snapshot)
    return None


def _read_json(response: httpx.Response, operation: str) -> Any:
    """Lee JSON desde Canvas y agrega contexto cuando la respuesta no es JSON."""

    try:
        return response.json()
    except JSONDecodeError as exc:
        content_type = response.headers.get("content-type", "unknown")
        preview = response.text[:200].replace("\n", " ").strip() or "<empty>"
        raise ValueError(
            f"{operation} returned a non-JSON response "
            f"(status={response.status_code}, content_type={content_type}, body={preview})"
        ) from exc
