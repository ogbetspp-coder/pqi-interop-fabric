"""Read-only endpoints for the three fictional source domains."""

from fastapi import APIRouter
from backend.sources import erp, plm, rim

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/erp/products")
def list_erp_products():
    return [p.model_dump() for p in erp.get_all_products()]


@router.get("/erp/presentations")
def list_erp_presentations(active_only: bool = True):
    pres = erp.get_active_presentations() if active_only else erp.get_active_presentations()
    return [p.model_dump() for p in pres]


@router.get("/plm/components")
def list_plm_components(presentation_id: str | None = None):
    if presentation_id:
        return [c.model_dump() for c in plm.get_components(presentation_id)]
    return [c.model_dump() for c in plm.get_all_components()]


@router.get("/rim/presentations")
def list_rim_presentations():
    return [r.model_dump() for r in rim.get_all_rim()]
