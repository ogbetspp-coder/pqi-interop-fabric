"""
Pure canonical FHIR R5 resource builders.

Each function takes source domain objects and mapping config dicts,
and returns a complete FHIR resource dict ready for HAPI.

No DB access, no HAPI access, no side effects.
Deterministic: same inputs always produce the same output.
"""

from backend.models.source_models import ErpProduct, ErpPresentation, PlmComponent

# ── ID generation ──────────────────────────────────────────────────────────────

def mpd_id(product_code: str) -> str:
    return f"mpd-{product_code.lower()}"


def mid_id(product_code: str) -> str:
    return f"mid-{product_code.lower()}"


def ppd_id(presentation_id: str) -> str:
    return f"ppd-{presentation_id.lower()}"


# ── Mapping helpers ────────────────────────────────────────────────────────────

def _map(local: str, mappings: list[dict], key: str = "local") -> dict | None:
    for m in mappings:
        if m.get(key, "").lower() == local.lower():
            return m
    return None


def _quality_standards(
    component_type: str, market: str, qs_rules: list[dict]
) -> list[dict]:
    for rule in qs_rules:
        if rule["component_type"] == component_type and rule["market"] == market:
            return [
                {
                    "type": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/package-property",
                            "code": "Quality Standard",
                            "display": "Quality Standard",
                        }]
                    },
                    "valueCodeableConcept": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/package-grade",
                            "code": s["code"],
                            "display": s["display"],
                        }]
                    },
                }
                for s in rule["standards"]
            ]
    return []


# ── MedicinalProductDefinition ─────────────────────────────────────────────────

def build_mpd(product: ErpProduct, dose_form_mappings: list[dict]) -> tuple[dict, list[dict]]:
    """
    Returns (resource_dict, mappings_applied).
    mappings_applied records which local terms were resolved for the trace.
    """
    applied: list[dict] = []

    dose_form_match = _map(product.dose_form, dose_form_mappings)
    if dose_form_match:
        applied.append({"type": "dose_form", "local": product.dose_form,
                         "code": dose_form_match["code"], "display": dose_form_match["display"]})
        dose_form_coding = [{"system": "http://standardterms.edqm.eu",
                              "code": dose_form_match["code"],
                              "display": dose_form_match["display"]}]
    else:
        dose_form_coding = [{"text": product.dose_form}]

    route_match = _map(product.route, dose_form_mappings, key="local")
    if route_match and "route_code" in route_match:
        applied.append({"type": "route", "local": product.route,
                         "code": route_match["route_code"], "display": route_match["route_display"]})
        route_coding = [{"system": "http://standardterms.edqm.eu",
                          "code": route_match["route_code"],
                          "display": route_match["route_display"]}]
    else:
        route_coding = [{"text": product.route}]

    resource = {
        "resourceType": "MedicinalProductDefinition",
        "id": mpd_id(product.product_code),
        "meta": {
            "profile": [
                "http://hl7.org/fhir/uv/pharm-quality/StructureDefinition/MedicinalProductDefinition-drug-product-pq"
            ]
        },
        "identifier": [{
            "system": "urn:example:novapharma:erp:product-code",
            "value": product.product_code,
        }],
        "description": (
            f"Fictional product anchor for {product.product_name} {product.strength} "
            f"{product.dose_form}. Reusable across all package variants and markets."
        ),
        "combinedPharmaceuticalDoseForm": {"coding": dose_form_coding},
        "route": [{"coding": route_coding}],
        "name": [{
            "productName": f"{product.product_name} {product.strength} {product.dose_form}s",
            "type": {
                "coding": [{
                    "system": "http://hl7.org/fhir/uv/pharm-quality/CodeSystem/cs-productNameType-pq-example",
                    "code": "Proprietary",
                    "display": "Proprietary",
                }]
            },
            "part": [
                {
                    "part": product.strength,
                    "type": {"coding": [{
                        "system": "http://hl7.org/fhir/medicinal-product-name-part-type",
                        "code": "StrengthPart",
                        "display": "Strength part",
                    }]},
                },
                {
                    "part": f"{product.dose_form}s",
                    "type": {"coding": [{
                        "system": "http://hl7.org/fhir/medicinal-product-name-part-type",
                        "code": "DoseFormPart",
                        "display": "Dose form part",
                    }]},
                },
            ],
        }],
    }
    return resource, applied


# ── ManufacturedItemDefinition ─────────────────────────────────────────────────

def build_mid(product: ErpProduct, dose_form_mappings: list[dict]) -> tuple[dict, list[dict]]:
    applied: list[dict] = []

    dose_form_match = _map(product.dose_form, dose_form_mappings)
    if dose_form_match:
        applied.append({"type": "dose_form", "local": product.dose_form,
                         "code": dose_form_match["code"], "display": dose_form_match["display"]})
        dose_form_coding = [{"system": "http://standardterms.edqm.eu",
                              "code": dose_form_match["code"],
                              "display": dose_form_match["display"]}]
    else:
        dose_form_coding = [{"text": product.dose_form}]

    resource = {
        "resourceType": "ManufacturedItemDefinition",
        "id": mid_id(product.product_code),
        "meta": {
            "profile": [
                "http://hl7.org/fhir/uv/pharm-quality/StructureDefinition/ManufacturedItemDefinition-drug-pq"
            ]
        },
        "status": "active",
        "name": f"{product.product_name} {product.strength} {product.dose_form}",
        "manufacturedDoseForm": {"coding": dose_form_coding},
        "unitOfPresentation": {"text": product.dose_form.capitalize()},
    }
    return resource, applied


# ── PackagedProductDefinition ──────────────────────────────────────────────────

def build_ppd(
    presentation: ErpPresentation,
    components: list[PlmComponent],
    material_mappings: list[dict],
    packaging_type_mappings: list[dict],
    closure_type_mappings: list[dict],
    qs_rules: list[dict],
    marketing_status: str,
) -> tuple[dict, list[dict]]:
    applied: list[dict] = []

    market_iso = {
        "US": {"code": "US", "display": "United States"},
        "EU": {"code": "EU", "display": "European Union"},
        "CA": {"code": "CA", "display": "Canada"},
    }.get(presentation.market, {"code": presentation.market, "display": presentation.market})

    # Build packaging node for a single component
    def _component_node(comp: PlmComponent, children: list[dict]) -> dict:
        mat_match = _map(comp.material_local, material_mappings)
        if mat_match:
            applied.append({"type": "material", "local": comp.material_local,
                             "code": mat_match["code"], "display": mat_match["display"]})
            material_coding = [{"system": "http://hl7.org/fhir/package-material",
                                 "code": mat_match["code"], "display": mat_match["display"]}]
        else:
            material_coding = [{"text": comp.material_local}]

        node: dict = {
            "material": [{"coding": material_coding}],
            "manufacturer": [{"display": comp.supplier}],
        }

        # Component type coding
        if comp.component_type in ("CHILD_RESISTANT_CLOSURE", "FOIL_SEAL",
                                   "BLISTER_BODY", "BLISTER_LID"):
            ct_match = _map(comp.component_type, closure_type_mappings)
            if ct_match:
                applied.append({"type": "closure_type", "local": comp.component_type,
                                 "code": ct_match["code"], "display": ct_match["display"]})
                node["type"] = {"coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/container-closure-type",
                    "code": ct_match["code"],
                    "display": ct_match["display"],
                }]}
            node["componentPart"] = True
        else:
            # Root container (BOTTLE etc.) — use packaging-type system
            pt_match = _map(comp.component_type, packaging_type_mappings)
            if pt_match:
                applied.append({"type": "packaging_type", "local": comp.component_type,
                                 "code": pt_match["code"], "display": pt_match["display"]})
                node["type"] = {"coding": [{
                    "system": "http://hl7.org/fhir/packaging-type",
                    "code": pt_match["code"],
                    "display": pt_match["display"],
                }]}

        # Quality standards from config
        qs = _quality_standards(comp.component_type, presentation.market, qs_rules)
        if qs:
            node["property"] = qs

        if children:
            node["packaging"] = children

        return node

    # Build hierarchy bottom-up
    # Index components by component_id
    by_id = {c.component_id: c for c in components}

    # Find root (no parent) and children map
    roots = [c for c in components if c.parent_component_id is None]
    children_of: dict[str, list[PlmComponent]] = {}
    for c in components:
        if c.parent_component_id:
            children_of.setdefault(c.parent_component_id, []).append(c)

    def _build_node_recursive(comp: PlmComponent) -> dict:
        child_nodes = [_build_node_recursive(ch) for ch in children_of.get(comp.component_id, [])]
        return _component_node(comp, child_nodes)

    packaging_node: dict = {}
    if roots:
        root = roots[0]
        packaging_node = _build_node_recursive(root)
        # Root bottle: add containedItem pointing to MID
        packaging_node["containedItem"] = [{
            "item": {
                "reference": {"reference": f"ManufacturedItemDefinition/{mid_id(presentation.product_code)}"}
            },
            "amount": {"value": presentation.pack_count, "unit": presentation.pack_unit},
        }]

    # Add bottle color property if it is a BOTTLE presentation
    if presentation.packaging_family == "BOTTLE" and "property" in packaging_node:
        packaging_node["property"].insert(0, {
            "type": {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/package-property",
                "code": "Color", "display": "Color",
            }]},
            "valueCodeableConcept": {"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/drug-substance-or-product-color",
                "code": "white", "display": "White",
            }]},
        })

    resource = {
        "resourceType": "PackagedProductDefinition",
        "id": ppd_id(presentation.presentation_id),
        "meta": {
            "profile": [
                "http://hl7.org/fhir/uv/pharm-quality/StructureDefinition/PackagedProductDefinition-drug-pq"
            ]
        },
        "name": (
            f"{presentation.local_packaging_text or presentation.presentation_id}"
        ),
        "description": (
            f"{presentation.packaging_family.capitalize()} presentation, "
            f"{presentation.pack_count} {presentation.pack_unit}s, "
            f"{market_iso['display']} market. "
            "Primary container closure system only; secondary carton excluded from structured hierarchy."
        ),
        "packageFor": [{"reference": f"MedicinalProductDefinition/{mpd_id(presentation.product_code)}"}],
        "containedItemQuantity": [{"value": presentation.pack_count, "unit": presentation.pack_unit}],
        "marketingStatus": [{
            "country": {"coding": [{
                "system": "urn:iso:std:iso:3166",
                "code": market_iso["code"],
                "display": market_iso["display"],
            }]},
            "status": {"text": marketing_status},
        }],
        "packaging": packaging_node,
    }
    return resource, applied
