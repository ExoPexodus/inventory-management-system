from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import Tenant, TenantFeatureOverride, TenantLicenseCache

# Pro plan features — mirrors the PLAN_FEATURES["pro"] dict from the old plans.py.
# These are seeded into TenantLicenseCache.plan_features so resolve_plan_value
# reads from the DB cache rather than a now-deleted hardcoded constant.
PRO_FEATURES = {
    "max_channels": 5,
    "shopify_connector": True,
    "woocommerce_connector": True,
    "headless_api": True,
    "hosted_checkout": True,
    "byo_stripe": True,
    "byo_razorpay": True,
    "byo_paypal": True,
    "max_products": 5000,
    "multi_currency_advanced": True,
    "email_volume_per_month": 10000,
}


def _seed_license_cache(db, tenant: Tenant, plan_codename: str, plan_features: dict) -> None:
    """Insert a TenantLicenseCache row so resolve_plan_value has data to read."""
    existing = db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(TenantLicenseCache)
        .where(TenantLicenseCache.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if existing is None:
        db.add(TenantLicenseCache(
            tenant_id=tenant.id,
            subscription_status="active",
            plan_codename=plan_codename,
            max_shops=5,
            max_employees=20,
            storage_limit_mb=10000,
            last_synced_at=datetime.now(UTC),
            plan_features=plan_features,
        ))
    else:
        existing.plan_codename = plan_codename
        existing.plan_features = plan_features
    db.flush()


@pytest.fixture()
def pro_tenant(db, tenant: Tenant) -> Tenant:
    _seed_license_cache(db, tenant, "pro", PRO_FEATURES)
    return tenant


def _resolve(db, tenant: Tenant, plan_codename: str = "pro"):
    from app.billing.entitlements import resolve_for_tenant
    return resolve_for_tenant(db, tenant.id, plan_codename)


def test_resolver_returns_plan_value_when_no_override(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    assert ents.has("headless_api") is True
    assert ents.get("max_channels") == 5


def test_resolver_returns_default_for_unknown_plan(db, tenant: Tenant) -> None:
    """A tenant with no license cache falls back to catalog defaults (headless_api=False, max_channels=1)."""
    ents = _resolve(db, tenant, plan_codename="totally-unknown")
    assert ents.has("headless_api") is False
    assert ents.get("max_channels") == 1


def test_override_beats_plan(db, tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id,
        feature_key="max_channels",
        value=42,
        reason="enterprise pilot",
    ))
    db.flush()

    ents = _resolve(db, tenant, plan_codename="free")
    assert ents.get("max_channels") == 42


def test_expired_override_is_ignored(db, tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    ))
    db.flush()

    ents = _resolve(db, tenant, plan_codename="free")
    assert ents.has("headless_api") is False


def test_future_expiring_override_still_applies(db, pro_tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="pro")
    assert ents.has("headless_api") is True


def test_require_raises_when_feature_off(db, tenant: Tenant) -> None:
    """A tenant with no license cache resolves headless_api=False (catalog default)."""
    ents = _resolve(db, tenant, plan_codename="free")
    with pytest.raises(HTTPException) as exc:
        ents.require("headless_api")
    assert exc.value.status_code == 403
    assert "plan_upgrade_required" in str(exc.value.detail)


def test_require_returns_silently_when_on(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    ents.require("headless_api")  # no exception


def test_limit_returns_numeric_value(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    assert ents.limit("max_channels") == 5


def test_limit_raises_for_non_numeric_feature(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    with pytest.raises(ValueError):
        ents.limit("headless_api")  # bool, not numeric


def test_permanent_override_no_expiry_applies(db, tenant: Tenant) -> None:
    """An override with expires_at=None (the most common shape) must apply."""
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=None,
    ))
    db.flush()

    ents = _resolve(db, tenant, plan_codename="free")
    assert ents.has("headless_api") is True


def test_require_raises_for_non_boolean_feature(db, pro_tenant: Tenant) -> None:
    """require() is for boolean gates only; numeric features must raise ValueError."""
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    with pytest.raises(ValueError):
        ents.require("max_channels")  # numeric, not boolean
