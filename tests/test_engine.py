"""
Engine acceptance tests.

All tests require a running local stack (Postgres + HAPI).
See conftest.py for setup.

Hard gates (marked with HARD GATE):
  - test_supplier_change_versions_only_ppd
  - test_no_ui_hardcoded_facts (manual verification note)
  - test_new_market_reuses_exact_mpd_id
"""

import pytest
from backend.engine import canonicalizer, hapi_client
from backend.db import execute, query


# ── 1. Initial canonicalization creates expected resource set ─────────────────

def test_initial_canonicalization_creates_all_resources():
    result = canonicalizer.run()
    resource_ids = {e["resource_id"] for e in result["events"]}

    assert "mpd-avl10" in resource_ids
    assert "mpd-cvx5" in resource_ids
    assert "mid-avl10" in resource_ids
    assert "mid-cvx5" in resource_ids
    assert "ppd-avl10-28ct-us" in resource_ids
    assert "ppd-avl10-56ct-eu" in resource_ids
    assert "ppd-cvx5-30ct-us" in resource_ids
    assert "ppd-cvx5-30bl-eu" in resource_ids

    # All should be CREATED on first run
    created = {e["resource_id"] for e in result["events"] if e["event_type"] == "CREATED"}
    assert "mpd-avl10" in created
    assert "ppd-avl10-28ct-us" in created


def test_initial_canonicalization_persists_to_hapi():
    canonicalizer.run()

    version, resource = hapi_client.get_resource("MedicinalProductDefinition", "mpd-avl10")
    assert resource is not None
    assert version == "1"

    version, resource = hapi_client.get_resource("PackagedProductDefinition", "ppd-avl10-28ct-us")
    assert resource is not None
    assert version == "1"


# ── 2. Supplier change updates only the intended PPD (HARD GATE) ──────────────

def test_supplier_change_versions_only_ppd():
    """
    HARD GATE: A seal supplier change in PLM must version only the affected PPD.
    MPD and MID must NOT receive a new version. This is the core thesis.
    """
    canonicalizer.run()  # establish v1 baseline for all resources

    # Capture pre-change versions from HAPI
    mpd_v_before, _ = hapi_client.get_resource("MedicinalProductDefinition", "mpd-avl10")
    mid_v_before, _ = hapi_client.get_resource("ManufacturedItemDefinition", "mid-avl10")
    ppd_us_v_before, _ = hapi_client.get_resource("PackagedProductDefinition", "ppd-avl10-28ct-us")
    ppd_eu_v_before, _ = hapi_client.get_resource("PackagedProductDefinition", "ppd-avl10-56ct-eu")

    # Apply supplier change in PLM
    execute(
        "UPDATE plm_components SET supplier = 'BarrierSeal Systems' WHERE component_id = %s",
        ("AVL10-US-SEAL",),
    )

    result = canonicalizer.run(presentation_ids=["AVL10-28CT-US"])
    events_by_id = {e["resource_id"]: e for e in result["events"]}

    # PPD for US must be UPDATED
    assert events_by_id["ppd-avl10-28ct-us"]["event_type"] == "UPDATED"

    # HARD GATE: MPD must NOT be versioned
    mpd_v_after, _ = hapi_client.get_resource("MedicinalProductDefinition", "mpd-avl10")
    assert mpd_v_after == mpd_v_before, (
        f"HARD GATE FAILED: mpd-avl10 version changed from {mpd_v_before} to {mpd_v_after}. "
        "A supplier change must not version the product anchor."
    )

    # HARD GATE: MID must NOT be versioned
    mid_v_after, _ = hapi_client.get_resource("ManufacturedItemDefinition", "mid-avl10")
    assert mid_v_after == mid_v_before, (
        f"HARD GATE FAILED: mid-avl10 version changed from {mid_v_before} to {mid_v_after}. "
        "A supplier change must not version the manufactured item."
    )

    # EU PPD (different presentation, not in this run) must not be affected
    ppd_eu_v_after, _ = hapi_client.get_resource("PackagedProductDefinition", "ppd-avl10-56ct-eu")
    assert ppd_eu_v_after == ppd_eu_v_before, (
        "EU PPD version changed unexpectedly after US-only supplier change."
    )


# ── 3. Unchanged MPD and MID retain prior version on re-run ──────────────────

def test_unchanged_resources_skipped_on_rerun():
    canonicalizer.run()  # v1

    result2 = canonicalizer.run()  # rerun with no source changes
    events_by_id = {e["resource_id"]: e for e in result2["events"]}

    assert events_by_id["mpd-avl10"]["event_type"] == "SKIPPED"
    assert events_by_id["mid-avl10"]["event_type"] == "SKIPPED"
    assert events_by_id["ppd-avl10-28ct-us"]["event_type"] == "SKIPPED"

    # Version must still be 1 after two identical runs
    version, _ = hapi_client.get_resource("MedicinalProductDefinition", "mpd-avl10")
    assert version == "1"


# ── 4. New market variant reuses exact MPD ID (HARD GATE) ────────────────────

def test_new_market_reuses_exact_mpd_id():
    """
    HARD GATE: Activating a new market presentation must reuse the existing
    mpd-avl10 resource ID exactly — not create a new or duplicate MPD.
    """
    canonicalizer.run()  # establish mpd-avl10 at v1

    mpd_v_before, _ = hapi_client.get_resource("MedicinalProductDefinition", "mpd-avl10")
    assert mpd_v_before is not None

    # Activate CA market
    execute(
        "UPDATE erp_presentations SET active = TRUE WHERE presentation_id = %s",
        ("AVL10-28CT-CA",),
    )
    result = canonicalizer.run(presentation_ids=["AVL10-28CT-CA"])
    events_by_id = {e["resource_id"]: e for e in result["events"]}

    # New PPD created for CA
    assert "ppd-avl10-28ct-ca" in events_by_id
    assert events_by_id["ppd-avl10-28ct-ca"]["event_type"] == "CREATED"

    # HARD GATE: mpd-avl10 must be SKIPPED (reused), not CREATED or UPDATED
    assert events_by_id["mpd-avl10"]["event_type"] == "SKIPPED", (
        f"HARD GATE FAILED: mpd-avl10 was {events_by_id['mpd-avl10']['event_type']} "
        "when adding a new market variant. The product anchor must be reused, not re-created."
    )

    # The CA PPD must reference the exact same mpd-avl10 ID
    _, ppd_ca = hapi_client.get_resource("PackagedProductDefinition", "ppd-avl10-28ct-ca")
    assert ppd_ca is not None
    ref = ppd_ca.get("packageFor", [{}])[0].get("reference", "")
    assert ref == "MedicinalProductDefinition/mpd-avl10", (
        f"CA PPD packageFor reference is '{ref}', expected 'MedicinalProductDefinition/mpd-avl10'."
    )


# ── 5. Terminology mappings resolve deterministically ────────────────────────

def test_terminology_mappings_deterministic():
    from backend.engine.builder import build_mpd, build_mid
    from backend.sources.erp import get_product
    import json
    from pathlib import Path

    maps_dir = Path(__file__).parent.parent / "backend" / "mappings"
    dose_form_mappings = json.loads((maps_dir / "dose_form_map.json").read_text())["mappings"]
    route_mappings = json.loads((maps_dir / "route_map.json").read_text())["mappings"]

    product = get_product("AVL10")
    assert product is not None

    # Run twice — output must be identical
    r1, m1 = build_mpd(product, dose_form_mappings, route_mappings)
    r2, m2 = build_mpd(product, dose_form_mappings, route_mappings)

    assert r1 == r2
    assert m1 == m2

    # Dose form must resolve to EDQM code, not fall back to text
    dose_form = r1["combinedPharmaceuticalDoseForm"]["coding"][0]
    assert dose_form["system"] == "http://standardterms.edqm.eu"
    assert dose_form["code"] == "10219000"

    # Route must resolve to its own EDQM code
    route = r1["route"][0]["coding"][0]
    assert route["system"] == "http://standardterms.edqm.eu"
    assert route["code"] == "20053000"


# ── 6. Downstream delta contains only changed resources ──────────────────────

def test_downstream_delta_contains_only_changed_resources():
    from backend.downstream.consumer import get_inbox

    canonicalizer.run()  # v1 — all CREATED, delta delivered

    inbox_after_v1 = get_inbox(limit=1)
    assert len(inbox_after_v1) == 1
    delta = inbox_after_v1[0]
    resource_ids = delta["resource_ids"]
    # All 8 initial resources should be in the delta
    assert len(resource_ids) == 8

    # Now change only US seal supplier
    execute(
        "UPDATE plm_components SET supplier = 'BarrierSeal Systems' WHERE component_id = %s",
        ("AVL10-US-SEAL",),
    )
    canonicalizer.run(presentation_ids=["AVL10-28CT-US"])

    inbox_after_update = get_inbox(limit=1)
    latest_delta = inbox_after_update[0]
    # Only ppd-avl10-28ct-us should be in this delta
    assert latest_delta["resource_ids"] == ["ppd-avl10-28ct-us"], (
        f"Expected downstream delta to contain only ['ppd-avl10-28ct-us'], "
        f"got {latest_delta['resource_ids']}"
    )


# ── 7. Deterministic resource IDs from business keys ─────────────────────────

def test_resource_ids_are_deterministic():
    from backend.engine.builder import mpd_id, mid_id, ppd_id

    assert mpd_id("AVL10") == "mpd-avl10"
    assert mpd_id("CVX5") == "mpd-cvx5"
    assert mid_id("AVL10") == "mid-avl10"
    assert ppd_id("AVL10-28CT-US") == "ppd-avl10-28ct-us"
    assert ppd_id("CVX5-30BL-EU") == "ppd-cvx5-30bl-eu"


# ── 8. Full demo starts and produces correct summary ─────────────────────────

def test_full_run_summary_counts():
    result = canonicalizer.run()
    # 2 MPDs + 2 MIDs + 4 PPDs = 8 resources on initial run
    assert result["summary"]["created"] == 8
    assert result["summary"]["updated"] == 0
    assert result["summary"]["skipped"] == 0

    # Second identical run: all skipped
    result2 = canonicalizer.run()
    assert result2["summary"]["created"] == 0
    assert result2["summary"]["updated"] == 0
    assert result2["summary"]["skipped"] == 8


# ── 9. Closure type codes are official PQI IG codes ──────────────────────────

def test_closure_type_codes_are_official():
    """
    All closure_type_map entries must use officially published PQI IG codes.
    'Lidding Foil' was a fabricated code and must not appear.
    """
    import json
    from pathlib import Path

    maps_dir = Path(__file__).parent.parent / "backend" / "mappings"
    closure_map = json.loads((maps_dir / "closure_type_map.json").read_text())

    official_codes = {
        "Child Proof Cap",
        "Multi-layer Foil Seal Liner",
        "Blister",
        "Blister Foil Lidding",
    }
    for entry in closure_map["mappings"]:
        assert entry["code"] in official_codes, (
            f"Non-official closure type code '{entry['code']}' in closure_type_map. "
            f"Valid codes: {official_codes}"
        )
        assert entry["code"] != "Lidding Foil", (
            "Fabricated code 'Lidding Foil' must not be used — correct code is 'Blister Foil Lidding'."
        )


# ── 10. Route mapping is separate from dose form mapping ─────────────────────

def test_route_mapping_separate_from_dose_form_mapping():
    """
    Route and dose form are distinct EDQM terminology domains.
    route_map.json must exist separately; dose_form_map.json must not contain route codes.
    """
    import json
    from pathlib import Path

    maps_dir = Path(__file__).parent.parent / "backend" / "mappings"
    dose_form_map = json.loads((maps_dir / "dose_form_map.json").read_text())
    route_map = json.loads((maps_dir / "route_map.json").read_text())

    # dose_form_map must not contain "oral" (a route term)
    df_locals = {e["local"].lower() for e in dose_form_map["mappings"]}
    assert "oral" not in df_locals, (
        "'oral' found in dose_form_map — route terms must live in route_map.json only."
    )

    # route_map must exist and contain at least "oral"
    route_locals = {e["local"].lower() for e in route_map["mappings"]}
    assert "oral" in route_locals, "route_map.json is missing 'oral'"

    # MPD builder must emit route from route_map, not dose_form_map
    from backend.engine.builder import build_mpd
    from backend.sources.erp import get_product

    product = get_product("AVL10")
    r, _ = build_mpd(product, dose_form_map["mappings"], route_map["mappings"])
    route_coding = r["route"][0]["coding"][0]
    assert route_coding["system"] == "http://standardterms.edqm.eu"
    assert route_coding["code"] == "20053000", (
        f"MPD route code should be EDQM 20053000 (Oral use), got {route_coding['code']}"
    )


# ── 11. Composite material emits multiple codings ────────────────────────────

def test_composite_material_mapping_emits_multiple_material_codings():
    """
    PVC/Alu foil must produce two material codings: PolyVinylChloride + Aluminium.
    A single-coding output would silently discard one component of the composite.
    """
    from backend.engine.builder import _map_material_codings
    import json
    from pathlib import Path

    maps_dir = Path(__file__).parent.parent / "backend" / "mappings"
    material_map = json.loads((maps_dir / "material_map.json").read_text())["mappings"]

    codings = _map_material_codings("PVC/Alu foil", material_map)
    assert len(codings) == 2, (
        f"PVC/Alu foil must produce 2 codings (PVC + Aluminium), got {len(codings)}"
    )
    codes = {c["code"] for c in codings}
    assert "200000003222" in codes, "PolyVinylChloride code 200000003222 missing from composite"
    assert "200000003200" in codes, "Aluminium code 200000003200 missing from composite"


# ── 12. MarketingStatus is a structured CodeableConcept with dateRange ────────

def test_marketing_status_contains_structured_status_and_date():
    """
    PPD.marketingStatus must carry a CodeableConcept status and dateRange.start
    derived from the RIM approval_date — not a free-text string.
    """
    canonicalizer.run()

    _, ppd = hapi_client.get_resource("PackagedProductDefinition", "ppd-avl10-28ct-us")
    assert ppd is not None

    ms_list = ppd.get("marketingStatus", [])
    assert ms_list, "marketingStatus is missing from PPD"

    ms = ms_list[0]

    # Status must be a CodeableConcept with at least one coding
    status = ms.get("status", {})
    codings = status.get("coding", [])
    assert codings, "marketingStatus.status must be a CodeableConcept, not plain text"
    assert codings[0]["system"] == "http://hl7.org/fhir/publication-status"
    assert codings[0]["code"] == "active"

    # dateRange.start must be present (seeded from RIM)
    date_range = ms.get("dateRange", {})
    assert date_range.get("start"), "marketingStatus.dateRange.start must be set from RIM approval_date"


# ── 13. If-Match conflict is handled by retry (HARD GATE) ────────────────────

def test_if_match_conflict_is_handled(monkeypatch):
    """
    HARD GATE: A 412 Precondition Failed from HAPI must trigger a single retry
    without If-Match — the engine must not crash or skip the resource.
    """
    from backend.engine import hapi_client as hc

    # Establish v1 baseline
    canonicalizer.run()

    # Apply a source change to force an update
    execute(
        "UPDATE plm_components SET supplier = 'BarrierSeal Systems' WHERE component_id = %s",
        ("AVL10-US-SEAL",),
    )

    original_put = hc.put_resource
    put_calls: list[dict] = []

    def _conflicting_put(resource_type, resource_id, resource, if_match_version=None):
        put_calls.append({"resource_id": resource_id, "if_match_version": if_match_version})
        if len(put_calls) == 1 and if_match_version is not None:
            raise hc.IfMatchConflict("simulated server version conflict")
        return original_put(resource_type, resource_id, resource, if_match_version=None)

    monkeypatch.setattr(hc, "put_resource", _conflicting_put)

    result = canonicalizer.run(presentation_ids=["AVL10-28CT-US"])

    assert result["summary"]["updated"] == 1, "PPD update must succeed despite simulated 412"
    # Retry must have happened
    assert len(put_calls) == 2, f"Expected 2 PUT calls (conflict + retry), got {len(put_calls)}"
    assert put_calls[0]["if_match_version"] is not None, "First call must use If-Match"
    assert put_calls[1]["if_match_version"] is None, "Retry call must not use If-Match"


# ── 14. canonical_runs table records run lifecycle ────────────────────────────

def test_canonical_runs_record_started_and_completed():
    result = canonicalizer.run()
    run_id = result["run_id"]

    rows = query("SELECT * FROM canonical_runs WHERE run_id = %s", (run_id,))
    assert len(rows) == 1, "canonical_runs must have exactly one row per run"

    run = rows[0]
    assert run["status"] == "completed", f"Expected status='completed', got '{run['status']}'"
    assert run["started_at"] is not None
    assert run["completed_at"] is not None
    assert run["completed_at"] >= run["started_at"]

    summary = run["summary"]
    assert "created" in summary
    assert summary["created"] == result["summary"]["created"]


# ── 15. UI aggregate endpoints supply all facts the UI needs ─────────────────

def test_ui_endpoints_supply_all_business_facts_needed_by_ui():
    """
    /engine/ui/canonical-summary must return display_name for MPDs and
    market + pack_count + package_for for PPDs so the UI can render without
    additional HAPI calls.
    """
    from fastapi.testclient import TestClient
    from backend.main import app

    canonicalizer.run()
    client = TestClient(app)

    resp = client.get("/engine/ui/canonical-summary")
    assert resp.status_code == 200
    data = resp.json()

    resources = data["resources"]
    mpds = [r for r in resources if r["resource_type"] == "MedicinalProductDefinition"]
    ppds = [r for r in resources if r["resource_type"] == "PackagedProductDefinition"]

    assert mpds, "canonical-summary must include MPDs"
    assert ppds, "canonical-summary must include PPDs"

    for mpd in mpds:
        assert "display_name" in mpd, f"MPD {mpd['resource_id']} missing display_name"
        assert "product_code" in mpd, f"MPD {mpd['resource_id']} missing product_code"
        assert mpd["display_name"], "display_name must be non-empty"

    for ppd in ppds:
        assert "market" in ppd, f"PPD {ppd['resource_id']} missing market"
        assert "pack_count" in ppd, f"PPD {ppd['resource_id']} missing pack_count"
        assert "package_for" in ppd, f"PPD {ppd['resource_id']} missing package_for"
        assert ppd["pack_count"] is not None


# ── 16. No hardcoded canonical inventory in engine API ───────────────────────

def test_no_hardcoded_canonical_inventory_in_engine_api():
    """
    list_canonical() and reset_demo() must discover resources from the
    fingerprint registry — not from a hardcoded Python list.
    Guards against regression to the pre-hardening pattern.
    """
    import inspect
    from backend.api.engine import list_canonical, reset_demo

    # These known resource IDs must not appear as string literals in these two functions
    known_ids = ("mpd-avl10", "mpd-cvx5", "mid-avl10", "mid-cvx5",
                 "ppd-avl10-28ct-us", "ppd-avl10-56ct-eu")

    for fn in (list_canonical, reset_demo):
        src = inspect.getsource(fn)
        for rid in known_ids:
            assert rid not in src, (
                f"{fn.__name__} contains hardcoded resource ID '{rid}'. "
                "Use canonical_fingerprints registry instead."
            )
