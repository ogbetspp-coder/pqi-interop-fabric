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
    Wipe engine state: clear fingerprints, events, traces, downstream inbox.
    Wipe HAPI (delete all canonical resources). Reseed PLM to initial state.
    Then run full canonicalization from scratch.
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
    # Clear engine support tables
    execute("TRUNCATE canonical_fingerprints, canonical_events, canonical_run_traces, downstream_inbox")

    # Delete all canonical resources from HAPI
    resource_ids = [
        ("MedicinalProductDefinition", "mpd-avl10"),
        ("MedicinalProductDefinition", "mpd-cvx5"),
        ("ManufacturedItemDefinition", "mid-avl10"),
        ("ManufacturedItemDefinition", "mid-cvx5"),
        ("PackagedProductDefinition", "ppd-avl10-28ct-us"),
        ("PackagedProductDefinition", "ppd-avl10-56ct-eu"),
        ("PackagedProductDefinition", "ppd-cvx5-30ct-us"),
        ("PackagedProductDefinition", "ppd-cvx5-30bl-eu"),
        ("PackagedProductDefinition", "ppd-avl10-28ct-ca"),
    ]
    for rt, rid in resource_ids:
        try:
            # HAPI R5 delete
            import os, httpx
            base = os.environ.get("HAPI_BASE_URL", "http://localhost:8080/fhir")
            httpx.delete(f"{base}/{rt}/{rid}", timeout=10)
        except Exception:
            pass

    result = canonicalizer.run()
    return {"reset": True, **result}


@router.get("/canonical")
def list_canonical():
    """Summary of all canonical resources from HAPI."""
    summaries = []
    for rt, rid in [
        ("MedicinalProductDefinition", "mpd-avl10"),
        ("MedicinalProductDefinition", "mpd-cvx5"),
        ("ManufacturedItemDefinition", "mid-avl10"),
        ("ManufacturedItemDefinition", "mid-cvx5"),
        ("PackagedProductDefinition", "ppd-avl10-28ct-us"),
        ("PackagedProductDefinition", "ppd-avl10-56ct-eu"),
        ("PackagedProductDefinition", "ppd-cvx5-30ct-us"),
        ("PackagedProductDefinition", "ppd-cvx5-30bl-eu"),
        ("PackagedProductDefinition", "ppd-avl10-28ct-ca"),
    ]:
        version, resource = hapi_client.get_resource(rt, rid)
        if resource:
            summaries.append({
                "resource_type": rt,
                "resource_id": rid,
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
