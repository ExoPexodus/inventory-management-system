import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import CartItem, Channel, InventoryPool, Product, Tenant, TenantEmailConfig
from app.services.email_service import encrypt_secret


@pytest.fixture()
def setup(db, tenant: Tenant):
    pool = InventoryPool(tenant_id=tenant.id, name=f"p-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    ch = Channel(tenant_id=tenant.id, type="headless", name=f"c-{uuid.uuid4().hex[:6]}",
                 config={}, inventory_pool_id=pool.id, currency_code="INR")
    db.add(ch)
    db.flush()
    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=999, product_type="physical", status="active",
    )
    db.add(product)
    db.flush()
    config = TenantEmailConfig(
        tenant_id=tenant.id, provider="resend", from_email="store@example.com",
        from_name="Store", api_key_encrypted=encrypt_secret("re_test"),
    )
    db.add(config)
    db.flush()
    cart = CartItem(
        tenant_id=tenant.id, channel_id=ch.id,
        cart_token=f"tok-{uuid.uuid4().hex[:8]}",
        product_id=product.id, quantity=2,
        unit_price_cents=999, currency_code="INR",
    )
    db.add(cart)
    db.commit()
    return {"channel": ch, "product": product, "cart": cart}


def test_send_abandoned_cart_email_success(db, tenant: Tenant, setup) -> None:
    from app.services.email_service import send_abandoned_cart_email

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "email_sent"}

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        result = send_abandoned_cart_email(
            db=db,
            tenant_id=tenant.id,
            channel_id=setup["channel"].id,
            cart_token=setup["cart"].cart_token,
            customer_email="buyer@example.com",
            checkout_url="https://shop.com/checkout/abc",
        )

    assert result is True
    call_json = mock_post.call_args.kwargs.get("json", {})
    assert "buyer@example.com" in str(call_json.get("to", ""))
    assert "Widget" in call_json.get("html", "")


def test_send_abandoned_cart_no_config(db, tenant: Tenant, setup) -> None:
    """Without email config, function returns False silently."""
    from app.services.email_service import send_abandoned_cart_email

    # Remove the config fixture created in setup by re-querying directly
    from app.models import TenantEmailConfig
    cfg = db.query(TenantEmailConfig).filter_by(tenant_id=tenant.id).first()
    if cfg:
        db.delete(cfg)
        db.commit()

    result = send_abandoned_cart_email(
        db=db, tenant_id=tenant.id, channel_id=setup["channel"].id,
        cart_token=setup["cart"].cart_token, customer_email="buyer@example.com",
    )
    assert result is False
