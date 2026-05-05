"""Entitlements resolver — merges catalog defaults, plan values, and tenant overrides.

Resolution order (later sources override earlier):
    1. Catalog default (from features.py)
    2. Plan-codename value (from plans.py)
    3. Per-tenant override (from tenant_feature_overrides table; expired rows ignored)

Use ``resolve_for_tenant`` in tests and service code; in route handlers, prefer
the FastAPI dependency ``EntitlementsDep`` from billing.deps (Task 5).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.features import (
    FEATURE_CATALOG,
    FeatureDefinition,
    ValueType,
    get_definition,
    resolve_default,
)
from app.billing.plans import resolve_plan_value
from app.models import TenantFeatureOverride


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
        """For boolean features. Raises if the feature is not boolean."""
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
        """Raise 403 if a boolean feature is off. No-op if on."""
        d = get_definition(key)
        if d is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"unknown feature {key!r}",
            )
        if d.value_type is ValueType.BOOL and not self.has(key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "plan_upgrade_required",
                    "required_feature": key,
                    "current_plan": self.plan_codename,
                },
            )

    def to_dict(self) -> dict[str, Any]:
        # Materialize all known keys (defaults + plan + overrides)
        out: dict[str, Any] = {}
        for f in FEATURE_CATALOG:
            out[f.key] = self.get(f.key)
        return out


def _load_overrides(db: Session, tenant_id: UUID) -> dict[str, Any]:
    """Load active (non-expired) per-tenant overrides keyed by feature_key."""
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


def resolve_for_tenant(db: Session, tenant_id: UUID, plan_codename: str) -> Entitlements:
    """Resolve entitlements for a tenant. Returns a typed ``Entitlements`` view.

    Order: catalog default -> plan value -> override.
    """
    values: dict[str, Any] = {}

    # 1. Plan values (only for keys the plan explicitly sets; resolve_plan_value
    #    handles fallback to default per-key on .get(), so we materialize the
    #    full catalog here for cache stability)
    for f in FEATURE_CATALOG:
        values[f.key] = resolve_plan_value(plan_codename, f.key)

    # 2. Active per-tenant overrides
    overrides = _load_overrides(db, tenant_id)
    values.update(overrides)

    return Entitlements.from_values(plan_codename, values)
