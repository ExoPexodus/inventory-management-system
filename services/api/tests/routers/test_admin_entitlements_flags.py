from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import FeatureFlag, Tenant
from app.worker.queue import redis_conn


@pytest.fixture(autouse=True)
def clear_flag_cache():
    r = redis_conn()
    for k in r.scan_iter("flag:v1:*"):
        r.delete(k)
    yield


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    """Stub admin auth + override get_db_admin so route uses the test's session.

    Without overriding get_db_admin, the route opens a fresh SessionLocal()
    that can't see the conftest-managed transaction's writes.
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


def test_create_flag(db, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/flags", json={
        "key": "stock_reservations_enabled",
        "default_state": False,
        "rollout_rules": {"percent": 10},
        "description": "Phase 0 reservation engine",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["key"] == "stock_reservations_enabled"
    assert body["default_state"] is False
    assert body["rollout_rules"]["percent"] == 10


def test_list_flags(db, auth_headers) -> None:
    db.add(FeatureFlag(key="flag-a", default_state=True))
    db.add(FeatureFlag(key="flag-b", default_state=False))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/entitlements/flags", headers=auth_headers)
    assert resp.status_code == 200
    keys = {f["key"] for f in resp.json()}
    assert keys >= {"flag-a", "flag-b"}


def test_update_flag_invalidates_cache(db, auth_headers) -> None:
    from app.billing.flags import is_enabled

    flag = FeatureFlag(key="flag-toggle", default_state=False)
    db.add(flag)
    db.commit()
    db.refresh(flag)

    # Prime cache
    assert is_enabled(db, uuid.uuid4(), "flag-toggle") is False

    client = TestClient(app)
    resp = client.patch(f"/v1/admin/entitlements/flags/{flag.id}", json={
        "default_state": True,
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["default_state"] is True

    # Cache should be invalidated → next read sees new value
    assert is_enabled(db, uuid.uuid4(), "flag-toggle") is True


def test_delete_flag(db, auth_headers) -> None:
    flag = FeatureFlag(key="flag-doomed", default_state=False)
    db.add(flag)
    db.commit()
    db.refresh(flag)

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/entitlements/flags/{flag.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_duplicate_key_rejected(db, auth_headers) -> None:
    db.add(FeatureFlag(key="flag-dup", default_state=False))
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/flags", json={
        "key": "flag-dup", "default_state": True,
    }, headers=auth_headers)
    assert resp.status_code == 409
