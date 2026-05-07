import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models import Channel, InventoryPool, Order, OrderLine, Tenant, TenantEmailConfig
from app.services.email_service import encrypt_secret


@pytest.fixture()
def channel(db, tenant: Tenant) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
        type="headless",
        name=f"test-{uuid.uuid4().hex[:6]}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def email_config(db, tenant: Tenant) -> TenantEmailConfig:
    config = TenantEmailConfig(
        tenant_id=tenant.id,
        provider="resend",
        from_email="store@example.com",
        from_name="My Store",
        api_key_encrypted=encrypt_secret("re_test_xxx"),
    )
    db.add(config)
    db.flush()
    return config


@pytest.fixture()
def order_with_lines(db, tenant: Tenant, channel: Channel, email_config: TenantEmailConfig) -> Order:
    order = Order(
        tenant_id=tenant.id,
        channel_id=channel.id,
        status="confirmed",
        customer_email="buyer@example.com",
        subtotal_cents=3998,
        tax_cents=719,
        shipping_cents=0,
        discount_cents=0,
        total_cents=4717,
        currency_code="INR",
        shipping_address={"city": "Mumbai", "country": "IN"},
    )
    db.add(order)
    db.flush()
    db.add(OrderLine(
        tenant_id=tenant.id,
        order_id=order.id,
        title="Widget A",
        sku="W001",
        quantity=2,
        unit_price_cents=1999,
        line_total_cents=3998,
    ))
    db.flush()
    return order


def test_send_order_confirmation_success(db, order_with_lines: Order) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "email_test123"}

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        from app.services.email_service import send_order_confirmation
        result = send_order_confirmation(db, order_with_lines)

    assert result is True
    call_json = mock_post.call_args.kwargs.get("json", {})
    assert call_json["to"] == ["buyer@example.com"]
    assert "Order Confirmed" in call_json["subject"]
    assert "Widget A" in call_json["html"]


def test_send_order_confirmation_no_config(db, tenant: Tenant, channel: Channel) -> None:
    order = Order(
        tenant_id=tenant.id,
        channel_id=channel.id,
        status="confirmed",
        customer_email="buyer@example.com",
        subtotal_cents=1000,
        tax_cents=0,
        shipping_cents=0,
        discount_cents=0,
        total_cents=1000,
        currency_code="INR",
    )
    db.add(order)
    db.flush()

    from app.services.email_service import send_order_confirmation
    result = send_order_confirmation(db, order)
    assert result is False


def test_send_order_confirmation_no_customer_email(db, tenant: Tenant, channel: Channel, email_config: TenantEmailConfig) -> None:
    order = Order(
        tenant_id=tenant.id,
        channel_id=channel.id,
        status="confirmed",
        customer_email=None,
        subtotal_cents=1000,
        tax_cents=0,
        shipping_cents=0,
        discount_cents=0,
        total_cents=1000,
        currency_code="INR",
    )
    db.add(order)
    db.flush()

    from app.services.email_service import send_order_confirmation
    result = send_order_confirmation(db, order)
    assert result is False


def test_send_order_confirmation_api_failure_does_not_raise(db, order_with_lines: Order) -> None:
    mock_resp = MagicMock(status_code=500)
    mock_resp.text = "Internal Server Error"

    with patch("httpx.post", return_value=mock_resp):
        from app.services.email_service import send_order_confirmation
        result = send_order_confirmation(db, order_with_lines)
    assert result is False


def test_send_test_email_resend(tenant: Tenant, email_config: TenantEmailConfig) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "test_email_123"}

    with patch("httpx.post", return_value=mock_resp):
        from app.services.email_service import send_test_email
        result = send_test_email(email_config, to_email="merchant@example.com")
    assert result is True


def test_send_test_email_smtp(db, tenant: Tenant) -> None:
    from app.services.email_service import encrypt_secret, send_test_email

    smtp_config = TenantEmailConfig(
        tenant_id=tenant.id,
        provider="smtp",
        from_email="orders@mystore.com",
        from_name="My Store",
        smtp_host="smtp.hostinger.com",
        smtp_port=587,
        smtp_username="orders@mystore.com",
        smtp_password_encrypted=encrypt_secret("secret"),
    )
    db.add(smtp_config)
    db.flush()

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        result = send_test_email(smtp_config, to_email="merchant@example.com")
    assert result is True
