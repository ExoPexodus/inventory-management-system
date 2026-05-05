from __future__ import annotations

import uuid

import pytest

from app.models import FeatureFlag, Tenant
from app.worker.queue import redis_conn


@pytest.fixture(autouse=True)
def clear_flag_cache():
    r = redis_conn()
    for k in r.scan_iter("flag:v1:*"):
        r.delete(k)
    yield
    for k in r.scan_iter("flag:v1:*"):
        r.delete(k)


def _flag(db, key: str, default: bool = False, rules: dict | None = None) -> FeatureFlag:
    f = FeatureFlag(key=key, default_state=default, rollout_rules=rules)
    db.add(f)
    db.flush()
    return f


def test_unknown_flag_is_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    assert is_enabled(db, tenant.id, "does-not-exist") is False


def test_flag_default_state_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-a", default=False)
    assert is_enabled(db, tenant.id, "flag-a") is False


def test_flag_default_state_on(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-b", default=True)
    assert is_enabled(db, tenant.id, "flag-b") is True


def test_allowlist_takes_effect_when_default_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-c", default=False, rules={"allowlist": [str(tenant.id)]})
    assert is_enabled(db, tenant.id, "flag-c") is True

    other_tenant = uuid.uuid4()
    assert is_enabled(db, other_tenant, "flag-c") is False


def test_denylist_takes_effect_when_default_on(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-d", default=True, rules={"denylist": [str(tenant.id)]})
    assert is_enabled(db, tenant.id, "flag-d") is False


def test_percent_rollout_is_deterministic_per_tenant(db, tenant: Tenant) -> None:
    """A given tenant_id either bucket-hits or not for a given flag — not random."""
    from app.billing.flags import is_enabled
    _flag(db, "flag-e", default=False, rules={"percent": 50})
    a = is_enabled(db, tenant.id, "flag-e")
    b = is_enabled(db, tenant.id, "flag-e")
    assert a == b


def test_percent_rollout_zero_is_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-f", default=False, rules={"percent": 0})
    assert is_enabled(db, tenant.id, "flag-f") is False


def test_percent_rollout_hundred_is_on(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-g", default=False, rules={"percent": 100})
    assert is_enabled(db, tenant.id, "flag-g") is True


def test_invalidate_clears_cached_value(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled, invalidate_flag_cache
    flag = _flag(db, "flag-h", default=False)
    assert is_enabled(db, tenant.id, "flag-h") is False  # populates cache

    flag.default_state = True
    db.flush()

    # Stale cache still says False until invalidated
    assert is_enabled(db, tenant.id, "flag-h") is False
    invalidate_flag_cache("flag-h")
    assert is_enabled(db, tenant.id, "flag-h") is True
