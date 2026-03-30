"""
Thin HTTP client for HAPI FHIR R5.

Rules enforced here:
- All PUTs include If-Match only when we have a known version (for optimistic locking).
- GET before PUT is skipped; fingerprint cache in Postgres is the gatekeeper.
- Returns (version_id, resource_dict) or raises on non-2xx.
- IfMatchConflict is raised on 412; caller must decide whether to retry.
"""

import os
import httpx

HAPI_BASE = os.environ.get("HAPI_BASE_URL", "http://localhost:8080/fhir")
HEADERS = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}


class IfMatchConflict(Exception):
    """HAPI returned 412 Precondition Failed — server version has moved past our cached version."""


def _client() -> httpx.Client:
    return httpx.Client(base_url=HAPI_BASE, headers=HEADERS, timeout=30)


def get_resource(resource_type: str, resource_id: str) -> tuple[str | None, dict | None]:
    """Returns (version_id, resource) or (None, None) if not found."""
    with _client() as c:
        r = c.get(f"/{resource_type}/{resource_id}")
        if r.status_code == 404:
            return None, None
        r.raise_for_status()
        body = r.json()
        version = body.get("meta", {}).get("versionId")
        return version, body


def put_resource(
    resource_type: str,
    resource_id: str,
    resource: dict,
    if_match_version: str | None = None,
) -> str:
    """
    PUT resource to HAPI. Returns new versionId.

    If if_match_version is provided, sends If-Match: W/"<version>" for optimistic locking.
    Raises IfMatchConflict on 412 — caller must refresh version and retry if desired.
    """
    extra_headers = {}
    if if_match_version is not None:
        extra_headers["If-Match"] = f'W/"{if_match_version}"'
    with _client() as c:
        r = c.put(f"/{resource_type}/{resource_id}", json=resource, headers=extra_headers)
        if r.status_code == 412:
            raise IfMatchConflict(
                f"{resource_type}/{resource_id}: server has moved past version {if_match_version}"
            )
        r.raise_for_status()
        body = r.json()
        return body.get("meta", {}).get("versionId", "?")


def get_history(resource_type: str, resource_id: str) -> list[dict]:
    """Returns list of historical versions, newest first."""
    with _client() as c:
        r = c.get(f"/{resource_type}/{resource_id}/_history")
        r.raise_for_status()
        bundle = r.json()
        return [e["resource"] for e in bundle.get("entry", [])]


def get_metadata() -> dict:
    with _client() as c:
        r = c.get("/metadata")
        r.raise_for_status()
        return r.json()
