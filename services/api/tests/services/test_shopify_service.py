import json
from unittest.mock import MagicMock, patch

import pytest

from app.models import Channel, ChannelProductMapping, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def shopify_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    import uuid
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="shopify", name="My Shopify Store",
        config={
            "shopify_shop_domain": "test-store.myshopify.com",
            "shopify_access_token": "shpat_test123",
            "shopify_api_secret": "shpss_test123",
            "shopify_location_id": "12345678",
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
        description="A fine widget",
    )
    db.add(p)
    db.flush()
    return p


def test_test_connection_success(db, shopify_channel: Channel) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"shop": {"name": "Test Store", "currency": "INR"}}

    with patch("httpx.get", return_value=mock_response):
        from app.services.shopify_service import test_connection
        result = test_connection(shopify_channel)
        assert result["success"] is True
        assert result["shop_name"] == "Test Store"


def test_test_connection_invalid_credentials(db, shopify_channel: Channel) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"errors": "Invalid API key"}

    with patch("httpx.get", return_value=mock_response):
        from app.services.shopify_service import ShopifyAuthError, test_connection
        with pytest.raises(ShopifyAuthError):
            test_connection(shopify_channel)


def test_push_product_creates_new(db, tenant: Tenant, shopify_channel: Channel, product: Product) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "product": {
            "id": 987654321,
            "variants": [{"id": 111222333, "sku": "SKU-001"}],
        }
    }

    with patch("httpx.post", return_value=mock_response):
        from app.services.shopify_service import push_product
        mapping = push_product(db, shopify_channel, product)
        assert mapping.external_product_id == "987654321"
        assert mapping.channel_id == shopify_channel.id
        assert mapping.product_id == product.id


def test_push_product_updates_existing(db, tenant: Tenant, shopify_channel: Channel, product: Product) -> None:
    db.add(ChannelProductMapping(
        tenant_id=tenant.id, channel_id=shopify_channel.id,
        product_id=product.id, external_product_id="987654321",
    ))
    db.flush()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "product": {"id": 987654321, "variants": [{"id": 111222333, "sku": "SKU-001"}]}
    }

    with patch("httpx.put", return_value=mock_response):
        from app.services.shopify_service import push_product
        mapping = push_product(db, shopify_channel, product)
        assert mapping.external_product_id == "987654321"


def test_push_inventory_level(db, shopify_channel: Channel) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"inventory_level": {"available": 10}}

    with patch("httpx.post", return_value=mock_response) as mock_post:
        from app.services.shopify_service import push_inventory_level
        push_inventory_level(shopify_channel, inventory_item_id="555666", quantity=10)
        assert mock_post.called
        body = json.loads(mock_post.call_args.kwargs.get("content", "{}"))
        assert body["location_id"] == 12345678
        assert body["inventory_item_id"] == "555666"
        assert body["available"] == 10


def test_get_shopify_products_parses_response(db, shopify_channel: Channel) -> None:
    shopify_products = [
        {"id": 111, "title": "Widget A", "variants": [{"sku": "SKU-A", "price": "19.99"}]},
        {"id": 222, "title": "Widget B", "variants": [{"sku": "SKU-B", "price": "29.99"}]},
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"products": shopify_products}

    with patch("httpx.get", return_value=mock_response):
        from app.services.shopify_service import get_shopify_products
        products = get_shopify_products(shopify_channel)
        assert len(products) == 2
        assert products[0]["id"] == 111


def test_verify_webhook_signature_valid() -> None:
    import base64
    import hashlib
    import hmac as hmac_mod
    secret = "test_secret"
    body = b'{"id": 12345}'
    digest = base64.b64encode(
        hmac_mod.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    from app.services.shopify_service import verify_webhook_signature
    assert verify_webhook_signature(body, digest, secret) is True


def test_verify_webhook_signature_invalid() -> None:
    from app.services.shopify_service import verify_webhook_signature
    assert verify_webhook_signature(b'{"id": 12345}', "bad_sig", "secret") is False
