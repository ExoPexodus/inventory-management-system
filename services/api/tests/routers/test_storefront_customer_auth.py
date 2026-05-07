# NOTE: `from __future__ import annotations` deliberately absent.

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, StorefrontOTP, Tenant


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
def db_override(db, channel: Channel):
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.pop(get_db, None)


def test_request_otp_sends_response(db, tenant: Tenant, channel: Channel, db_override) -> None:
    from unittest.mock import patch
    with patch("app.services.email_service._resend_send", return_value=True):
        resp = TestClient(app).post(
            "/v1/storefront/auth/otp/request",
            json={"email": "shopper@example.com"},
            headers={"X-Channel-Id": str(channel.id)},
        )
    assert resp.status_code == 200, resp.text
    assert "sent" in resp.json()


def test_verify_otp_returns_token(db, tenant: Tenant, channel: Channel, db_override) -> None:
    code = "123456"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    otp = StorefrontOTP(
        tenant_id=tenant.id, channel_id=channel.id,
        email="shopper@example.com",
        code_hash=code_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(otp)
    db.commit()

    resp = TestClient(app).post(
        "/v1/storefront/auth/otp/verify",
        json={"email": "shopper@example.com", "code": code},
        headers={"X-Channel-Id": str(channel.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_verify_wrong_otp_rejected(db, tenant: Tenant, channel: Channel, db_override) -> None:
    otp = StorefrontOTP(
        tenant_id=tenant.id, channel_id=channel.id,
        email="shopper@example.com",
        code_hash=hashlib.sha256("999999".encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(otp)
    db.commit()

    resp = TestClient(app).post(
        "/v1/storefront/auth/otp/verify",
        json={"email": "shopper@example.com", "code": "000000"},
        headers={"X-Channel-Id": str(channel.id)},
    )
    assert resp.status_code == 401
