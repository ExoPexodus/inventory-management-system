"""End-to-end smoke test for the entitlements stack.

Exercises: TenantLicenseCache -> _load_license_context (license_deps) ->
_load_entitlements (billing.deps) -> Entitlements.require -> HTTP response.
"""
# NOTE: `from __future__ import annotations` is intentionally absent here.
# Under PEP 563, FastAPI's get_type_hints() cannot resolve `EntitlementsDep`
# from _build_app()'s local scope (becomes a bare string, treated as a query
# param, 422 on every request). See the same comment in test_entitlements_dep.py.

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import Tenant, TenantFeatureOverride, TenantLicenseCache
from app.worker.queue import redis_conn


def _purge(tenant_id):
    r = redis_conn()
    for k in r.scan_iter(f"ents:v1:{tenant_id}:*"):
        r.delete(k)


@pytest.fixture(autouse=True)
def cache_clean(tenant: Tenant):
    _purge(tenant.id)
    yield
    _purge(tenant.id)


def _seed_license(db, tenant_id, plan_codename: str) -> None:
    db.add(TenantLicenseCache(
        tenant_id=tenant_id,
        subscription_status="active",
        plan_codename=plan_codename,
        max_shops=999,
        max_employees=999,
        storage_limit_mb=99999,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()


def _build_app(db, tenant_id):
    """Build a minimal FastAPI app with auth + db overrides + a gated route.

    Three deviations from the plan's original sketch (all necessary):
    - is_legacy_token=False so license loading actually consults the cache
    - dependency_overrides[get_db_admin] so the route uses the test's session
      (the route's default SessionLocal() opens a separate connection and
      can't see the conftest-managed transaction's data)
    - No `from __future__ import annotations` at module top (PEP 563 + FastAPI
      type-hint resolution from local scope don't mix)
    """
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.billing.deps import EntitlementsDep
    from app.db.admin_deps_db import get_db_admin

    app = FastAPI()
    app.dependency_overrides[require_admin_context] = lambda: AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )
    app.dependency_overrides[get_db_admin] = lambda: db

    @app.get("/probe/headless")
    def probe(ents: EntitlementsDep):
        ents.require("headless_api")
        return {"plan": ents.plan_codename, "max_channels": ents.limit("max_channels")}

    return app


def test_pro_plan_gets_through(db, tenant: Tenant) -> None:
    _seed_license(db, tenant.id, "pro")
    app = _build_app(db, tenant.id)
    resp = TestClient(app).get("/probe/headless")
    assert resp.status_code == 200
    assert resp.json() == {"plan": "pro", "max_channels": 5}


def test_free_plan_blocked_with_structured_error(db, tenant: Tenant) -> None:
    _seed_license(db, tenant.id, "free")
    app = _build_app(db, tenant.id)
    resp = TestClient(app).get("/probe/headless")
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error"] == "plan_upgrade_required"
    assert body["detail"]["required_feature"] == "headless_api"
    assert body["detail"]["current_plan"] == "free"


def test_override_unblocks_a_free_plan(db, tenant: Tenant) -> None:
    _seed_license(db, tenant.id, "free")
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id,
        feature_key="headless_api",
        value=True,
        reason="Beta access",
    ))
    db.commit()

    app = _build_app(db, tenant.id)
    resp = TestClient(app).get("/probe/headless")
    assert resp.status_code == 200
    assert resp.json()["plan"] == "free"  # plan codename unchanged
