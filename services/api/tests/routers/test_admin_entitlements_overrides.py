from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant, TenantFeatureOverride
from app.worker.queue import redis_conn


def _purge_cache(tenant_id):
    r = redis_conn()
    for k in r.scan_iter(f"ents:v1:{tenant_id}:*"):
        r.delete(k)


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    """Stub admin auth: operator with the entitlements:manage permission.

    Also overrides get_db_admin to use the conftest-managed connection so the
    route's writes are visible to the test's `db` fixture (see Task 5 notes
    on session isolation).
    """
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="staff",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"entitlements:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_override(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api",
        "value": True,
        "reason": "Beta access",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["feature_key"] == "headless_api"
    assert body["value"] is True
    assert body["reason"] == "Beta access"


def test_create_override_invalidates_cache(db, tenant: Tenant, auth_headers) -> None:
    from app.billing.entitlements import resolve_for_tenant
    _purge_cache(tenant.id)

    # Prime cache with current state
    resolve_for_tenant(db, tenant.id, "free")
    assert redis_conn().keys(f"ents:v1:{tenant.id}:*")

    # Create override via API
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api", "value": True,
    }, headers=auth_headers)
    assert resp.status_code == 201

    # Cache should be cleared
    assert not redis_conn().keys(f"ents:v1:{tenant.id}:*")


def test_list_overrides(db, tenant: Tenant, auth_headers) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="headless_api", value=True,
    ))
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="max_channels", value=42,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/entitlements/overrides", headers=auth_headers)
    assert resp.status_code == 200
    keys = {o["feature_key"] for o in resp.json()}
    assert keys == {"headless_api", "max_channels"}


def test_delete_override(db, tenant: Tenant, auth_headers) -> None:
    o = TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="headless_api", value=True,
    )
    db.add(o)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/entitlements/overrides/{o.id}", headers=auth_headers)
    assert resp.status_code == 204

    # Confirm gone
    resp = client.get("/v1/admin/entitlements/overrides", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_unknown_feature_key_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "made-up-feature", "value": True,
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "unknown feature" in resp.json()["detail"].lower()


def test_create_with_expiry(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api",
        "value": True,
        "expires_at": expires,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["expires_at"] is not None


def test_missing_permission_returns_403(db, tenant: Tenant) -> None:
    """The router-level require_permission('entitlements:manage') gate must block
    operators without the permission. Stubs an AdminContext with empty permissions."""
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/admin/entitlements/overrides")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_value_null_rejected_with_422(db, tenant: Tenant, auth_headers) -> None:
    """The DB column is NOT NULL JSONB; explicit null in the body must be rejected
    at the API boundary (422), not bubble up as a DB integrity error (500)."""
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api",
        "value": None,
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_upsert_replaces_existing(db, tenant: Tenant, auth_headers) -> None:
    """POSTing the same feature_key twice updates the existing row, not insert duplicate.

    The unique constraint on (tenant_id, feature_key) would 500 on duplicate insert;
    this test exercises the SELECT-then-mutate branch in create_override.
    """
    client = TestClient(app)

    # Create
    resp1 = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api",
        "value": True,
        "reason": "first reason",
    }, headers=auth_headers)
    assert resp1.status_code == 201
    first_id = resp1.json()["id"]

    # Update via POST same feature_key
    resp2 = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api",
        "value": False,
        "reason": "updated reason",
    }, headers=auth_headers)
    assert resp2.status_code == 201
    second_id = resp2.json()["id"]

    # Same row id; updated fields
    assert second_id == first_id
    assert resp2.json()["value"] is False
    assert resp2.json()["reason"] == "updated reason"

    # Confirm only one row exists
    resp3 = client.get("/v1/admin/entitlements/overrides", headers=auth_headers)
    assert resp3.status_code == 200
    rows = resp3.json()
    keys = [r["feature_key"] for r in rows if r["feature_key"] == "headless_api"]
    assert len(keys) == 1
