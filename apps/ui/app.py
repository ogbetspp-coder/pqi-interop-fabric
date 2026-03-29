"""
PQI Interoperability Fabric — business demo UI.

All business facts come from the backend API.
No hardcoded version numbers, supplier names, or resource counts.
"""

import os
import httpx
import streamlit as st

BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000")


# ── backend helpers ───────────────────────────────────────────────────────────

def _get(path: str) -> dict | list | None:
    try:
        r = httpx.get(f"{BACKEND}{path}", timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _post(path: str) -> dict | None:
    try:
        r = httpx.post(f"{BACKEND}{path}", timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Request failed: {e}")
        return None


def _backend_ok() -> bool:
    result = _get("/health")
    return result is not None and result.get("status") == "ok"


# ── page setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PQI Interoperability Fabric",
    layout="wide",
    initial_sidebar_state="expanded",
)

page = st.sidebar.radio(
    "Navigation",
    ["Why This Matters", "Source Systems", "Canonical Model",
     "Controlled Change", "Downstream Impact", "Technical Evidence"],
)

if not _backend_ok():
    st.error(
        "Backend not reachable. Run `docker compose up -d` and wait for all services to start, "
        "then reload this page."
    )
    st.stop()

# ── page: Why This Matters ────────────────────────────────────────────────────

if page == "Why This Matters":
    st.title("PQI Interoperability Fabric")
    st.markdown(
        "A pharmaceutical product portfolio is described by multiple source systems — "
        "ERP, packaging data, and regulatory records — each owning different slices of meaning. "
        "When those systems disagree, or when a change in one system has to propagate to others, "
        "the result is manual re-entry, ambiguity, and audit risk."
    )
    st.markdown(
        "This demo shows a different pattern: a **canonical PQI/FHIR layer** that pulls meaning "
        "from each source domain, normalises it using governed mappings, and persists a single "
        "reusable canonical record per resource. When a source changes, only the affected "
        "canonical records are versioned. Downstream systems receive a validated delta — "
        "not a free-text string to reinterpret."
    )
    st.divider()

    c1, c2, c3 = st.columns(3)
    c1.markdown("**One source of canonical truth**\n\nThree source systems feed one canonical engine. Each source owns what it knows.")
    c2.markdown("**Controlled versioning**\n\nA packaging change versions only the packaging record. Product anchors and item definitions stay stable.")
    c3.markdown("**Downstream-ready deltas**\n\nThe downstream consumer receives structured, validated canonical output — not raw source text.")

    st.divider()
    st.markdown("**Demo product portfolio**")

    products = _get("/sources/erp/products") or []
    presentations = _get("/sources/erp/presentations") or []
    if products:
        c1, c2 = st.columns(2)
        c1.metric("Product anchors", len(products))
        c2.metric("Active package presentations", len(presentations))
        for p in products:
            pres_for = [x for x in presentations if x["product_code"] == p["product_code"]]
            markets = sorted({x["market"] for x in pres_for})
            st.markdown(f"- **{p['product_name']} {p['strength']} {p['dose_form']}** "
                        f"({p['product_code']}) · {len(pres_for)} presentation(s) · markets: {', '.join(markets)}")

# ── page: Source Systems ──────────────────────────────────────────────────────

elif page == "Source Systems":
    st.title("Source Systems")
    st.markdown(
        "Three fictional source systems contribute complementary data slices. "
        "Each system owns what it knows — no system tries to own everything."
    )

    tab_erp, tab_plm, tab_rim = st.tabs(["NovaPharma ERP", "PackVault PLM", "ReguTrack RIM"])

    with tab_erp:
        st.markdown("**Owns:** product codes, markets, pack counts, packaging families")
        products = _get("/sources/erp/products") or []
        presentations = _get("/sources/erp/presentations") or []
        if products:
            st.markdown("*Products*")
            st.dataframe(
                [{"Code": p["product_code"], "Name": p["product_name"],
                  "Strength": p["strength"], "Dose form": p["dose_form"],
                  "Route": p["route"]} for p in products],
                use_container_width=True, hide_index=True,
            )
        if presentations:
            st.markdown("*Active presentations*")
            st.dataframe(
                [{"ID": p["presentation_id"], "Product": p["product_code"],
                  "Market": p["market"], "Count": p["pack_count"],
                  "Unit": p["pack_unit"], "Family": p["packaging_family"]} for p in presentations],
                use_container_width=True, hide_index=True,
            )

    with tab_plm:
        st.markdown("**Owns:** component suppliers, material grades, approved specifications")
        components = _get("/sources/plm/components") or []
        if components:
            st.dataframe(
                [{"ID": c["component_id"], "Presentation": c["presentation_id"],
                  "Type": c["component_type"], "Material": c["material_local"],
                  "Supplier": c["supplier"], "Spec": c["spec_reference"]} for c in components],
                use_container_width=True, hide_index=True,
            )

    with tab_rim:
        st.markdown("**Owns:** approved presentation identifiers, marketing status by market")
        rim = _get("/sources/rim/presentations") or []
        if rim:
            st.dataframe(
                [{"ID": r["presentation_id"], "Status": r["marketing_status"],
                  "Submission": r["submission_id"], "Approved": r["approval_date"],
                  "Dossier": r["dossier_reference"]} for r in rim],
                use_container_width=True, hide_index=True,
            )

# ── page: Canonical Model ─────────────────────────────────────────────────────

elif page == "Canonical Model":
    st.title("Canonical Package Model")
    st.markdown(
        "The PQI engine normalises source data into FHIR R5 canonical records. "
        "Product anchors are reused across all package variants. "
        "Each package record points back to one stable product anchor."
    )

    canonical = _get("/engine/canonical") or []
    if not canonical:
        st.info("No canonical records loaded yet. Run the engine from the Controlled Change page.")
        st.stop()

    mpds = [r for r in canonical if r["resource_type"] == "MedicinalProductDefinition"]
    mids = [r for r in canonical if r["resource_type"] == "ManufacturedItemDefinition"]
    ppds = [r for r in canonical if r["resource_type"] == "PackagedProductDefinition"]

    m1, m2, m3 = st.columns(3)
    m1.metric("Product anchors (MPD)", len(mpds))
    m2.metric("Manufactured items (MID)", len(mids))
    m3.metric("Package records (PPD)", len(ppds))

    st.markdown("**Product anchors — reusable across all variants**")
    for mpd in mpds:
        resource = _get(f"/engine/canonical/MedicinalProductDefinition/{mpd['resource_id']}")
        if resource:
            name = resource.get("name", [{}])[0].get("productName", mpd["resource_id"])
            pcode = resource.get("identifier", [{}])[0].get("value", "")
            st.markdown(f"- **{name}** (`{mpd['resource_id']}`) · product code: {pcode} · version: {mpd['version']}")

    st.divider()
    st.markdown("**Package records — one per market/presentation**")
    rows = []
    for ppd in ppds:
        resource = _get(f"/engine/canonical/PackagedProductDefinition/{ppd['resource_id']}")
        if resource:
            market = ""
            for ms in resource.get("marketingStatus", []):
                for coding in ms.get("country", {}).get("coding", []):
                    market = coding.get("code", "")
            qty = resource.get("containedItemQuantity", [{}])[0]
            rows.append({
                "ID": ppd["resource_id"],
                "Market": market,
                "Count": f"{qty.get('value', '')} {qty.get('unit', '')}",
                "Product anchor": resource.get("packageFor", [{}])[0].get("reference", "").split("/")[-1],
                "Version": ppd["version"],
                "Last updated": ppd["last_updated"],
            })
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()
    with st.expander("Technical detail — raw FHIR JSON for any resource"):
        rid = st.text_input("Resource ID (e.g. ppd-avl10-28ct-us)")
        rtype = st.selectbox("Resource type", ["PackagedProductDefinition", "MedicinalProductDefinition", "ManufacturedItemDefinition"])
        if rid:
            r = _get(f"/engine/canonical/{rtype}/{rid}")
            if r:
                st.json(r)
            else:
                st.warning("Not found.")

# ── page: Controlled Change ───────────────────────────────────────────────────

elif page == "Controlled Change":
    st.title("Controlled Change")
    st.markdown(
        "A supplier change in PackVault PLM propagates through the canonical engine. "
        "Only the affected package record is versioned. Unchanged records are skipped."
    )

    col_run, col_f2, col_f3, col_reset = st.columns(4)

    with col_run:
        if st.button("Run engine (full)", use_container_width=True):
            with st.spinner("Running canonicalization..."):
                result = _post("/engine/run")
            if result:
                st.success(f"Run `{result['run_id'][:8]}...` · "
                           f"created: {result['summary']['created']} · "
                           f"updated: {result['summary']['updated']} · "
                           f"skipped: {result['summary']['skipped']}")
                st.session_state["last_run"] = result

    with col_f2:
        if st.button("Flow 2: Supplier change", use_container_width=True):
            with st.spinner("Applying supplier change..."):
                result = _post("/engine/flows/2")
            if result:
                st.success(f"Supplier: **{result['supplier_before']}** → **{result['supplier_after']}**")
                st.session_state["last_run"] = result
                st.session_state["flow2_result"] = result

    with col_f3:
        if st.button("Flow 3: New market (CA)", use_container_width=True):
            with st.spinner("Activating CA market..."):
                result = _post("/engine/flows/3")
            if result:
                st.success(f"Activated: {result.get('activated_presentation')}")
                st.session_state["last_run"] = result

    with col_reset:
        if st.button("Reset demo", use_container_width=True, type="secondary"):
            with st.spinner("Resetting..."):
                result = _post("/engine/reset")
            if result:
                st.info("Demo reset to initial state.")
                st.session_state.pop("last_run", None)
                st.session_state.pop("flow2_result", None)

    # Show before/after for Flow 2 if available
    if "flow2_result" in st.session_state:
        r = st.session_state["flow2_result"]
        st.divider()
        st.markdown("**Flow 2 result — controlled supplier change**")
        c1, c2 = st.columns(2)
        c1.info(f"Before\n\n**{r['supplier_before']}**")
        c2.success(f"After\n\n**{r['supplier_after']}**")

        events = r.get("events", [])
        updated = [e for e in events if e["event_type"] == "UPDATED"]
        skipped = [e for e in events if e["event_type"] == "SKIPPED"]

        st.markdown(f"**Versioned:** {len(updated)} record(s)")
        for e in updated:
            st.markdown(f"- `{e['resource_id']}` ({e['resource_type']}) "
                        f"v{e['old_version']} → v{e['new_version']} · {e['change_summary']}")

        st.markdown(f"**Unchanged (skipped):** {len(skipped)} record(s)")
        for e in skipped:
            st.markdown(f"- `{e['resource_id']}` ({e['resource_type']}) stayed at v{e['old_version']}")

    # Show last run events if available
    elif "last_run" in st.session_state:
        r = st.session_state["last_run"]
        st.divider()
        st.markdown(f"**Last run:** `{r['run_id'][:8]}...`")
        for e in r.get("events", []):
            icon = "🟢" if e["event_type"] == "CREATED" else ("🔵" if e["event_type"] == "UPDATED" else "⚪")
            st.markdown(f"{icon} `{e['resource_id']}` — **{e['event_type']}** "
                        f"v{e.get('old_version', '–')} → v{e.get('new_version', '–')}")

# ── page: Downstream Impact ───────────────────────────────────────────────────

elif page == "Downstream Impact":
    st.title("Downstream Impact — GlobalRIM")
    st.markdown(
        "The GlobalRIM downstream consumer receives validated canonical deltas from the engine. "
        "It does not parse source text. It receives structured, versioned canonical output."
    )

    inbox = _get("/downstream/inbox") or []
    if not inbox:
        st.info("No downstream events yet. Run the engine from the Controlled Change page.")
    else:
        st.metric("Inbox items", len(inbox))
        for item in inbox:
            with st.expander(
                f"Run `{item['run_id'][:8]}...` · "
                f"resources: {len(item['resource_ids'])} · "
                f"markets: {', '.join(item['markets'])} · "
                f"{item['received_at'][:19].replace('T', ' ')}"
            ):
                c1, c2 = st.columns(2)
                c1.markdown("**Impacted resources**")
                for rid in item["resource_ids"]:
                    old_v = item["old_versions"].get(rid, "–")
                    new_v = item["new_versions"].get(rid, "–")
                    c1.markdown(f"- `{rid}` · v{old_v} → v{new_v}")

                c2.markdown(f"**Status:** {item['processing_status']}")
                c2.markdown(f"**Markets:** {', '.join(item['markets'])}")
                c2.markdown(f"**Received:** {item['received_at'][:19].replace('T', ' ')}")

                with st.expander("Raw canonical delta payload"):
                    st.json(item["payload"])

# ── page: Technical Evidence ──────────────────────────────────────────────────

elif page == "Technical Evidence":
    st.title("Technical Evidence")

    tab_hapi, tab_history, tab_maps, tab_events = st.tabs(
        ["FHIR Server", "Resource History", "Mappings", "Event Log"]
    )

    with tab_hapi:
        meta = _get("/fhir/metadata")
        if meta:
            sw = meta.get("software", {})
            st.success(
                f"HAPI FHIR online · version {meta.get('fhirVersion')} · "
                f"{sw.get('name')} {sw.get('version')}"
            )
            with st.expander("Raw /metadata"):
                st.json(meta)
        else:
            st.error("FHIR metadata not reachable.")

    with tab_history:
        st.markdown("Select a resource to see its version history.")
        rt = st.selectbox("Resource type", ["PackagedProductDefinition", "MedicinalProductDefinition", "ManufacturedItemDefinition"])
        rid = st.text_input("Resource ID", value="ppd-avl10-28ct-us")
        if rid:
            history = _get(f"/engine/canonical/{rt}/{rid}/history")
            if history:
                st.dataframe(history, use_container_width=True, hide_index=True)
            else:
                st.info("No history found — run the engine first.")

            trace = _get(f"/engine/trace/{rid}")
            if trace:
                st.markdown("**Latest provenance trace**")
                st.markdown(f"- Action: **{trace['action']}** · Reason: {trace['reason']}")
                st.markdown(f"- Fingerprint before: `{(trace.get('fingerprint_before') or 'none')[:16]}...`")
                st.markdown(f"- Fingerprint after: `{trace['fingerprint_after'][:16]}...`")
                with st.expander("Source rows that fed this resource"):
                    st.json(trace["source_rows"])
                with st.expander("Mappings applied"):
                    st.json(trace["mappings_applied"])

    with tab_maps:
        st.markdown("Explicit local-to-canonical term mappings. Config-driven, not hardcoded in engine.")
        maps = _get("/engine/mappings") or {}
        for name, content in maps.items():
            with st.expander(f"{name} — {content.get('description', '')}"):
                entries = content.get("mappings") or content.get("rules") or []
                st.dataframe(entries, use_container_width=True, hide_index=True)

    with tab_events:
        st.markdown("Full event log from the engine.")
        events = _get("/events/") or []
        if events:
            st.dataframe(
                [{"Type": e["event_type"], "Resource": e["resource_id"],
                  "Kind": e["resource_type"].replace("Definition", ""),
                  "v_before": e.get("old_version"), "v_after": e.get("new_version"),
                  "Summary": e.get("change_summary", "")[:60],
                  "When": e["created_at"][:19].replace("T", " ")} for e in events],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No events yet.")
