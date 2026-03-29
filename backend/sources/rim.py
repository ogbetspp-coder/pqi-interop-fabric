"""ReguTrack RIM source reader. Read-only access to rim_presentations."""

from backend.db import query
from backend.models.source_models import RimPresentation


def get_rim(presentation_id: str) -> RimPresentation | None:
    rows = query(
        "SELECT * FROM rim_presentations WHERE presentation_id = %s",
        (presentation_id,),
    )
    return RimPresentation(**rows[0]) if rows else None


def get_all_rim() -> list[RimPresentation]:
    rows = query("SELECT * FROM rim_presentations ORDER BY presentation_id")
    return [RimPresentation(**r) for r in rows]
