from unittest.mock import MagicMock, patch
import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def stripe_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return Channel(
        tenant_id=tenant.id, type="headless", name="Stripe",
        config={"payment_provider": "stripe", "stripe_secret_key": "sk_test_xxx",
                "stripe_publishable_key": "pk_test_xxx",
                "checkout_success_url": "https://shop.com/success"},
        inventory_pool_id=pool.id, currency_code="INR",
    )


@pytest.fixture()
def razorpay_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return Channel(
        tenant_id=tenant.id, type="headless", name="Razorpay",
        config={"payment_provider": "razorpay", "razorpay_key_id": "rzp_test_xxx",
                "razorpay_key_secret": "test_secret",
                "checkout_success_url": "https://shop.com/success"},
        inventory_pool_id=pool.id, currency_code="INR",
    )


def test_create_stripe_payment_intent(stripe_channel) -> None:
    mock_intent = MagicMock()
    mock_intent.id = "pi_test123"
    mock_intent.client_secret = "pi_test123_secret"

    with patch("stripe.PaymentIntent.create", return_value=mock_intent):
        from app.services.payment_service import create_payment_intent
        result = create_payment_intent(stripe_channel, 1999, "INR")
        assert result["provider"] == "stripe"
        assert result["client_secret"] == "pi_test123_secret"


def test_create_razorpay_order(razorpay_channel) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "order_rzp_test", "amount": 199900, "currency": "INR", "status": "created"}

    with patch("httpx.post", return_value=mock_resp):
        from app.services.payment_service import create_payment_intent
        result = create_payment_intent(razorpay_channel, 1999, "INR")
        assert result["provider"] == "razorpay"
        assert result["order_id"] == "order_rzp_test"
        assert result["key_id"] == "rzp_test_xxx"


def test_verify_stripe_success(stripe_channel) -> None:
    mock_intent = MagicMock()
    mock_intent.status = "succeeded"
    with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
        from app.services.payment_service import verify_payment
        assert verify_payment(stripe_channel, "pi_test123") is True


def test_verify_stripe_pending(stripe_channel) -> None:
    mock_intent = MagicMock()
    mock_intent.status = "requires_payment_method"
    with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
        from app.services.payment_service import verify_payment
        assert verify_payment(stripe_channel, "pi_test123") is False


def test_verify_razorpay_signature(razorpay_channel) -> None:
    import hashlib
    import hmac as hmac_mod
    order_id = "order_test"
    payment_id = "pay_test"
    sig = hmac_mod.new("test_secret".encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()

    from app.services.payment_service import verify_razorpay_signature
    assert verify_razorpay_signature(razorpay_channel, order_id, payment_id, sig) is True
    assert verify_razorpay_signature(razorpay_channel, order_id, payment_id, "bad") is False
