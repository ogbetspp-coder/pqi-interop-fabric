-- PQI Interoperability Fabric — seed data
-- Fictional data only. All company and supplier names are demo placeholders.
--
-- Initial state: 2 products, 4 presentations across 2 markets.
-- Flow 2 (supplier change) and Flow 3 (new market) are pre-staged but inactive.

-- ── ERP: products ─────────────────────────────────────────────────────────────

INSERT INTO erp_products VALUES
    ('AVL10', 'AVELOR',  '10 mg', 'tablet',  'oral', TRUE),
    ('CVX5',  'CORVEX',  '5 mg',  'capsule', 'oral', TRUE);

-- ── ERP: presentations ────────────────────────────────────────────────────────

INSERT INTO erp_presentations VALUES
    ('AVL10-28CT-US',  'AVL10', 'US', 28, 'tablet',  'BOTTLE',  'BOTTLE AVELOR 10MG 28 TABS, US',  TRUE),
    ('AVL10-56CT-EU',  'AVL10', 'EU', 56, 'tablet',  'BOTTLE',  'BOTTLE AVELOR 10MG 56 TABS, EU',  TRUE),
    ('CVX5-30CT-US',   'CVX5',  'US', 30, 'capsule', 'BOTTLE',  'BOTTLE CORVEX 5MG 30 CAPS, US',   TRUE),
    ('CVX5-30BL-EU',   'CVX5',  'EU', 30, 'capsule', 'BLISTER', 'BLISTER CORVEX 5MG 30 CAPS, EU',  TRUE),
    -- Flow 3 pre-staged: inactive until POST /engine/flows/3
    ('AVL10-28CT-CA',  'AVL10', 'CA', 28, 'tablet',  'BOTTLE',  'BOTTLE AVELOR 10MG 28 TABS, CA',  FALSE);

-- ── PLM: components — AVL10-28CT-US (US bottle) ──────────────────────────────

INSERT INTO plm_components VALUES
    ('AVL10-US-BOTTLE',  'AVL10-28CT-US', 'BOTTLE',                 NULL,             'High-density polyethylene (HDPE)', 'NovaCon Packaging',   'SPC-AVL-BTL-001', TRUE),
    ('AVL10-US-CAP',     'AVL10-28CT-US', 'CHILD_RESISTANT_CLOSURE','AVL10-US-BOTTLE','Polypropylene',                    'CapSafe Components',  'SPC-AVL-CAP-001', TRUE),
    ('AVL10-US-SEAL',    'AVL10-28CT-US', 'FOIL_SEAL',              'AVL10-US-CAP',   'Aluminum foil',                    'SealGuard Tech',      'SPC-AVL-SEA-001', TRUE);

-- ── PLM: components — AVL10-56CT-EU (EU bottle) ──────────────────────────────

INSERT INTO plm_components VALUES
    ('AVL10-EU-BOTTLE',  'AVL10-56CT-EU', 'BOTTLE',                 NULL,             'High-density polyethylene (HDPE)', 'EuroPack GmbH',       'SPC-AVL-BTL-002', TRUE),
    ('AVL10-EU-CAP',     'AVL10-56CT-EU', 'CHILD_RESISTANT_CLOSURE','AVL10-EU-BOTTLE','Polypropylene',                    'CapSafe Components',  'SPC-AVL-CAP-002', TRUE),
    ('AVL10-EU-SEAL',    'AVL10-56CT-EU', 'FOIL_SEAL',              'AVL10-EU-CAP',   'Aluminum foil',                    'SealGuard Tech',      'SPC-AVL-SEA-002', TRUE);

-- ── PLM: components — CVX5-30CT-US (US bottle, capsules) ─────────────────────

INSERT INTO plm_components VALUES
    ('CVX5-US-BOTTLE',   'CVX5-30CT-US',  'BOTTLE',                 NULL,             'High-density polyethylene (HDPE)', 'NovaCon Packaging',   'SPC-CVX-BTL-001', TRUE),
    ('CVX5-US-CAP',      'CVX5-30CT-US',  'CHILD_RESISTANT_CLOSURE','CVX5-US-BOTTLE', 'Polypropylene',                    'CapSafe Components',  'SPC-CVX-CAP-001', TRUE),
    ('CVX5-US-SEAL',     'CVX5-30CT-US',  'FOIL_SEAL',              'CVX5-US-CAP',    'Aluminum foil',                    'SealGuard Tech',      'SPC-CVX-SEA-001', TRUE);

-- ── PLM: components — CVX5-30BL-EU (EU blister, capsules) ───────────────────

INSERT INTO plm_components VALUES
    ('CVX5-EU-BL-BODY',  'CVX5-30BL-EU',  'BLISTER_BODY',           NULL,             'PVC/Alu foil',                     'BlisterTech Europe',  'SPC-CVX-BLB-001', TRUE),
    ('CVX5-EU-BL-LID',   'CVX5-30BL-EU',  'BLISTER_LID',            'CVX5-EU-BL-BODY','Aluminum foil',                    'BlisterTech Europe',  'SPC-CVX-BLL-001', TRUE);

-- ── PLM: components — AVL10-28CT-CA (pre-staged, inactive) ──────────────────

INSERT INTO plm_components VALUES
    ('AVL10-CA-BOTTLE',  'AVL10-28CT-CA', 'BOTTLE',                 NULL,             'High-density polyethylene (HDPE)', 'NovaCon Packaging',   'SPC-AVL-BTL-003', TRUE),
    ('AVL10-CA-CAP',     'AVL10-28CT-CA', 'CHILD_RESISTANT_CLOSURE','AVL10-CA-BOTTLE','Polypropylene',                    'CapSafe Components',  'SPC-AVL-CAP-003', TRUE),
    ('AVL10-CA-SEAL',    'AVL10-28CT-CA', 'FOIL_SEAL',              'AVL10-CA-CAP',   'Aluminum foil',                    'SealGuard Tech',      'SPC-AVL-SEA-003', TRUE);

-- ── RIM: presentations ────────────────────────────────────────────────────────

INSERT INTO rim_presentations VALUES
    ('AVL10-28CT-US', 'SUB-AVL-US-001', 'authorised', '2023-01-15', 'NDA-AVL10-US'),
    ('AVL10-56CT-EU', 'SUB-AVL-EU-001', 'authorised', '2023-03-20', 'MAA-AVL10-EU'),
    ('CVX5-30CT-US',  'SUB-CVX-US-001', 'authorised', '2023-06-01', 'NDA-CVX5-US'),
    ('CVX5-30BL-EU',  'SUB-CVX-EU-001', 'authorised', '2023-08-10', 'MAA-CVX5-EU'),
    -- Flow 3 pre-staged
    ('AVL10-28CT-CA', 'SUB-AVL-CA-001', 'authorised', '2024-02-01', 'NOC-AVL10-CA');
