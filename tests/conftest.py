"""
Test configuration.

Tests run against a live local stack (Postgres + HAPI).
Start the stack with `docker compose up -d` before running tests.

Environment variables (defaults match compose.yaml):
  DATABASE_URL     postgresql://pqi:pqi@localhost:5432/pqi_fabric
  HAPI_BASE_URL    http://localhost:8080/fhir
"""

import os
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://pqi:pqi@localhost:5432/pqi_fabric")
os.environ.setdefault("HAPI_BASE_URL", "http://localhost:8080/fhir")


@pytest.fixture(autouse=True)
def reset_engine_state():
    """Reset engine state before each test for determinism."""
    from backend.db import execute
    from backend.engine import hapi_client
    import httpx

    # Reset PLM seal supplier
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

    # Delete canonical resources from HAPI
    base = os.environ["HAPI_BASE_URL"]
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
        try:
            httpx.delete(f"{base}/{rt}/{rid}", timeout=10)
        except Exception:
            pass

    yield
