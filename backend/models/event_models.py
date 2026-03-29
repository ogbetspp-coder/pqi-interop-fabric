from pydantic import BaseModel
from datetime import datetime


class CanonicalEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: str      # CREATED, UPDATED, SKIPPED
    resource_type: str
    resource_id: str
    old_version: str | None
    new_version: str | None
    change_summary: str | None
    created_at: datetime


class RunTrace(BaseModel):
    trace_id: str
    run_id: str
    resource_id: str
    resource_type: str
    source_rows: dict
    mappings_applied: list
    fingerprint_before: str | None
    fingerprint_after: str
    action: str
    reason: str | None
    created_at: datetime


class DownstreamInboxItem(BaseModel):
    inbox_id: str
    event_id: str
    run_id: str
    payload: dict
    resource_ids: list
    old_versions: dict
    new_versions: dict
    markets: list
    received_at: datetime
    processing_status: str


class EngineRunResult(BaseModel):
    run_id: str
    events: list[CanonicalEvent]
    traces: list[RunTrace]
    downstream_items: list[DownstreamInboxItem]
