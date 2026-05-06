# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import FxRate, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"currency:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_fx_rate(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD",
        "to_currency": "INR",
        "rate": "83.25",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "INR"
    assert Decimal(body["rate"]) == Decimal("83.25")
    assert body["source"] == "manual"


def test_list_fx_rates(db, tenant: Tenant, auth_headers) -> None:
    db.add(FxRate(
        tenant_id=tenant.id, from_currency="USD", to_currency="EUR",
        rate=Decimal("0.92"), source="manual", effective_at=datetime.now(UTC),
    ))
    db.add(FxRate(
        tenant_id=tenant.id, from_currency="USD", to_currency="GBP",
        rate=Decimal("0.79"), source="manual", effective_at=datetime.now(UTC),
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/fx-rates", headers=auth_headers)
    assert resp.status_code == 200
    pairs = {(r["from_currency"], r["to_currency"]) for r in resp.json()}
    assert pairs == {("USD", "EUR"), ("USD", "GBP")}


def test_create_fx_rate_normalises_currency_to_upper(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "usd",
        "to_currency": "eur",
        "rate": "0.92",
    }, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "EUR"


def test_create_same_pair_updates(db, tenant: Tenant, auth_headers) -> None:
    """POSTing the same pair twice updates the existing row."""
    client = TestClient(app)
    r1 = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "INR", "rate": "82.00",
    }, headers=auth_headers)
    r2 = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "INR", "rate": "83.50",
    }, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert Decimal(r2.json()["rate"]) == Decimal("83.50")


def test_delete_fx_rate(db, tenant: Tenant, auth_headers) -> None:
    rate = FxRate(
        tenant_id=tenant.id, from_currency="USD", to_currency="JPY",
        rate=Decimal("150.0"), source="manual", effective_at=datetime.now(UTC),
    )
    db.add(rate)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/fx-rates/{rate.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_invalid_rate_format_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "EUR", "rate": "not-a-number",
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_negative_rate_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "EUR", "rate": "-1.0",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "positive" in resp.json()["detail"].lower()
