# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant, WebhookEndpoint
from app.services.webhook_service import generate_secret


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"webhooks:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_list_supported_events(auth_headers) -> None:
    resp = TestClient(app).get("/v1/admin/webhooks/supported-events", headers=auth_headers)
    assert resp.status_code == 200
    assert "order.confirmed" in resp.json()


def test_create_endpoint(db, tenant: Tenant, auth_headers) -> None:
    resp = TestClient(app).post("/v1/admin/webhooks/endpoints", json={
        "url": "https://merchant.example.com/hooks",
        "events": ["order.confirmed"],
        "description": "My store hook",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["url"] == "https://merchant.example.com/hooks"
    assert "order.confirmed" in body["events"]
    assert len(body["secret"]) == 64  # 32 hex bytes
    assert body["status"] == "active"


def test_create_endpoint_unknown_event_rejected(db, tenant: Tenant, auth_headers) -> None:
    resp = TestClient(app).post("/v1/admin/webhooks/endpoints", json={
        "url": "https://merchant.example.com/hooks",
        "events": ["payment.captured"],
    }, headers=auth_headers)
    assert resp.status_code == 400


def test_list_endpoints(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    client.post("/v1/admin/webhooks/endpoints", json={
        "url": "https://a.example.com/hooks", "events": ["order.confirmed"],
    }, headers=auth_headers)
    client.post("/v1/admin/webhooks/endpoints", json={
        "url": "https://b.example.com/hooks", "events": ["order.confirmed"],
    }, headers=auth_headers)
    resp = client.get("/v1/admin/webhooks/endpoints", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_update_endpoint_disable(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    created = client.post("/v1/admin/webhooks/endpoints", json={
        "url": "https://merchant.example.com/hooks", "events": ["order.confirmed"],
    }, headers=auth_headers).json()
    resp = client.patch(f"/v1/admin/webhooks/endpoints/{created['id']}",
                        json={"status": "disabled"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


def test_delete_endpoint(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    created = client.post("/v1/admin/webhooks/endpoints", json={
        "url": "https://merchant.example.com/hooks", "events": ["order.confirmed"],
    }, headers=auth_headers).json()
    resp = client.delete(f"/v1/admin/webhooks/endpoints/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert client.get("/v1/admin/webhooks/endpoints", headers=auth_headers).json() == []


def test_rotate_secret(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    created = client.post("/v1/admin/webhooks/endpoints", json={
        "url": "https://merchant.example.com/hooks", "events": ["order.confirmed"],
    }, headers=auth_headers).json()
    original_secret = created["secret"]
    resp = client.post(
        f"/v1/admin/webhooks/endpoints/{created['id']}/rotate-secret", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["secret"] != original_secret


def test_list_deliveries_empty(db, tenant: Tenant, auth_headers) -> None:
    resp = TestClient(app).get("/v1/admin/webhooks/deliveries", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []
