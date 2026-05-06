"""End-to-end smoke test for the headless storefront API.

Full shopper flow: browse catalog → cart → discount → checkout summary → submit order.
Verifies stock committed and cart cleared after order submission.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import (
    Channel, Discount, InventoryPool, InventoryPoolShop, Order,
    Product, Shop, StockMovement, StockReservation, Tenant, TaxRegion, TaxRule,
)


@pytest.fixture(autouse=True)
def _override_storefront_db(db):
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
        tax_included_in_price=False,
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Handmade Mug", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical", status="active",
        slug="handmade-mug", weight_grams=400,
    )
    db.add(product)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=100, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))

    discount = Discount(
        tenant_id=tenant.id, name="10% off", code="TEN",
        discount_type="percentage", value_bps=1000, status="active",
    )
    db.add(discount)

    region = TaxRegion(tenant_id=tenant.id, name="India GST", country_code="IN")
    db.add(region)
    db.flush()
    db.add(TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST 18%",
        components=[{"label": "GST", "rate_bps": 1800}],
    ))
    db.commit()

    return {"channel": channel, "product": product}


def _h(setup):
    return {"X-Channel-Id": str(setup["channel"].id)}


def test_full_shopper_flow(db, tenant: Tenant, setup) -> None:
    client = TestClient(app)

    # 1. Browse catalog
    catalog = client.get("/v1/storefront/products", headers=_h(setup))
    assert catalog.status_code == 200
    assert any(p["name"] == "Handmade Mug" for p in catalog.json()["items"])

    # 2. Get product by slug
    detail = client.get("/v1/storefront/products/handmade-mug", headers=_h(setup))
    assert detail.status_code == 200
    assert detail.json()["slug"] == "handmade-mug"

    # 3. Create cart and add 2 mugs
    cart = client.post("/v1/storefront/cart", headers=_h(setup)).json()
    token = cart["cart_token"]

    add = client.post(f"/v1/storefront/cart/{token}/items", json={
        "product_id": str(setup["product"].id), "quantity": 2,
    }, headers=_h(setup))
    assert add.status_code == 200
    assert add.json()["total_cents"] == 20000

    # Reservation created
    reservations = db.execute(
        select(StockReservation).where(
            StockReservation.cart_token == token, StockReservation.status == "active"
        )
    ).scalars().all()
    assert len(reservations) == 1
    assert reservations[0].quantity == 2

    # 4. Apply discount
    disc = client.post(f"/v1/storefront/cart/{token}/discount",
                       json={"code": "TEN"}, headers=_h(setup))
    assert disc.status_code == 200
    assert disc.json()["discount_cents"] == 2000
    assert disc.json()["final_subtotal_cents"] == 18000

    # 5. Get summary with tax
    summary = client.get(
        f"/v1/storefront/cart/{token}/summary",
        params={"destination_country": "IN", "discount_code": "TEN"},
        headers=_h(setup),
    )
    assert summary.status_code == 200
    s = summary.json()
    assert s["subtotal_cents"] == 20000
    assert s["discount_cents"] == 2000
    assert s["tax_cents"] == 3600  # 20000 * 18% = 3600 (tax on pre-discount subtotal)
    assert s["total_cents"] == 21600  # (20000 - 2000) + 3600

    # 6. Submit order
    order_resp = client.post("/v1/storefront/orders", json={
        "cart_token": token,
        "payment_provider": "stripe",
        "payment_reference": "pi_test_stripe_123",
        "customer_email": "mug-buyer@example.com",
        "shipping_address": {"country": "IN", "city": "Bangalore"},
        "discount_code": "TEN",
    }, headers=_h(setup))
    assert order_resp.status_code == 201, order_resp.text
    order = order_resp.json()
    assert order["status"] == "confirmed"
    assert order["customer_email"] == "mug-buyer@example.com"
    assert order["discount_cents"] == 2000
    assert order["total_cents"] == 18000

    # 7. Cart is cleared
    cart_after = client.get(f"/v1/storefront/cart/{token}", headers=_h(setup)).json()
    assert cart_after["items"] == []

    # 8. Reservation committed
    res_after = db.execute(
        select(StockReservation).where(StockReservation.cart_token == token)
    ).scalars().all()
    assert all(r.status == "committed" for r in res_after)
