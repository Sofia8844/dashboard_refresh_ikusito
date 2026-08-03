from __future__ import annotations

from copy import deepcopy
from typing import Any


def extract_snapshot_document(snapshot: dict[str, Any]) -> dict[str, Any]:
    for key in ("document", "resolvedDocument", "page", "data"):
        candidate = snapshot.get(key)
        if isinstance(candidate, dict):
            return deepcopy(candidate)
    return deepcopy(snapshot)


def reduce_events(snapshot: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    document = extract_snapshot_document(snapshot)

    for event in sorted(events, key=_event_sort_key):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
        replacement = _document_replacement(payload)
        if replacement is not None:
            document = replacement
            continue
        _apply_known_mutation(document, event.get("type") or event.get("eventType"), payload)

    return {"resolvedDocument": document}


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("sequence") or event.get("version") or ""),
        str(event.get("createdAt") or event.get("created_at") or event.get("timestamp") or ""),
        str(event.get("id") or ""),
    )


def _document_replacement(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("document", "resolvedDocument", "page"):
        value = payload.get(key)
        if isinstance(value, dict):
            return deepcopy(value)
    return None


def _apply_known_mutation(document: dict[str, Any], event_type: str | None, payload: dict[str, Any]) -> None:
    if not event_type:
        return

    normalized = event_type.lower()
    if "widget" in normalized and ("updated" in normalized or "upsert" in normalized):
        widget = payload.get("widget")
        widget_id = payload.get("widgetId") or payload.get("id")
        if isinstance(widget, dict) and widget_id:
            _replace_object_by_id(document, str(widget_id), widget)
    elif "widget" in normalized and ("deleted" in normalized or "removed" in normalized):
        widget_id = payload.get("widgetId") or payload.get("id")
        if widget_id:
            _remove_object_by_id(document, str(widget_id))


def _replace_object_by_id(node: Any, object_id: str, replacement: dict[str, Any]) -> bool:
    if isinstance(node, dict):
        if str(node.get("id")) == object_id:
            node.clear()
            node.update(deepcopy(replacement))
            return True
        return any(_replace_object_by_id(value, object_id, replacement) for value in node.values())
    if isinstance(node, list):
        return any(_replace_object_by_id(item, object_id, replacement) for item in node)
    return False


def _remove_object_by_id(node: Any, object_id: str) -> bool:
    if isinstance(node, list):
        original_len = len(node)
        node[:] = [
            item for item in node if not (isinstance(item, dict) and str(item.get("id")) == object_id)
        ]
        removed = len(node) != original_len
        return removed or any(_remove_object_by_id(item, object_id) for item in node)
    if isinstance(node, dict):
        return any(_remove_object_by_id(value, object_id) for value in node.values())
    return False

