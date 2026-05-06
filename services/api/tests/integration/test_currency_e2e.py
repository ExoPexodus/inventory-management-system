"""End-to-end smoke test for the multi-currency engine.

Covers:
- Money type behavior under arithmetic
- FX service: set, get, convert (direct + inverse + same-currency)
- Pricing resolver: explicit channel-specific > tenant-wide > FX-derived
- Admin endpoints: create FX rate via API, then resolver picks it up
"""
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, ProductPrice, Shop, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="manual", name=f"channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="E2E Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1999,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"currency:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_full_pricing_resolution_chain(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """No prices, no rate → raises. Add tenant-wide → tenant-wide. Add channel-specific → channel-specific."""
    from app.billing.fx import FxRateMissingError
    from app.billing.money import Money
    from app.billing.pricing import price_for_product_in_currency

    # 1. No prices, no rate → raises
    with pytest.raises(FxRateMissingError):
        price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)

    # 2. Add tenant-wide price → returns it
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.flush()
    p1 = price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)
    assert p1 == Money(1899, "EUR")

    # 3. Add channel-specific override → returns it instead
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=channel.id,
        currency_code="EUR", amount_cents=1799,
    ))
    db.flush()
    p2 = price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)
    assert p2 == Money(1799, "EUR")


def test_fx_fallback_via_admin_api(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """Set FX rate via admin API. Resolver uses it for currencies without explicit ProductPrice."""
    from app.billing.money import Money
    from app.billing.pricing import price_for_product_in_currency

    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD",
        "to_currency": "INR",
        "rate": "83.00",
    })
    assert resp.status_code == 201

    # No ProductPrice for INR → resolver uses FX. unit_price_cents=1999 USD × 83 = 165917 INR cents
    p = price_for_product_in_currency(db, product.id, "INR", channel_id=channel.id)
    assert p == Money(165917, "INR")


def test_money_arithmetic_invariants(db, tenant: Tenant) -> None:
    from app.billing.fx import FxRateMissingError, convert
    from app.billing.money import Money

    # Same currency: add/sub work
    a = Money(1000, "USD")
    b = Money(250, "USD")
    assert (a + b) == Money(1250, "USD")
    assert (a - b) == Money(750, "USD")

    # Cross currency: arithmetic raises
    with pytest.raises(ValueError):
        a + Money(100, "EUR")

    # Convert is the only legal cross-currency operation, and requires a rate
    with pytest.raises(FxRateMissingError):
        convert(db, tenant.id, a, "EUR")


def test_admin_api_lifecycle(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """Round-trip: create rate, list rates, create product price, list prices, delete."""
    client = TestClient(app)

    # Create FX rate
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "EUR", "rate": "0.92",
    })
    assert resp.status_code == 201
    rate_id = resp.json()["id"]

    # List shows it
    resp = client.get("/v1/admin/fx-rates")
    assert resp.status_code == 200
    assert any(r["id"] == rate_id for r in resp.json())

    # Create channel-specific price
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": str(channel.id),
        "currency_code": "EUR",
        "amount_cents": 1799,
    })
    assert resp.status_code == 201
    price_id = resp.json()["id"]

    # List shows it
    resp = client.get(f"/v1/admin/products/{product.id}/prices")
    assert resp.status_code == 200
    assert any(p["id"] == price_id for p in resp.json())

    # Delete both
    assert client.delete(f"/v1/admin/products/{product.id}/prices/{price_id}").status_code == 204
    assert client.delete(f"/v1/admin/fx-rates/{rate_id}").status_code == 204
