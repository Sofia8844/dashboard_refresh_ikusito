from __future__ import annotations

from dataclasses import dataclass
from typing import Self

import httpx
import pytest

from app.clients.canvas import CanvasClient, _extract_snapshot_id, _read_json
from app.clients.mcp import _extract_rows
from app.config import Settings


def test_canvas_read_json_reports_non_json_context() -> None:
    response = httpx.Response(
        502,
        headers={"content-type": "text/html"},
        text="<html>bad gateway</html>",
    )

    with pytest.raises(ValueError, match="Canvas latest snapshot returned a non-JSON response"):
        _read_json(response, "Canvas latest snapshot")


def test_canvas_extract_snapshot_id_supports_mongo_id() -> None:
    assert _extract_snapshot_id({"_id": "6a6c4aa8ff9fa16fca225044"}) == "6a6c4aa8ff9fa16fca225044"


def test_mcp_extract_rows_reports_non_json_content() -> None:
    @dataclass
    class ContentItem:
        text: str

    @dataclass
    class ToolResult:
        content: list[ContentItem]

    with pytest.raises(ValueError, match="MCP tool returned non-JSON content"):
        _extract_rows(ToolResult(content=[ContentItem(text="")]))


@pytest.mark.asyncio
async def test_canvas_create_snapshot_posts_flat_document(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(self, url: str, json: dict[str, object]) -> httpx.Response:
            captured["url"] = url
            captured["json"] = json
            return httpx.Response(200, json={"id": "snapshot-created"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = CanvasClient(
        Settings(
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            RABBITMQ_URL="amqp://guest:guest@localhost/",
            CANVAS_API_BASE_URL="http://canvas",
        )
    )

    snapshot_id = await client.create_snapshot(
        project_id="project",
        page_id="page",
        base_snapshot_id="base-snapshot",
        document={
            "width": 1200,
            "height": 800,
            "widgets": [],
            "figures": [],
            "images": [],
        },
    )

    assert snapshot_id == "snapshot-created"
    assert captured["url"] == "http://canvas/api/pages/project/project"
    assert captured["json"] == {
        "pageId": "page",
        "width": 1200,
        "height": 800,
        "widgets": [],
        "figures": [],
        "images": [],
    }
