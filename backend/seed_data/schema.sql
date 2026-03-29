-- PQI Interoperability Fabric — database schema
-- Three fictional source domains + engine support tables

-- ── NovaPharma ERP ───────────────────────────────────────────────────────────

CREATE TABLE erp_products (
    product_code        TEXT PRIMARY KEY,
    product_name        TEXT NOT NULL,
    strength            TEXT NOT NULL,
    dose_form           TEXT NOT NULL,   -- local term, e.g. "tablet", "capsule"
    route               TEXT NOT NULL,   -- local term, e.g. "oral"
    active              BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE erp_presentations (
    presentation_id     TEXT PRIMARY KEY,  -- e.g. AVL10-28CT-US
    product_code        TEXT NOT NULL REFERENCES erp_products(product_code),
    market              TEXT NOT NULL,     -- US, EU, CA
    pack_count          INTEGER NOT NULL,
    pack_unit           TEXT NOT NULL,     -- tablet, capsule
    packaging_family    TEXT NOT NULL,     -- BOTTLE, BLISTER
    local_packaging_text TEXT,
    active              BOOLEAN NOT NULL DEFAULT TRUE
);

-- ── PackVault PLM ─────────────────────────────────────────────────────────────

CREATE TABLE plm_components (
    component_id        TEXT PRIMARY KEY,  -- e.g. AVL10-US-BOTTLE
    presentation_id     TEXT NOT NULL,     -- matches erp_presentations
    component_type      TEXT NOT NULL,     -- BOTTLE, CHILD_RESISTANT_CLOSURE, FOIL_SEAL, BLISTER_BODY, BLISTER_LID
    parent_component_id TEXT,              -- NULL for root; closure/seal point to bottle
    material_local      TEXT NOT NULL,     -- local material text before mapping
    supplier            TEXT NOT NULL,
    spec_reference      TEXT,
    active              BOOLEAN NOT NULL DEFAULT TRUE
);

-- ── ReguTrack RIM ─────────────────────────────────────────────────────────────

CREATE TABLE rim_presentations (
    presentation_id     TEXT PRIMARY KEY,  -- matches erp_presentations
    submission_id       TEXT,
    marketing_status    TEXT NOT NULL DEFAULT 'authorised',
    approval_date       TEXT,
    dossier_reference   TEXT
);

-- ── Engine support tables ─────────────────────────────────────────────────────

-- Content fingerprints — Postgres holds this cache; HAPI holds canonical truth
CREATE TABLE canonical_fingerprints (
    resource_id         TEXT PRIMARY KEY,
    resource_type       TEXT NOT NULL,
    fingerprint         TEXT NOT NULL,
    last_updated        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Full event history for every engine run
CREATE TABLE canonical_events (
    event_id            TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL,
    event_type          TEXT NOT NULL,   -- CREATED, UPDATED, SKIPPED
    resource_type       TEXT NOT NULL,
    resource_id         TEXT NOT NULL,
    old_version         TEXT,
    new_version         TEXT,
    change_summary      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Per-resource trace: which source rows fed it, which mappings were applied
CREATE TABLE canonical_run_traces (
    trace_id            TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL,
    resource_id         TEXT NOT NULL,
    resource_type       TEXT NOT NULL,
    source_rows         JSONB NOT NULL DEFAULT '{}',
    mappings_applied    JSONB NOT NULL DEFAULT '[]',
    fingerprint_before  TEXT,
    fingerprint_after   TEXT NOT NULL,
    action              TEXT NOT NULL,  -- CREATED, UPDATED, SKIPPED
    reason              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Downstream GlobalRIM mock consumer inbox
CREATE TABLE downstream_inbox (
    inbox_id            TEXT PRIMARY KEY,
    event_id            TEXT NOT NULL,
    run_id              TEXT NOT NULL,
    payload             JSONB NOT NULL,
    resource_ids        JSONB NOT NULL DEFAULT '[]',
    old_versions        JSONB NOT NULL DEFAULT '{}',
    new_versions        JSONB NOT NULL DEFAULT '{}',
    markets             JSONB NOT NULL DEFAULT '[]',
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_status   TEXT NOT NULL DEFAULT 'received'
);
