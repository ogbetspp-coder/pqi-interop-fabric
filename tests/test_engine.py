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

    dose_form_mappings = json.loads(
        ((__import__("pathlib").Path(__file__).parent.parent / "backend" / "mappings" / "dose_form_map.json")).read_text()
    )["mappings"]

    product = get_product("AVL10")
    assert product is not None

    # Run twice — output must be identical
    r1, m1 = build_mpd(product, dose_form_mappings)
    r2, m2 = build_mpd(product, dose_form_mappings)

    assert r1 == r2
    assert m1 == m2

    # Dose form must resolve to EDQM code, not fall back to text
    dose_form = r1["combinedPharmaceuticalDoseForm"]["coding"][0]
    assert dose_form["system"] == "http://standardterms.edqm.eu"
    assert dose_form["code"] == "10219000"


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
