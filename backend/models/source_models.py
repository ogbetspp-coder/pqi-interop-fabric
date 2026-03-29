from pydantic import BaseModel


class ErpProduct(BaseModel):
    product_code: str
    product_name: str
    strength: str
    dose_form: str
    route: str
    active: bool


class ErpPresentation(BaseModel):
    presentation_id: str
    product_code: str
    market: str
    pack_count: int
    pack_unit: str
    packaging_family: str
    local_packaging_text: str | None
    active: bool


class PlmComponent(BaseModel):
    component_id: str
    presentation_id: str
    component_type: str
    parent_component_id: str | None
    material_local: str
    supplier: str
    spec_reference: str | None
    active: bool


class RimPresentation(BaseModel):
    presentation_id: str
    submission_id: str | None
    marketing_status: str
    approval_date: str | None
    dossier_reference: str | None
