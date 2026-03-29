# PQI Interoperability Fabric

A Phase 1 demo of controlled, near-real-time interoperability for pharmaceutical quality data.

This is not a generic FHIR demo.
It is a narrow, commercially credible proof that a canonical PQI/FHIR layer can consume structured source data from multiple fictional source systems, produce deterministic canonical output, version only the records that actually changed, and deliver validated deltas to a downstream consumer.

---

## Why this matters

Pharmaceutical product portfolios are described across multiple systems — ERP for product codes and pack counts, PLM for component suppliers and material grades, RIM for regulatory presentation identifiers. These systems agree on some things and differ on others.

When a packaging change is approved — for example, a new foil seal liner supplier — the change needs to propagate to canonical records that downstream regulatory and supply chain systems rely on. Today that often means manual re-entry, version reconciliation across spreadsheets, and free-text descriptions that different receiving systems interpret differently.

This demo shows the alternative: a canonical PQI engine that ingests structured source deltas, normalises local terms via governed mappings, versions only the impacted records, and delivers structured canonical output downstream. The product anchor stays stable. The package record versions. The downstream consumer receives a validated delta, not a string.

---

## Architecture

```
NovaPharma ERP  ──┐
PackVault PLM   ──┼──▶  PQI Engine  ──▶  HAPI FHIR R5  ──▶  GlobalRIM
ReguTrack RIM   ──┘         │
                             └──▶  Event log + downstream inbox (Postgres)
```

All source domains live as separate tables in one Postgres database.
The PQI engine runs as one FastAPI backend.
HAPI FHIR R5 is the canonical system of record.
Postgres holds source data, fingerprint cache, event log, and downstream inbox.
The Streamlit UI talks only to the backend API — never directly to HAPI.

---

## What each fictional source system owns

| System | Owns |
|---|---|
| **NovaPharma ERP** | Product code, product name, strength, dose form, route, market, pack count, packaging family |
| **PackVault PLM** | Component suppliers, material grades, approved specifications, parent/child component hierarchy |
| **ReguTrack RIM** | Approved presentation identifiers, marketing status by market, dossier references |
| **GlobalRIM** | Downstream mock consumer — receives canonical deltas, stores inbound event history |

---

## Canonical resource roles

| Resource | Role |
|---|---|
| `MedicinalProductDefinition` | Reusable product anchor. One per product code. Stable across all package variants. |
| `ManufacturedItemDefinition` | Physical item definition. One per product code. Stable. |
| `PackagedProductDefinition` | Package presentation. One per market/pack/presentation. Versions when packaging changes. |

Terminology mapping from local source terms to FHIR R5 coded concepts is driven by five JSON config files in `backend/mappings/`. These are designed in a ConceptMap-like structure and are fully inspectable from the UI.

---

## Demo flows

| Flow | What it proves |
|---|---|
| **Flow 1 — Initial canonicalization** | Run engine → 2 MPDs, 2 MIDs, 4 PPDs created in HAPI. Product anchors reused across market variants. |
| **Flow 2 — Controlled supplier change** | PLM seal supplier updated → only `ppd-avl10-28ct-us` versions. MPD and MID stay at v1. Downstream delta delivered. |
| **Flow 3 — New market variant** | CA presentation activated → new `ppd-avl10-28ct-ca` created. Existing `mpd-avl10` reused exactly. |
| **Flow 4 — Terminology normalisation** | Mappings page shows local term → FHIR code resolution for materials, closure types, dose forms. |
| **Flow 5 — Impact view** | Technical Evidence page shows which source rows fed each resource, which mappings were applied, and why unchanged resources were skipped. |

---

## Deterministic IDs

Resource IDs are fully deterministic from business keys:

| Pattern | Example |
|---|---|
| `mpd-{product_code_lower}` | `mpd-avl10` |
| `mid-{product_code_lower}` | `mid-avl10` |
| `ppd-{presentation_id_lower}` | `ppd-avl10-28ct-us` |

This is essential for stable upsert behaviour and clean version history.

---

## How to run locally

Requirements: Docker, Docker Compose.

```bash
git clone <repo-url>
cd pqi-interop-fabric
chmod +x seed.sh
./seed.sh
```

This starts all services and runs the initial canonicalization.
Open `http://localhost:8501` to view the demo.

Individual commands:
```bash
docker compose up -d          # start all services
docker compose down           # stop all services
docker compose logs backend   # backend logs
docker compose logs hapi      # HAPI logs
```

Run tests (requires running stack):
```bash
pip install pytest httpx psycopg2-binary pydantic httpx
pytest tests/ -v
```

---

## Service ports

| Service | Port |
|---|---|
| Streamlit UI | `http://localhost:8501` |
| FastAPI backend | `http://localhost:8000` |
| HAPI FHIR R5 | `http://localhost:8080/fhir` |
| Postgres | `localhost:5432` |

---

## Technical compromises in Phase 1

1. **Single backend process.** All source domains, engine, events, and downstream consumer run in one FastAPI process. Service separation is intentionally deferred to Phase 2 once flows are proven.

2. **Outbox polling model.** The downstream consumer reads from a Postgres table. There is no push-based eventing. This is honest and explicit — the README and UI both use the phrase "near-real-time controlled propagation."

3. **HAPI topic-based subscriptions not used.** A clean outbox + delta model is simpler and equally demonstrable for this scope.

4. **No authentication.** This is a local demo stack. Do not expose it publicly.

5. **HAPI uses in-memory H2 storage.** Data is lost on container restart. Persistent volume can be added trivially if needed.
