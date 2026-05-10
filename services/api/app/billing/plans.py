"""Plan-feature resolver — reads from tenant's synced license cache.

The source of truth for plan-feature values has moved to the platform DB
(plan_features table). The platform service embeds the merged feature map
(plan features + per-tenant overrides) in the LicenseResponse as
`plan_features: dict[str, Any]`. The IMS license sync writes this into
`TenantLicenseCache.plan_features`.

`resolve_plan_value` reads from that cache. If no cache row exists (e.g.
tenant has never synced), it falls back to `resolve_default` from the
feature catalog.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.features import resolve_default


def resolve_plan_value(db: Session, tenant_id: UUID, feature_key: str) -> Any:
    """Resolve a feature value for a tenant from the synced license cache.

    Falls back to the feature catalog default when no cache exists or the
    feature key is absent from the cached plan_features map.
    """
    # Import here to avoid circular imports (models → billing → models)
    from app.models.tables import TenantLicenseCache

    cache = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)
    ).scalar_one_or_none()

    if cache is not None and cache.plan_features and feature_key in cache.plan_features:
        return cache.plan_features[feature_key]

    return resolve_default(feature_key)
