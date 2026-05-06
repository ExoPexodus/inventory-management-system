import base64
import hashlib
import hmac as hmac_mod
import json
from unittest.mock import MagicMock, patch
import uuid

import pytest

from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def woo_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="woocommerce", name="My WooCommerce Store",
        config={
            "woocommerce_store_url": "https://mystore.com",
            "woocommerce_consumer_key": "ck_test123",
            "woocommerce_consumer_secret": "cs_test123",
            "woocommerce_webhook_secret": "whs_test123",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku="SKU-001",
        unit_price_cents=1999, product_type="physical", status="active",
        description="A great widget",
    )
    db.add(p)
    db.flush()
    return p


def test_test_connection_success(db, woo_channel: Channel) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"store_name": "My WooCommerce Store", "currency": "INR"}

    with patch("httpx.get", return_value=mock_resp):
        from app.services.woocommerce_service import test_connection
        result = test_connection(woo_channel)
        assert result["success"] is True
        assert result["store_name"] == "My WooCommerce Store"


def test_test_connection_bad_credentials(db, woo_channel: Channel) -> None:
    mock_resp = MagicMock(status_code=401)
    mock_resp.json.return_value = {"code": "woocommerce_rest_authentication_error"}

    with patch("httpx.get", return_value=mock_resp):
        from app.services.woocommerce_service import WooCommerceAuthError, test_connection
        with pytest.raises(WooCommerceAuthError):
            test_connection(woo_channel)


def test_push_product_creates_new(db, tenant: Tenant, woo_channel: Channel, product: Product) -> None:
    mock_resp = MagicMock(status_code=201)
    mock_resp.json.return_value = {"id": 42, "sku": "SKU-001", "name": "Widget"}

    with patch("httpx.post", return_value=mock_resp):
        from app.services.woocommerce_service import push_product
        mapping = push_product(db, woo_channel, product)
        assert mapping.external_product_id == "42"
        assert mapping.channel_id == woo_channel.id


def test_push_product_updates_existing(db, tenant: Tenant, woo_channel: Channel, product: Product) -> None:
    db.add(ChannelProductMapping(
        tenant_id=tenant.id, channel_id=woo_channel.id,
        product_id=product.id, external_product_id="42",
    ))
    db.flush()

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": 42, "sku": "SKU-001", "name": "Widget"}

    with patch("httpx.put", return_value=mock_resp):
        from app.services.woocommerce_service import push_product
        mapping = push_product(db, woo_channel, product)
        assert mapping.external_product_id == "42"


def test_get_woocommerce_products_parses_response(db, woo_channel: Channel) -> None:
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"id": 1, "name": "Widget A", "sku": "SKU-A", "price": "19.99"},
        {"id": 2, "name": "Widget B", "sku": "SKU-B", "price": "29.99"},
    ]

    with patch("httpx.get", return_value=mock_resp):
        from app.services.woocommerce_service import get_woocommerce_products
        products = get_woocommerce_products(woo_channel)
        assert len(products) == 2


def test_verify_webhook_signature_valid() -> None:
    secret = "whs_test"
    body = b'{"id": 12345}'
    digest = base64.b64encode(
        hmac_mod.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    from app.services.woocommerce_service import verify_webhook_signature
    assert verify_webhook_signature(body, digest, secret) is True


def test_verify_webhook_signature_invalid() -> None:
    from app.services.woocommerce_service import verify_webhook_signature
    assert verify_webhook_signature(b'{"id": 12345}', "bad_sig", "secret") is False


def test_import_woocommerce_catalog(db, tenant: Tenant, woo_channel: Channel, product: Product) -> None:
    woo_products = [
        {"id": 100, "name": "Widget", "sku": "SKU-001", "price": "19.99", "status": "publish"},
        {"id": 200, "name": "New Item", "sku": "NEW-001", "price": "9.99", "status": "publish"},
        {"id": 300, "name": "No SKU", "sku": "", "price": "5.00", "status": "publish"},
    ]

    from app.services.woocommerce_service import import_woocommerce_catalog
    result = import_woocommerce_catalog(db, woo_channel, woo_products)
    assert result["matched"] == 1
    assert result["created"] == 1
    assert result["skipped"] == 1
