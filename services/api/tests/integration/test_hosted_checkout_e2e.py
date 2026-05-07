"""End-to-end smoke test for the hosted checkout flow (Stripe, mocked)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Order, Product, Shop, StockMovement, Tenant


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name="Headless Store",
        config={"payment_provider": "stripe", "stripe_secret_key": "sk_test_xxx",
                "stripe_publishable_key": "pk_test_xxx",
                "checkout_success_url": "https://shop.com/success"},
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()
    product = Product(
        tenant_id=tenant.id, name="E2E Mug", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1999, product_type="physical", status="active",
    )
    db.add(product)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=50, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()
    return {"channel": channel, "product": product}


def test_full_hosted_checkout_stripe(db, tenant: Tenant, setup) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        channel = setup["channel"]
        product = setup["product"]

        # 1. Create cart + add item
        cart = client.post("/v1/storefront/cart",
                           headers={"X-Channel-Id": str(channel.id)}).json()
        token = cart["cart_token"]
        client.post(f"/v1/storefront/cart/{token}/items", json={
            "product_id": str(product.id), "quantity": 2,
        }, headers={"X-Channel-Id": str(channel.id)})

        # 2. Create checkout session
        session_resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": token,
        }, headers={"X-Channel-Id": str(channel.id)})
        assert session_resp.status_code == 201
        session_token = session_resp.json()["session_token"]
        assert session_token in session_resp.json()["checkout_url"]

        # 3. Hosted page serves HTML with publishable key
        page = client.get(f"/checkout/{session_token}")
        assert page.status_code == 200
        assert "pk_test_xxx" in page.text

        # 4. Create Stripe payment intent
        mock_intent = MagicMock()
        mock_intent.id = "pi_e2e_test"
        mock_intent.client_secret = "pi_e2e_test_secret"
        with patch("stripe.PaymentIntent.create", return_value=mock_intent):
            pi = client.post(f"/v1/checkout/{session_token}/payment-intent", json={
                "customer_email": "e2e@example.com",
                "shipping_address": {"country": "IN", "city": "Delhi"},
            })
        assert pi.status_code == 200
        assert pi.json()["client_secret"] == "pi_e2e_test_secret"

        # 5. Complete checkout
        mock_verify = MagicMock()
        mock_verify.status = "succeeded"
        with patch("stripe.PaymentIntent.retrieve", return_value=mock_verify):
            complete = client.post(f"/v1/checkout/{session_token}/complete", json={
                "payment_intent_id": "pi_e2e_test",
                "customer_email": "e2e@example.com",
            })
        assert complete.status_code == 200
        result = complete.json()
        assert result["status"] == "completed"
        assert "success" in result["redirect_url"]

        # 6. IMS Order exists
        order = db.execute(
            select(Order).where(Order.id == uuid.UUID(result["order_id"]))
        ).scalar_one()
        assert order.customer_email == "e2e@example.com"
        assert order.total_cents == 3998  # 1999 * 2
        assert order.channel_id == channel.id

        # 7. Cart cleared
        cart_after = client.get(f"/v1/storefront/cart/{token}",
                                headers={"X-Channel-Id": str(channel.id)}).json()
        assert cart_after["items"] == []

    finally:
        app.dependency_overrides.pop(get_db, None)
