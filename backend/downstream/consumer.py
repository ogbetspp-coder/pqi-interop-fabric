"""
GlobalRIM downstream mock consumer.

Receives canonical delta payloads from the engine and stores them in
downstream_inbox. This simulates a receiving system that consumes
validated canonical deltas rather than re-parsing source text.
"""

import json
import uuid
from datetime import datetime, timezone

from backend.db import execute, query


def deliver_delta(run_id: str, events: list[dict], changed_resources: list[dict]) -> None:
    """Write one inbox record per run that contains changed resources."""
    changed_events = [e for e in events if e["event_type"] in ("CREATED", "UPDATED")]
    if not changed_events:
        return

    inbox_id = str(uuid.uuid4())
    event_id = changed_events[0]["event_id"]  # anchor to first change event

    resource_ids = [e["resource_id"] for e in changed_events]
    old_versions = {e["resource_id"]: e.get("old_version") for e in changed_events}
    new_versions = {e["resource_id"]: e.get("new_version") for e in changed_events}

    # Extract markets from PPD resources in payload
    markets: list[str] = []
    for res in changed_resources:
        if res.get("resourceType") == "PackagedProductDefinition":
            for ms in res.get("marketingStatus", []):
                country = ms.get("country", {})
                for coding in country.get("coding", []):
                    market = coding.get("code")
                    if market and market not in markets:
                        markets.append(market)

    payload = {
        "type": "canonical-delta",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "events": changed_events,
        "resources": changed_resources,
    }

    execute(
        """
        INSERT INTO downstream_inbox
          (inbox_id, event_id, run_id, payload, resource_ids,
           old_versions, new_versions, markets, processing_status)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, 'received')
        """,
        (
            inbox_id, event_id, run_id,
            json.dumps(payload),
            json.dumps(resource_ids),
            json.dumps(old_versions),
            json.dumps(new_versions),
            json.dumps(markets),
        ),
    )


def get_inbox(limit: int = 50) -> list[dict]:
    return query(
        "SELECT * FROM downstream_inbox ORDER BY received_at DESC LIMIT %s",
        (limit,),
    )
