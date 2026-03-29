"""PackVault PLM source reader. Read-only access to plm_components."""

from backend.db import query
from backend.models.source_models import PlmComponent


def get_components(presentation_id: str) -> list[PlmComponent]:
    rows = query(
        "SELECT * FROM plm_components WHERE presentation_id = %s AND active = TRUE "
        "ORDER BY component_id",
        (presentation_id,),
    )
    return [PlmComponent(**r) for r in rows]


def get_all_components() -> list[PlmComponent]:
    rows = query(
        "SELECT * FROM plm_components WHERE active = TRUE ORDER BY presentation_id, component_id"
    )
    return [PlmComponent(**r) for r in rows]
