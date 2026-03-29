# Presenter Demo Script

## Setup (before the meeting)

```bash
./seed.sh
```

Wait for: `Done. Open http://localhost:8501`

Open `http://localhost:8501` in a browser. Keep `http://localhost:8000/docs` open in a second tab for technical questions.

---

## Flow 1 — The canonical model (3 minutes)

**Navigate to:** Why This Matters

Say: "We have two fictional products and four packaged presentations across two markets. Three separate source systems each own a different slice of that information. The canonical engine pulls those slices together, normalises the terminology, and produces one versioned record per resource."

**Navigate to:** Source Systems

Show each tab briefly. Point out that NovaPharma ERP owns pack counts and markets, PackVault PLM owns supplier names, ReguTrack RIM owns regulatory presentation IDs. No single system owns everything.

**Navigate to:** Canonical Model

Show the product anchor count (2) and package record count (4). Point out: "Both AVELOR presentations — US and EU — share the same product anchor. That anchor stays stable. The package records are where the market-specific detail lives."

---

## Flow 2 — Controlled supplier change (3 minutes)

**Navigate to:** Controlled Change

Say: "In PackVault PLM, the approved supplier for the foil seal liner on the US bottle just changed. Watch what happens."

Click **Flow 2: Supplier change**.

Point to the before/after: SealGuard Tech → BarrierSeal Systems.

Point to the versioned/skipped breakdown: "One package record versioned. The product anchor and manufactured item were skipped — no spurious version bumps."

**Navigate to:** Downstream Impact

Show the inbox entry. "GlobalRIM received a canonical delta. It contains only the impacted package record, the old and new version numbers, and the market. It does not contain the source supplier string. The receiving system does not need to parse anything."

---

## Flow 3 — New market variant (2 minutes)

**Navigate to:** Controlled Change

Click **Flow 3: New market (CA)**.

**Navigate to:** Canonical Model

Show that `ppd-avl10-28ct-ca` now appears, pointing to the same `mpd-avl10` product anchor. "One new package record created. The product anchor was reused exactly — no duplication."

---

## Flow 4 — Terminology normalisation (1 minute)

**Navigate to:** Technical Evidence → Mappings

Show `material_map`: "High-density polyethylene (HDPE)" → FHIR code `200000003215`. Show `closure_type_map`: "FOIL_SEAL" → "Multi-layer Foil Seal Liner". Show `dose_form_map`: "tablet" → EDQM `10219000`.

Say: "Every mapping is explicit, inspectable, and config-driven. Nothing is resolved by guessing."

---

## Flow 5 — Impact view (1 minute)

**Navigate to:** Technical Evidence → Resource History

Enter `ppd-avl10-28ct-us`. Show version history (version 1 and version 2 after Flow 2). Show the provenance trace: which PLM rows fed it, which mappings were applied.

Enter `mpd-avl10`. Show version history: only version 1 — no spurious bumps from either supplier change or new market.

---

## Closing message

"The commercial argument is not that we can parse a text string. It is that a small number of product anchors — two here — can support many package variants across many markets, with controlled versioning and validated canonical output that downstream systems can consume without re-interpretation. That is the pattern that scales."

---

## If asked about real-time

"The current implementation uses a controlled propagation model — source change triggers engine run triggers downstream delta. We have not built push-based eventing in Phase 1 because outbox-style propagation is sufficient to prove the canonical versioning thesis. Push eventing is an addition, not a redesign."

## If asked about AI / LLMs

"There are no LLM calls in this stack. Every mapping is explicit config. Every ID is deterministic. The value is in the canonical structure and the versioning discipline — not in any parsing capability."
