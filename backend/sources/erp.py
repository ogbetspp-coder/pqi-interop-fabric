"""NovaPharma ERP source reader. Read-only access to erp_* tables."""

from backend.db import query
from backend.models.source_models import ErpProduct, ErpPresentation


def get_all_products() -> list[ErpProduct]:
    rows = query("SELECT * FROM erp_products ORDER BY product_code")
    return [ErpProduct(**r) for r in rows]


def get_product(product_code: str) -> ErpProduct | None:
    rows = query("SELECT * FROM erp_products WHERE product_code = %s", (product_code,))
    return ErpProduct(**rows[0]) if rows else None


def get_active_presentations() -> list[ErpPresentation]:
    rows = query(
        "SELECT * FROM erp_presentations WHERE active = TRUE ORDER BY presentation_id"
    )
    return [ErpPresentation(**r) for r in rows]


def get_presentation(presentation_id: str) -> ErpPresentation | None:
    rows = query(
        "SELECT * FROM erp_presentations WHERE presentation_id = %s",
        (presentation_id,),
    )
    return ErpPresentation(**rows[0]) if rows else None
