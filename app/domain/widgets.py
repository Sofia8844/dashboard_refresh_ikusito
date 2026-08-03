from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from typing import Any

Path = tuple[str | int, ...]
EDITOR_UPDATE_TIME_ZONE = timezone(timedelta(hours=-5), "America/Bogota")
EDITOR_DAILY_UPDATE_HOUR = 8


def collect_sql_widgets(document: dict[str, Any]) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    _walk_for_sql(document, (), found)
    return found


def apply_widget_rows(
    document: dict[str, Any],
    widget_results: dict[Path, list[Any]],
) -> dict[str, Any]:
    updated = deepcopy(document)
    for path, rows in widget_results.items():
        widget = _get_by_path(updated, path)
        if isinstance(widget, dict):
            diagram_data = widget.setdefault("diagramData", {})
            if isinstance(diagram_data, dict):
                diagram_data["rows"] = rows
    _touch_snapshot_dates(updated)
    return updated


def _walk_for_sql(node: Any, path: Path, found: list[tuple[Path, str]]) -> None:
    if isinstance(node, dict):
        diagram_data = node.get("diagramData")
        if isinstance(diagram_data, dict):
            statement = diagram_data.get("sql_statement")
            if isinstance(statement, str) and statement.strip():
                found.append((path, statement))
        for key, value in node.items():
            _walk_for_sql(value, (*path, key), found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_for_sql(value, (*path, index), found)


def _get_by_path(document: dict[str, Any], path: Path) -> Any:
    node: Any = document
    for part in path:
        node = node[part]
    return node


def _touch_snapshot_dates(document: dict[str, Any]) -> None:
    now = datetime.now(EDITOR_UPDATE_TIME_ZONE)
    next_update_date = now.date() + timedelta(days=1)
    next_update = datetime.combine(
        next_update_date,
        time(hour=EDITOR_DAILY_UPDATE_HOUR),
        tzinfo=EDITOR_UPDATE_TIME_ZONE,
    )
    for key, value in (
        ("lastUpdate", now.isoformat(timespec="seconds")),
        ("nextUpdate", next_update.isoformat(timespec="seconds")),
        ("createdAt", now.isoformat(timespec="seconds")),
    ):
        document[key] = value
