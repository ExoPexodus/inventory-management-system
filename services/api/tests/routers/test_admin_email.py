# NOTE: `from __future__ import annotations` deliberately absent (breaks FastAPI deps).

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None,
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"email:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_get_config_unconfigured(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/email/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["configured"] is False
    assert resp.json()["from_email"] is None


def test_configure_email(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/email/configure", json={
        "resend_api_key": "re_test_xxx",
        "from_email": "noreply@mystore.com",
        "from_name": "My Store",
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["from_email"] == "noreply@mystore.com"
    assert body["from_name"] == "My Store"


def test_get_config_after_configure(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    client.post("/v1/admin/email/configure", json={
        "resend_api_key": "re_test_xxx",
        "from_email": "store@example.com",
        "from_name": "Store",
    }, headers=auth_headers)
    resp = client.get("/v1/admin/email/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["configured"] is True
    assert resp.json()["from_email"] == "store@example.com"


def test_test_send_success(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    client.post("/v1/admin/email/configure", json={
        "resend_api_key": "re_test_xxx",
        "from_email": "store@example.com",
        "from_name": "Store",
    }, headers=auth_headers)

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "test_sent"}
    with patch("httpx.post", return_value=mock_resp):
        resp = client.post("/v1/admin/email/test-send", json={
            "to_email": "merchant@example.com",
        }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["sent"] is True


def test_test_send_without_config_returns_400(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/email/test-send", json={
        "to_email": "merchant@example.com",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"].lower()
