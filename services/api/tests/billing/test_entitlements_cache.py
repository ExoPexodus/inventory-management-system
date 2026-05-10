from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.models import Tenant, TenantFeatureOverride, TenantLicenseCache
from app.worker.queue import redis_conn

# Pro plan features for cache seeding
_PRO_FEATURES = {
    "max_channels": 5,
    "headless_api": True,
    "shopify_connector": True,
    "woocommerce_connector": True,
    "hosted_checkout": True,
    "byo_stripe": True,
    "byo_razorpay": True,
    "byo_paypal": True,
    "max_products": 5000,
    "multi_currency_advanced": True,
    "email_volume_per_month": 10000,
}


def _cache_key(tenant_id, plan: str) -> str:
    return f"ents:v1:{tenant_id}:{plan}"


def _purge(tenant_id):
    r = redis_conn()
    for k in r.scan_iter(f"ents:v1:{tenant_id}:*"):
        r.delete(k)


@pytest.fixture(autouse=True)
def clear_cache(tenant: Tenant):
    _purge(tenant.id)
    yield
    _purge(tenant.id)


def test_resolved_value_is_cached_after_first_call(db, tenant: Tenant) -> None:
    from app.billing.entitlements import resolve_for_tenant

    # Seed license cache with pro plan features so resolve_plan_value can read them
    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="pro",
        max_shops=5,
        max_employees=20,
        storage_limit_mb=10000,
        last_synced_at=datetime.now(UTC),
        plan_features=_PRO_FEATURES,
    ))
    db.flush()

    resolve_for_tenant(db, tenant.id, "pro")
    raw = redis_conn().get(_cache_key(tenant.id, "pro"))
    assert raw is not None
    payload = json.loads(raw)
    assert payload["plan_codename"] == "pro"
    assert payload["values"]["headless_api"] is True


def test_cache_hit_does_not_query_db(db, tenant: Tenant, monkeypatch) -> None:
    from app.billing import entitlements as ents_mod

    # Prime the cache
    ents_mod.resolve_for_tenant(db, tenant.id, "pro")

    # Now any DB call to _load_overrides would be a bug
    called = {"count": 0}
    real_loader = ents_mod._load_overrides

    def spy(*args, **kwargs):
        called["count"] += 1
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(ents_mod, "_load_overrides", spy)
    ents_mod.resolve_for_tenant(db, tenant.id, "pro")
    assert called["count"] == 0, "Expected cache hit, but DB loader was invoked"


def test_invalidate_removes_cached_entries(db, tenant: Tenant) -> None:
    from app.billing.entitlements import invalidate_cache, resolve_for_tenant

    resolve_for_tenant(db, tenant.id, "pro")
    resolve_for_tenant(db, tenant.id, "free")
    assert redis_conn().get(_cache_key(tenant.id, "pro")) is not None
    assert redis_conn().get(_cache_key(tenant.id, "free")) is not None

    invalidate_cache(tenant.id)
    assert redis_conn().get(_cache_key(tenant.id, "pro")) is None
    assert redis_conn().get(_cache_key(tenant.id, "free")) is None


def test_invalidate_called_after_override_write(db, tenant: Tenant) -> None:
    from app.billing.entitlements import resolve_for_tenant

    # Prime cache with current state (no overrides → free plan returns False)
    ents = resolve_for_tenant(db, tenant.id, "free")
    assert ents.has("headless_api") is False

    # Add override but DON'T invalidate — cache still says False
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="headless_api", value=True,
    ))
    db.flush()

    cached = resolve_for_tenant(db, tenant.id, "free")
    assert cached.has("headless_api") is False  # stale because not invalidated

    # Invalidate, then re-resolve — now reflects the override
    from app.billing.entitlements import invalidate_cache
    invalidate_cache(tenant.id)
    fresh = resolve_for_tenant(db, tenant.id, "free")
    assert fresh.has("headless_api") is True
