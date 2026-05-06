import uuid
from decimal import Decimal

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Product, ShippingRate, ShippingZone, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def physical_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1000, product_type="physical", weight_grams=500,
        shipping_class="standard",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def digital_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="eBook", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="digital",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def domestic_zone(db, tenant: Tenant, channel: Channel) -> ShippingZone:
    z = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Domestic", countries=["IN"], is_catch_all=False,
    )
    db.add(z)
    db.flush()
    return z


def _add_rate(db, zone, *, name, base_price, currency="INR", **kwargs) -> ShippingRate:
    r = ShippingRate(
        tenant_id=zone.tenant_id, zone_id=zone.id,
        name=name, base_price_cents=base_price, currency_code=currency,
        **kwargs,
    )
    db.add(r)
    db.flush()
    return r


def test_returns_matching_zone_rate(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db,
        channel_id=channel.id,
        destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000,
        currency="INR",
    )
    assert len(options) == 1
    assert options[0]["name"] == "Standard"
    assert options[0]["price_cents"] == 9900
    assert options[0]["is_free"] is False


def test_no_matching_zone_returns_empty(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Standard", base_price=9900)

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="US",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="INR",
    )
    assert options == []


def test_catch_all_zone_matches_any_country(db, tenant: Tenant, channel: Channel, physical_product: Product) -> None:
    catch_all = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Rest of World", countries=[], is_catch_all=True,
    )
    db.add(catch_all)
    db.flush()
    _add_rate(db, catch_all, name="International", base_price=49900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="DE",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="INR",
    )
    assert len(options) == 1
    assert options[0]["name"] == "International"


def test_free_above_threshold(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Free Standard", base_price=9900,
              currency="INR", free_above_cents=50000)

    from app.services.shipping_service import calculate_shipping_options
    below = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=40000, currency="INR",
    )
    assert below[0]["is_free"] is False
    assert below[0]["price_cents"] == 9900

    above = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=60000, currency="INR",
    )
    assert above[0]["is_free"] is True
    assert above[0]["price_cents"] == 0


def test_condition_by_total_filters_rate(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Mid-range rate", base_price=4900, currency="INR",
              condition_type="by_total", condition_min=5000, condition_max=10000)

    from app.services.shipping_service import calculate_shipping_options
    out_range = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=4000, currency="INR",
    )
    assert out_range == []

    in_range = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=7000, currency="INR",
    )
    assert len(in_range) == 1


def test_digital_only_cart_returns_no_rates(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, digital_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": digital_product.id, "quantity": 1, "unit_price_cents": 500}],
        cart_subtotal_cents=500, currency="INR",
    )
    assert options == []


def test_shipping_class_filter(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Fragile Rate", base_price=19900, currency="INR",
              applies_to_classes=["fragile"])
    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="INR",
    )
    names = {o["name"] for o in options}
    assert "Standard" in names
    assert "Fragile Rate" not in names


def test_rate_price_converted_to_requested_currency(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    from app.billing.fx import set_rate
    set_rate(db, tenant.id, "INR", "USD", Decimal("0.012"))
    db.flush()

    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="USD",
    )
    assert len(options) == 1
    assert options[0]["currency_code"] == "USD"
    assert options[0]["price_cents"] == 119  # 9900 * 0.012 = 118.8 → 119
