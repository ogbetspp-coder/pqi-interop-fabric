"""
PQI Canonicalization Engine.

Orchestrates the full pipeline:
  source data → normalize → build FHIR → fingerprint → conditional PUT → event + trace

Hard invariants enforced here:
1. Resources are PUT to HAPI only when content has changed (fingerprint gate).
2. MPD and MID are processed once per product code, not once per presentation.
3. Resource IDs are fully deterministic from business keys.
4. Unchanged resources receive a SKIPPED event, never a spurious version bump.
"""

import json
import uuid
from pathlib import Path

from backend.engine import builder, delta, hapi_client
from backend.events.outbox import record_event, record_trace
from backend.downstream.consumer import deliver_delta
from backend.models.source_models import ErpPresentation
from backend.sources import erp, plm, rim

# ── load mapping config once at module level ──────────────────────────────────

_MAPS_DIR = Path(__file__).parent.parent / "mappings"


def _load(filename: str) -> dict:
    return json.loads((_MAPS_DIR / filename).read_text())


_material_map = _load("material_map.json")["mappings"]
_packaging_type_map = _load("packaging_type_map.json")["mappings"]
_closure_type_map = _load("closure_type_map.json")["mappings"]
_dose_form_map = _load("dose_form_map.json")["mappings"]
_qs_rules = _load("quality_standard_map.json")["rules"]


# ── engine ────────────────────────────────────────────────────────────────────

def run(presentation_ids: list[str] | None = None) -> dict:
    """
    Run canonicalization for all active presentations, or a specific subset.
    Returns a summary dict with run_id and event list.
    """
    run_id = str(uuid.uuid4())

    presentations: list[ErpPresentation]
    if presentation_ids:
        presentations = [
            p for p in erp.get_active_presentations()
            if p.presentation_id in presentation_ids
        ]
    else:
        presentations = erp.get_active_presentations()

    # Deduplicate product codes — one MPD and one MID per product, not per presentation
    seen_products: set[str] = set()
    all_events: list[dict] = []
    changed_resources: list[dict] = []  # for downstream delta

    for pres in presentations:
        product = erp.get_product(pres.product_code)
        if not product:
            continue

        # ── MPD ───────────────────────────────────────────────────────────────
        if pres.product_code not in seen_products:
            seen_products.add(pres.product_code)

            mpd_resource, mpd_mappings = builder.build_mpd(product, _dose_form_map)
            mid_resource, mid_mappings = builder.build_mid(product, _dose_form_map)

            mpd_evt = _process_resource(
                run_id, mpd_resource, "MedicinalProductDefinition",
                source_rows={"erp_product": product.model_dump()},
                mappings=mpd_mappings,
            )
            all_events.append(mpd_evt)
            if mpd_evt["event_type"] in ("CREATED", "UPDATED"):
                changed_resources.append(mpd_resource)

            mid_evt = _process_resource(
                run_id, mid_resource, "ManufacturedItemDefinition",
                source_rows={"erp_product": product.model_dump()},
                mappings=mid_mappings,
            )
            all_events.append(mid_evt)
            if mid_evt["event_type"] in ("CREATED", "UPDATED"):
                changed_resources.append(mid_resource)

        # ── PPD ───────────────────────────────────────────────────────────────
        components = plm.get_components(pres.presentation_id)
        rim_data = rim.get_rim(pres.presentation_id)
        marketing_status = rim_data.marketing_status if rim_data else "unknown"

        ppd_resource, ppd_mappings = builder.build_ppd(
            pres, components,
            _material_map, _packaging_type_map, _closure_type_map,
            _qs_rules, marketing_status,
        )
        ppd_evt = _process_resource(
            run_id, ppd_resource, "PackagedProductDefinition",
            source_rows={
                "erp_presentation": pres.model_dump(),
                "plm_components": [c.model_dump() for c in components],
                "rim_presentation": rim_data.model_dump() if rim_data else None,
            },
            mappings=ppd_mappings,
        )
        all_events.append(ppd_evt)
        if ppd_evt["event_type"] in ("CREATED", "UPDATED"):
            changed_resources.append(ppd_resource)

    # Emit downstream delta for any changed resources
    if changed_resources:
        deliver_delta(run_id, all_events, changed_resources)

    return {
        "run_id": run_id,
        "events": all_events,
        "summary": {
            "created": sum(1 for e in all_events if e["event_type"] == "CREATED"),
            "updated": sum(1 for e in all_events if e["event_type"] == "UPDATED"),
            "skipped": sum(1 for e in all_events if e["event_type"] == "SKIPPED"),
        },
    }


def _process_resource(
    run_id: str,
    resource: dict,
    resource_type: str,
    source_rows: dict,
    mappings: list[dict],
) -> dict:
    resource_id = resource["id"]
    fp_new = delta.fingerprint(resource)
    fp_old = delta.get_stored(resource_id)

    if not delta.has_changed(resource_id, resource):
        # Unchanged — skip PUT entirely
        current_version, _ = hapi_client.get_resource(resource_type, resource_id)
        evt = record_event(
            run_id=run_id,
            event_type="SKIPPED",
            resource_type=resource_type,
            resource_id=resource_id,
            old_version=current_version,
            new_version=current_version,
            change_summary="No content change detected; PUT skipped.",
        )
        record_trace(
            run_id=run_id,
            resource_id=resource_id,
            resource_type=resource_type,
            source_rows=source_rows,
            mappings_applied=mappings,
            fingerprint_before=fp_old,
            fingerprint_after=fp_new,
            action="SKIPPED",
            reason="Fingerprint unchanged",
        )
        return evt

    # Changed or new — PUT to HAPI
    old_version, _ = hapi_client.get_resource(resource_type, resource_id)
    new_version = hapi_client.put_resource(resource_type, resource_id, resource)
    delta.store(resource_id, resource_type, fp_new)

    event_type = "CREATED" if old_version is None else "UPDATED"
    change_summary = _summarise_change(resource, resource_type, old_version)

    evt = record_event(
        run_id=run_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        old_version=old_version,
        new_version=new_version,
        change_summary=change_summary,
    )
    record_trace(
        run_id=run_id,
        resource_id=resource_id,
        resource_type=resource_type,
        source_rows=source_rows,
        mappings_applied=mappings,
        fingerprint_before=fp_old,
        fingerprint_after=fp_new,
        action=event_type,
        reason="Fingerprint changed" if old_version else "New resource",
    )
    return evt


def _summarise_change(resource: dict, resource_type: str, old_version: str | None) -> str:
    if old_version is None:
        return f"{resource_type} {resource['id']} created (version 1)."
    if resource_type == "PackagedProductDefinition":
        # Extract seal supplier from hierarchy for a meaningful summary
        try:
            for cap in resource["packaging"].get("packaging", []):
                for seal in cap.get("packaging", []):
                    for mfr in seal.get("manufacturer", []):
                        supplier = mfr.get("display", "")
                        if supplier:
                            return f"Seal liner supplier updated to '{supplier}'."
        except (KeyError, TypeError):
            pass
    return f"{resource_type} {resource['id']} updated."
