"""Entitlements resolver — merges catalog defaults, plan values, and tenant overrides.

Resolution order (later sources override earlier):
    1. Catalog default (from features.py)
    2. Plan-codename value (from plans.py)
    3. Per-tenant override (from tenant_feature_overrides table; expired rows ignored)

Use ``resolve_for_tenant`` in tests and service code; in route handlers, prefer
the FastAPI dependency ``EntitlementsDep`` from billing.deps (Task 5).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.features import (
    FEATURE_CATALOG,
    ValueType,
    get_definition,
    resolve_default,
)
from app.billing.plans import resolve_plan_value
from app.models import TenantFeatureOverride
from app.worker.queue import redis_conn

logger = logging.getLogger(__name__)

CACHE_PREFIX = "ents:v1"
CACHE_TTL_SECONDS = 300  # 5 minutes — invalidations on write keep this tighter


class Entitlements:
    """Resolved entitlements for a single tenant.

    Construct via ``resolve_for_tenant`` or ``Entitlements.from_values``.
    """

    def __init__(self, plan_codename: str, values: dict[str, Any]) -> None:
        self.plan_codename = plan_codename
        self._values = values

    @classmethod
    def from_values(cls, plan_codename: str, values: dict[str, Any]) -> "Entitlements":
        return cls(plan_codename, values)

    def get(self, key: str) -> Any:
        if key in self._values:
            return self._values[key]
        return resolve_default(key)

    def has(self, key: str) -> bool:
        """For boolean features. Returns False for unknown feature keys (silent —
        use ``get_definition()`` if you need to detect unknowns). Raises ValueError
        if the feature exists but is not boolean."""
        d = get_definition(key)
        if d is None:
            return False
        if d.value_type is not ValueType.BOOL:
            raise ValueError(f"has() called on non-boolean feature {key!r}")
        return bool(self.get(key))

    def limit(self, key: str) -> int:
        """For numeric limits. Raises if the feature is not numeric."""
        d = get_definition(key)
        if d is None:
            raise ValueError(f"unknown feature key {key!r}")
        if d.value_type is not ValueType.NUMERIC:
            raise ValueError(f"limit() called on non-numeric feature {key!r}")
        return int(self.get(key))

    def require(self, key: str) -> None:
        """Raise 403 if a boolean feature is off. No-op if on. Raises ValueError
        if used on a non-boolean feature (use ``limit()`` for numeric limits)."""
        d = get_definition(key)
        if d is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"unknown feature {key!r}",
            )
        if d.value_type is not ValueType.BOOL:
            raise ValueError(
                f"require() is for boolean features; {key!r} is {d.value_type.value}. "
                f"Use limit() for numeric features."
            )
        if not self.has(key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "plan_upgrade_required",
                    "required_feature": key,
                    "current_plan": self.plan_codename,
                },
            )

    def to_dict(self) -> dict[str, Any]:
        """Materialize the catalog-restricted view of all known features.

        Iterates ``FEATURE_CATALOG`` only — keys present in ``_values`` but not in
        the catalog (i.e. catalog-orphan overrides) are NOT included. For a
        lossless serialization (e.g. cache writes) use ``to_cache_payload()``.
        """
        out: dict[str, Any] = {}
        for f in FEATURE_CATALOG:
            out[f.key] = self.get(f.key)
        return out

    def to_cache_payload(self) -> dict[str, Any]:
        """Lossless serialization helper for cache writers. Returns the full
        `_values` dict plus `plan_codename` so ``Entitlements.from_values`` can
        reconstruct an equivalent instance. Includes catalog-orphan overrides
        (unlike ``to_dict()``)."""
        return {"plan_codename": self.plan_codename, "values": dict(self._values)}


def _load_overrides(db: Session, tenant_id: UUID) -> dict[str, Any]:
    """Load active (non-expired) per-tenant overrides keyed by feature_key."""
    # Per-tenant overrides are expected to be sparse (O(10s) rows max), so
    # we filter expired rows in Python rather than the WHERE clause. If the
    # row count grows large, push the filter into SQL.
    now = datetime.now(UTC)
    rows = db.execute(
        select(TenantFeatureOverride).where(TenantFeatureOverride.tenant_id == tenant_id)
    ).scalars().all()
    out: dict[str, Any] = {}
    for r in rows:
        if r.expires_at is not None and r.expires_at <= now:
            continue
        out[r.feature_key] = r.value
    return out


def _cache_key(tenant_id: UUID, plan_codename: str) -> str:
    return f"{CACHE_PREFIX}:{tenant_id}:{plan_codename}"


def resolve_for_tenant(db: Session, tenant_id: UUID, plan_codename: str) -> Entitlements:
    """Resolve entitlements for a tenant. Cache-aware.

    Cache hits skip DB. Misses load overrides + merge, then write through.
    Cache invalidation is the writer's responsibility — see ``invalidate_cache``.
    """
    cached = _read_cache(tenant_id, plan_codename)
    if cached is not None:
        return cached

    values: dict[str, Any] = {}
    for f in FEATURE_CATALOG:
        values[f.key] = resolve_plan_value(plan_codename, f.key)

    overrides = _load_overrides(db, tenant_id)
    values.update(overrides)

    ents = Entitlements.from_values(plan_codename, values)
    _write_cache(tenant_id, plan_codename, ents)
    return ents


def invalidate_cache(tenant_id: UUID) -> None:
    """Drop all cached entitlement entries for a tenant.

    Call this from any code path that writes a tenant_feature_overrides row.
    """
    try:
        r = redis_conn()
        keys = list(r.scan_iter(f"{CACHE_PREFIX}:{tenant_id}:*"))
        if keys:
            r.delete(*keys)
    except Exception:
        logger.warning("Failed to invalidate entitlement cache for %s", tenant_id, exc_info=True)


def _read_cache(tenant_id: UUID, plan_codename: str) -> Entitlements | None:
    try:
        raw = redis_conn().get(_cache_key(tenant_id, plan_codename))
        if raw is None:
            return None
        payload = json.loads(raw)
        return Entitlements.from_values(payload["plan_codename"], payload["values"])
    except Exception:
        logger.warning("Entitlement cache read failed for %s/%s", tenant_id, plan_codename, exc_info=True)
        return None


def _write_cache(tenant_id: UUID, plan_codename: str, ents: Entitlements) -> None:
    """Write cache entry. Uses to_cache_payload() to avoid private attribute access."""
    try:
        payload = json.dumps(ents.to_cache_payload())
        redis_conn().setex(_cache_key(tenant_id, plan_codename), CACHE_TTL_SECONDS, payload)
    except Exception:
        logger.warning("Entitlement cache write failed for %s/%s", tenant_id, plan_codename, exc_info=True)
