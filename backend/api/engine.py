"""
Engine endpoints.

POST /engine/run         — run full canonicalization
POST /engine/flows/2     — apply Flow 2: seal supplier change on AVL10-US, rerun
POST /engine/flows/3     — apply Flow 3: activate CA market variant, rerun
POST /engine/reset       — wipe HAPI + fingerprints, reseed, rerun from scratch
GET  /engine/canonical   — summary of all canonical resources (from HAPI via backend)
GET  /engine/canonical/{resource_type}/{resource_id} — single resource from HAPI
GET  /engine/canonical/{resource_type}/{resource_id}/history
GET  /engine/mappings    — return all mapping config (for UI transparency)
GET  /engine/trace/{resource_id} — latest provenance trace for a resource
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.db import execute, query
from backend.engine import canonicalizer, hapi_client
from backend.events.outbox import get_traces_for_run, get_latest_trace_for_resource

router = APIRouter(prefix="/engine", tags=["engine"])

_MAPS_DIR = Path(__file__).parent.parent / "mappings"


@router.post("/run")
def run_engine():
    result = canonicalizer.run()
    return result


@router.post("/flows/2")
def flow_2_supplier_change():
    """
    Flow 2: Controlled supplier change.
    Updates the AVL10-28CT-US foil seal supplier in PLM from SealGuard Tech
    to BarrierSeal Systems, then reruns the engine for that presentation only.
    Only ppd-avl10-28ct-us should version. MPD and MID must stay unchanged.
    """
    # Check current supplier to make it idempotent (show before/after clearly)
    rows = query(
        "SELECT supplier FROM plm_components WHERE component_id = %s",
        ("AVL10-US-SEAL",),
    )
    if not rows:
        raise HTTPException(404, "PLM component AVL10-US-SEAL not found")

    before = rows[0]["supplier"]
    after = "BarrierSeal Systems" if before == "SealGuard Tech" else "SealGuard Tech"

    execute(
        "UPDATE plm_components SET supplier = %s WHERE component_id = %s",
        (after, "AVL10-US-SEAL"),
    )

    result = canonicalizer.run(presentation_ids=["AVL10-28CT-US"])
    return {"flow": 2, "supplier_before": before, "supplier_after": after, **result}


@router.post("/flows/3")
def flow_3_new_market():
    """
    Flow 3: New market variant.
    Activates the pre-staged AVL10-28CT-CA (Canada) presentation.
    Existing mpd-avl10 must be reused — no new MPD created.
    """
    execute(
        "UPDATE erp_presentations SET active = TRUE WHERE presentation_id = %s",
        ("AVL10-28CT-CA",),
    )
    result = canonicalizer.run(presentation_ids=["AVL10-28CT-CA"])
    return {"flow": 3, "activated_presentation": "AVL10-28CT-CA", **result}


@router.post("/reset")
def reset_demo():
    """
    Wipe engine state: clear fingerprints, events, traces, runs, downstream inbox.
    Wipe HAPI (delete all canonical resources known to the fingerprint registry).
    Reseed PLM to initial state. Then run full canonicalization from scratch.
    """
    # Reset PLM seal supplier to initial state
    execute(
        "UPDATE plm_components SET supplier = 'SealGuard Tech' WHERE component_id = %s",
        ("AVL10-US-SEAL",),
    )
    # Deactivate CA presentation
    execute(
        "UPDATE erp_presentations SET active = FALSE WHERE presentation_id = %s",
        ("AVL10-28CT-CA",),
    )

    # Delete all canonical resources from HAPI using the fingerprint registry (no hardcoded list)
    known = query("SELECT resource_type, resource_id FROM canonical_fingerprints")
    import os, httpx
    base = os.environ.get("HAPI_BASE_URL", "http://localhost:8080/fhir")
    for row in known:
        try:
            httpx.delete(f"{base}/{row['resource_type']}/{row['resource_id']}", timeout=10)
        except Exception:
            pass

    # Clear engine support tables after HAPI delete
    execute(
        "TRUNCATE canonical_fingerprints, canonical_events, canonical_run_traces, "
        "canonical_runs, downstream_inbox"
    )

    result = canonicalizer.run()
    return {"reset": True, **result}


@router.get("/canonical")
def list_canonical():
    """Summary of all canonical resources from HAPI (registry-driven, no hardcoded list)."""
    known = query(
        "SELECT resource_type, resource_id FROM canonical_fingerprints "
        "ORDER BY resource_type, resource_id"
    )
    summaries = []
    for row in known:
        version, resource = hapi_client.get_resource(row["resource_type"], row["resource_id"])
        if resource:
            summaries.append({
                "resource_type": row["resource_type"],
                "resource_id": row["resource_id"],
                "version": version,
                "last_updated": resource.get("meta", {}).get("lastUpdated"),
            })
    return summaries


@router.get("/canonical/{resource_type}/{resource_id}")
def get_canonical(resource_type: str, resource_id: str):
    version, resource = hapi_client.get_resource(resource_type, resource_id)
    if not resource:
        raise HTTPException(404, f"{resource_type}/{resource_id} not found in HAPI")
    return resource


@router.get("/canonical/{resource_type}/{resource_id}/history")
def get_canonical_history(resource_type: str, resource_id: str):
    try:
        history = hapi_client.get_history(resource_type, resource_id)
    except Exception:
        raise HTTPException(404, f"History for {resource_type}/{resource_id} not found")
    return [
        {
            "version": r.get("meta", {}).get("versionId"),
            "lastUpdated": r.get("meta", {}).get("lastUpdated"),
        }
        for r in history
    ]


@router.get("/mappings")
def get_mappings():
    maps = {}
    for f in _MAPS_DIR.glob("*.json"):
        maps[f.stem] = json.loads(f.read_text())
    return maps


@router.get("/trace/{resource_id}")
def get_trace(resource_id: str):
    trace = get_latest_trace_for_resource(resource_id)
    if not trace:
        raise HTTPException(404, f"No trace found for {resource_id}")
    return trace


# ── UI aggregate endpoints ─────────────────────────────────────────────────────
# These endpoints serve exactly what the UI pages need in one call.
# UI must never do N+1 calls through the backend into HAPI.

@router.get("/ui/overview")
def ui_overview():
    """Single-call summary for the Why This Matters page."""
    from backend.sources import erp as erp_source
    products = erp_source.get_all_products()
    presentations = erp_source.get_active_presentations()
    run_rows = query(
        "SELECT COUNT(*) AS n, MAX(started_at) AS last_at FROM canonical_runs"
    )
    resource_rows = query("SELECT COUNT(*) AS n FROM canonical_fingerprints")
    run_count = run_rows[0]["n"] if run_rows else 0
    last_run_at = run_rows[0]["last_at"]
    canonical_resource_count = resource_rows[0]["n"] if resource_rows else 0
    return {
        "product_count": len(products),
        "active_presentation_count": len(presentations),
        "canonical_resource_count": canonical_resource_count,
        "run_count": run_count,
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
        "products": [p.model_dump() for p in products],
        "presentations": [p.model_dump() for p in presentations],
    }


@router.get("/ui/canonical-summary")
def ui_canonical_summary():
    """
    All canonical resources enriched with display-ready fields.
    Replaces N+1 calls in the Canonical Model page.
    """
    known = query(
        "SELECT resource_type, resource_id FROM canonical_fingerprints "
        "ORDER BY resource_type, resource_id"
    )
    resources = []
    counts: dict[str, int] = {}

    for row in known:
        rt, rid = row["resource_type"], row["resource_id"]
        counts[rt] = counts.get(rt, 0) + 1
        version, resource = hapi_client.get_resource(rt, rid)
        if not resource:
            continue

        entry: dict = {
            "resource_type": rt,
            "resource_id": rid,
            "version": version,
            "last_updated": resource.get("meta", {}).get("lastUpdated"),
        }

        if rt == "MedicinalProductDefinition":
            entry["display_name"] = resource.get("name", [{}])[0].get("productName", rid)
            entry["product_code"] = resource.get("identifier", [{}])[0].get("value", "")

        elif rt == "PackagedProductDefinition":
            # Extract market from marketingStatus (country or jurisdiction)
            market = ""
            for ms in resource.get("marketingStatus", []):
                for src in ("country", "jurisdiction"):
                    for coding in ms.get(src, {}).get("coding", []):
                        market = coding.get("code", "")
                        break
                if market:
                    break
            entry["market"] = market
            qty = resource.get("containedItemQuantity", [{}])[0]
            entry["pack_count"] = qty.get("value")
            entry["pack_unit"] = qty.get("unit", "")
            entry["package_for"] = (
                resource.get("packageFor", [{}])[0].get("reference", "").split("/")[-1]
            )

        resources.append(entry)

    return {"resources": resources, "counts": counts}


@router.get("/ui/latest-run")
def ui_latest_run():
    """Latest engine run with lifecycle state and events."""
    run_rows = query(
        "SELECT * FROM canonical_runs ORDER BY started_at DESC LIMIT 1"
    )
    if not run_rows:
        return None
    run = run_rows[0]
    events = query(
        "SELECT * FROM canonical_events WHERE run_id = %s ORDER BY created_at",
        (run["run_id"],),
    )
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "started_at": run["started_at"].isoformat() if run["started_at"] else None,
        "completed_at": run["completed_at"].isoformat() if run.get("completed_at") else None,
        "summary": run.get("summary"),
        "events": [
            {
                "event_type": e["event_type"],
                "resource_type": e["resource_type"],
                "resource_id": e["resource_id"],
                "old_version": e.get("old_version"),
                "new_version": e.get("new_version"),
                "change_summary": e.get("change_summary"),
            }
            for e in events
        ],
    }


@router.get("/ui/resource-trace/{resource_id}")
def ui_resource_trace(resource_id: str):
    """
    Combined trace + history for a resource.
    Replaces two separate calls in the Technical Evidence page.
    """
    trace = get_latest_trace_for_resource(resource_id)
    if not trace:
        raise HTTPException(404, f"No trace found for {resource_id}")

    resource_type = trace["resource_type"]
    try:
        history = hapi_client.get_history(resource_type, resource_id)
    except Exception:
        history = []

    return {
        "trace": {
            "action": trace["action"],
            "reason": trace["reason"],
            "fingerprint_before": trace.get("fingerprint_before"),
            "fingerprint_after": trace["fingerprint_after"],
            "mapping_artifact_hashes": trace.get("mapping_artifact_hashes"),
            "source_rows": trace["source_rows"],
            "mappings_applied": trace["mappings_applied"],
        },
        "history": [
            {
                "version": r.get("meta", {}).get("versionId"),
                "lastUpdated": r.get("meta", {}).get("lastUpdated"),
            }
            for r in history
        ],
    }
