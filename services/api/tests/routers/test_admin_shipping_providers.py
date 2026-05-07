# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"p-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    ch = Channel(tenant_id=tenant.id, type="headless", name=f"c-{uuid.uuid4().hex[:6]}",
                 config={}, inventory_pool_id=pool.id, currency_code="INR")
    db.add(ch)
    db.flush()
    db.commit()
    return ch


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin
    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"shipping:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_setup_shiprocket_validates_and_stores_encrypted(db, tenant: Tenant, channel: Channel, auth) -> None:
    from app.services.email_service import decrypt_secret

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"token": "test_jwt_token"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp), \
         patch("app.routers.admin_shipping_providers.redis_conn") as mock_redis_fn:
        mock_redis_fn.return_value = MagicMock()
        resp = TestClient(app).post(
            f"/v1/admin/channels/{channel.id}/shipping/setup-shiprocket",
            json={
                "email": "store@example.com",
                "password": "secret123",
                "pickup_location": "Warehouse-Mumbai",
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["configured"] is True
    assert body["pickup_location"] == "Warehouse-Mumbai"

    db.refresh(channel)
    assert channel.config.get("shipping_provider") == "shiprocket"
    assert channel.config.get("shiprocket_email") == "store@example.com"
    assert decrypt_secret(channel.config.get("shiprocket_password")) == "secret123"


def test_get_shipping_config_unconfigured(db, tenant: Tenant, channel: Channel, auth) -> None:
    resp = TestClient(app).get(f"/v1/admin/channels/{channel.id}/shipping/config")
    assert resp.status_code == 200
    assert resp.json()["configured"] is False


def test_delete_shipping_config(db, tenant: Tenant, channel: Channel, auth) -> None:
    channel.config = {**channel.config, "shipping_provider": "shiprocket",
                      "shiprocket_email": "store@example.com"}
    db.commit()

    with patch("app.routers.admin_shipping_providers.redis_conn") as mock_r:
        mock_r.return_value = MagicMock()
        resp = TestClient(app).delete(f"/v1/admin/channels/{channel.id}/shipping/config")
    assert resp.status_code == 204
    db.refresh(channel)
    assert channel.config.get("shipping_provider") is None
