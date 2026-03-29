"""Event outbox — writes canonical events and run traces to Postgres."""

import uuid
from datetime import datetime, timezone

from backend.db import execute, query


def record_event(
    run_id: str,
    event_type: str,
    resource_type: str,
    resource_id: str,
    old_version: str | None,
    new_version: str | None,
    change_summary: str | None,
) -> dict:
    event_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO canonical_events
          (event_id, run_id, event_type, resource_type, resource_id,
           old_version, new_version, change_summary)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (event_id, run_id, event_type, resource_type, resource_id,
         old_version, new_version, change_summary),
    )
    return {
        "event_id": event_id,
        "run_id": run_id,
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "old_version": old_version,
        "new_version": new_version,
        "change_summary": change_summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def record_trace(
    run_id: str,
    resource_id: str,
    resource_type: str,
    source_rows: dict,
    mappings_applied: list,
    fingerprint_before: str | None,
    fingerprint_after: str,
    action: str,
    reason: str | None,
) -> None:
    import json
    trace_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO canonical_run_traces
          (trace_id, run_id, resource_id, resource_type, source_rows,
           mappings_applied, fingerprint_before, fingerprint_after, action, reason)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
        """,
        (
            trace_id, run_id, resource_id, resource_type,
            json.dumps(source_rows), json.dumps(mappings_applied),
            fingerprint_before, fingerprint_after, action, reason,
        ),
    )


def get_events(limit: int = 100) -> list[dict]:
    return query(
        "SELECT * FROM canonical_events ORDER BY created_at DESC LIMIT %s",
        (limit,),
    )


def get_traces_for_run(run_id: str) -> list[dict]:
    return query(
        "SELECT * FROM canonical_run_traces WHERE run_id = %s ORDER BY created_at",
        (run_id,),
    )


def get_latest_trace_for_resource(resource_id: str) -> dict | None:
    rows = query(
        "SELECT * FROM canonical_run_traces WHERE resource_id = %s ORDER BY created_at DESC LIMIT 1",
        (resource_id,),
    )
    return rows[0] if rows else None
