"""
Fingerprint and change-detection logic.

A fingerprint is the SHA-256 of the canonical resource dict with meta stripped.
Meta (versionId, lastUpdated) is excluded because HAPI mutates it on every PUT
and it carries no content meaning for change detection.
"""

import hashlib
import json

from backend.db import execute, query


def fingerprint(resource: dict) -> str:
    """SHA-256 of canonical resource content, meta excluded."""
    clean = {k: v for k, v in resource.items() if k != "meta"}
    serialised = json.dumps(clean, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialised.encode()).hexdigest()


def get_stored(resource_id: str) -> str | None:
    rows = query(
        "SELECT fingerprint FROM canonical_fingerprints WHERE resource_id = %s",
        (resource_id,),
    )
    return rows[0]["fingerprint"] if rows else None


def store(resource_id: str, resource_type: str, fp: str) -> None:
    execute(
        """
        INSERT INTO canonical_fingerprints (resource_id, resource_type, fingerprint, last_updated)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (resource_id) DO UPDATE
          SET fingerprint = EXCLUDED.fingerprint,
              last_updated = NOW()
        """,
        (resource_id, resource_type, fp),
    )


def has_changed(resource_id: str, resource: dict) -> bool:
    """True if resource is new or its content differs from the stored fingerprint."""
    current = fingerprint(resource)
    stored = get_stored(resource_id)
    return stored is None or stored != current
