from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from app.config import Settings


class McpQueryClient:
    def __init__(self, settings: Settings):
        self.server_url = settings.mcp_server_url
        self.logged_user_role = settings.mcp_default_logged_user_role

    async def execute_sql(self, query: str) -> list[Any]:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(self.server_url) as streams, ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(
                "clean_and_execute_statement",
                arguments={
                    "query": query,
                    "logged_user_rol": self.logged_user_role,
                },
            )
        return _extract_rows(result)


def _extract_rows(result: Any) -> list[Any]:
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if isinstance(structured, dict) and isinstance(structured.get("rows"), list):
        return structured["rows"]

    content = getattr(result, "content", None)
    if isinstance(content, list):
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parsed = _load_tool_json(text)
                if isinstance(parsed, dict) and isinstance(parsed.get("rows"), list):
                    return parsed["rows"]

    if isinstance(result, dict) and isinstance(result.get("rows"), list):
        return result["rows"]
    raise ValueError("MCP response did not include rows")


def _load_tool_json(text: str) -> Any:
    """Convierte texto MCP a JSON y reporta contexto si llega vacio o mal formado."""

    try:
        return json.loads(text)
    except JSONDecodeError as exc:
        preview = text[:200].replace("\n", " ").strip() or "<empty>"
        raise ValueError(f"MCP tool returned non-JSON content: {preview}") from exc
