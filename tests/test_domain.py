from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.event_reducer import reduce_events
from app.domain.jobs import build_idempotency_key
from app.domain.widgets import apply_widget_rows, collect_sql_widgets
from app.services.worker import _snapshot_is_expired


def test_build_idempotency_key() -> None:
    assert build_idempotency_key("project", "page", "snapshot") == "refresh:project:page:snapshot"


def test_event_reducer_replaces_document_from_latest_event() -> None:
    snapshot = {"document": {"widgets": [{"id": "old"}]}}
    events = [
        {"sequence": 2, "payload": {"document": {"widgets": [{"id": "new"}]}}},
        {"sequence": 1, "payload": {"document": {"widgets": [{"id": "mid"}]}}},
    ]

    assert reduce_events(snapshot, events)["resolvedDocument"]["widgets"][0]["id"] == "new"


def test_collect_sql_widgets_and_apply_rows_preserves_design() -> None:
    document = {
        "widgets": [
            {
                "id": "w1",
                "x": 10,
                "diagramData": {
                    "sql_statement": "select 1",
                    "rows": [["old"]],
                    "columns": ["value"],
                    "chartType": "bar",
                },
            }
        ],
        "background": "white",
    }
    widgets = collect_sql_widgets(document)

    updated = apply_widget_rows(document, {widgets[0][0]: [[1]]})

    assert updated["widgets"][0]["diagramData"]["rows"] == [[1]]
    assert updated["widgets"][0]["diagramData"]["sql_statement"] == "select 1"
    assert updated["widgets"][0]["diagramData"]["chartType"] == "bar"
    assert updated["widgets"][0]["x"] == 10
    assert updated["background"] == "white"
    assert document["widgets"][0]["diagramData"]["rows"] == [["old"]]


def test_apply_rows_sets_next_update_to_next_day_at_8_bogota() -> None:
    document = {"widgets": [{"diagramData": {"sql_statement": "select 1", "rows": []}}]}
    widgets = collect_sql_widgets(document)

    updated = apply_widget_rows(document, {widgets[0][0]: [[1]]})

    last_update = datetime.fromisoformat(updated["lastUpdate"])
    next_update = datetime.fromisoformat(updated["nextUpdate"])
    assert next_update.hour == 8
    assert next_update.minute == 0
    assert next_update.second == 0
    assert next_update.utcoffset() == last_update.utcoffset()
    assert next_update.date() == last_update.date() + timedelta(days=1)


def test_snapshot_expiration() -> None:
    expired = {"document": {"nextUpdate": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}}
    current = {"document": {"nextUpdate": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()}}

    assert _snapshot_is_expired(expired) is True
    assert _snapshot_is_expired(current) is False
