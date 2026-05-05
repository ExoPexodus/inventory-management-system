from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import Tenant, TenantFeatureOverride


@pytest.fixture()
def pro_tenant(db, tenant: Tenant) -> Tenant:
    return tenant


def _resolve(db, tenant: Tenant, plan_codename: str = "pro"):
    from app.billing.entitlements import resolve_for_tenant
    return resolve_for_tenant(db, tenant.id, plan_codename)


def test_resolver_returns_plan_value_when_no_override(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    assert ents.has("headless_api") is True
    assert ents.get("max_channels") == 5


def test_resolver_returns_default_for_unknown_plan(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="totally-unknown")
    assert ents.has("headless_api") is False
    assert ents.get("max_channels") == 1


def test_override_beats_plan(db, pro_tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="max_channels",
        value=42,
        reason="enterprise pilot",
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="free")
    assert ents.get("max_channels") == 42


def test_expired_override_is_ignored(db, pro_tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="free")
    assert ents.has("headless_api") is False


def test_future_expiring_override_still_applies(db, pro_tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="free")
    assert ents.has("headless_api") is True


def test_require_raises_when_feature_off(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="free")
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


def test_permanent_override_no_expiry_applies(db, pro_tenant: Tenant) -> None:
    """An override with expires_at=None (the most common shape) must apply."""
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=None,
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="free")
    assert ents.has("headless_api") is True


def test_require_raises_for_non_boolean_feature(db, pro_tenant: Tenant) -> None:
    """require() is for boolean gates only; numeric features must raise ValueError."""
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    with pytest.raises(ValueError):
        ents.require("max_channels")  # numeric, not boolean
