import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import Tenant, TenantLicenseCache


@pytest.fixture()
def licensed_tenant(db, tenant: Tenant) -> Tenant:
    from datetime import UTC, datetime
    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="pro",
        max_shops=5,
        max_employees=20,
        storage_limit_mb=10000,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()
    return tenant


def _build_app_with_route():
    """Build a minimal FastAPI app with a single route gated by EntitlementsDep."""
    from app.billing.deps import EntitlementsDep
    from app.billing.entitlements import Entitlements

    app = FastAPI()

    @app.get("/test/headless-only")
    def headless_only(ents: EntitlementsDep) -> dict:
        ents.require("headless_api")
        return {"ok": True, "plan": ents.plan_codename}

    @app.get("/test/limit")
    def limit_route(ents: EntitlementsDep) -> dict:
        return {"max_channels": ents.limit("max_channels")}

    return app


def _stub_admin(app, tenant_id, db):
    """Override admin auth and DB so the test client uses a known context.

    Uses is_legacy_token=False because license_deps._load_license_context
    short-circuits to plan_codename="legacy" when is_legacy_token=True, which
    would bypass the cache lookup we need EntitlementsDep to consult. Permission
    checks aren't a concern here because the routes under test don't use
    require_permission().

    get_db_admin is also overridden to share the conftest db session so that
    the route handler sees rows committed by the test fixture — get_db_admin
    normally opens a fresh SessionLocal() which cannot see the fixture's
    connection-scoped transaction.
    """
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    return fake_ctx


def test_entitlements_dep_resolves_for_authenticated_tenant(db, licensed_tenant: Tenant) -> None:
    """A request from a tenant on 'pro' should pass the headless_api gate."""
    app = _build_app_with_route()
    _stub_admin(app, licensed_tenant.id, db)

    client = TestClient(app)
    resp = client.get("/test/headless-only")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "plan": "pro"}


def test_entitlements_dep_rejects_when_feature_off(db, tenant: Tenant) -> None:
    """A 'free' plan tenant calling a 'headless_api'-gated route gets 403 plan_upgrade_required."""
    from datetime import UTC, datetime

    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="free",
        max_shops=1,
        max_employees=2,
        storage_limit_mb=500,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()

    app = _build_app_with_route()
    _stub_admin(app, tenant.id, db)

    client = TestClient(app)
    resp = client.get("/test/headless-only")
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error"] == "plan_upgrade_required"
    assert body["detail"]["required_feature"] == "headless_api"
    assert body["detail"]["current_plan"] == "free"


def test_entitlements_dep_returns_numeric_limit(db, licensed_tenant: Tenant) -> None:
    app = _build_app_with_route()
    _stub_admin(app, licensed_tenant.id, db)

    client = TestClient(app)
    resp = client.get("/test/limit")
    assert resp.status_code == 200
    assert resp.json() == {"max_channels": 5}
