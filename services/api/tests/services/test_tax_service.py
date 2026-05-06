import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Product, TaxRegion, TaxRule, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
        tax_included_in_price=False,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product_standard(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=11800, product_type="physical",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def product_exempt(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Book", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical", tax_class="exempt",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def india_region(db, tenant: Tenant) -> TaxRegion:
    r = TaxRegion(tenant_id=tenant.id, name="India GST", country_code="IN")
    db.add(r)
    db.flush()
    return r


def _add_rule(db, region, tax_class, label, components):
    rule = TaxRule(
        tenant_id=region.tenant_id, region_id=region.id,
        tax_class=tax_class, label=label, components=components,
    )
    db.add(rule)
    db.flush()
    return rule


def test_exclusive_tax_added_to_price(db, tenant: Tenant, channel: Channel, product_standard: Product, india_region: TaxRegion) -> None:
    _add_rule(db, india_region, "standard", "GST 18%",
              [{"label": "CGST", "rate_bps": 900}, {"label": "SGST", "rate_bps": 900}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 11800}],
        currency="INR",
    )
    assert result["total_tax_cents"] > 0
    line = result["lines"][0]
    assert line["tax_cents"] == 2124  # 11800 * 0.18 = 2124
    assert len(line["components"]) == 2
    assert line["components"][0]["label"] == "CGST"
    assert line["components"][0]["tax_cents"] == 1062


def test_inclusive_tax_extracted_from_price(db, tenant: Tenant, shop: Shop, product_standard: Product, india_region: TaxRegion) -> None:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    incl_channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"incl-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
        tax_included_in_price=True,
    )
    db.add(incl_channel)
    db.flush()

    _add_rule(db, india_region, "standard", "GST 18%", [{"label": "IGST", "rate_bps": 1800}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=incl_channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 11800}],
        currency="INR",
    )
    line = result["lines"][0]
    # Inclusive: tax = 11800 * 0.18 / 1.18 = 1800
    assert line["tax_cents"] == 1800


def test_exempt_product_has_zero_tax(db, tenant: Tenant, channel: Channel, product_exempt: Product, india_region: TaxRegion) -> None:
    _add_rule(db, india_region, "standard", "GST 18%", [{"label": "GST", "rate_bps": 1800}])
    _add_rule(db, india_region, "exempt", "GST exempt", [])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_exempt.id, "quantity": 1, "unit_price_cents": 10000}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 0
    assert result["lines"][0]["tax_cents"] == 0


def test_no_region_returns_zero_tax(db, tenant: Tenant, channel: Channel, product_standard: Product) -> None:
    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="DE",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 10000}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 0


def test_donation_product_is_exempt_by_default(db, tenant: Tenant, channel: Channel, india_region: TaxRegion) -> None:
    donation = Product(
        tenant_id=tenant.id, name="Donation", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="donation",
    )
    db.add(donation)
    db.flush()

    _add_rule(db, india_region, "standard", "GST 18%", [{"label": "GST", "rate_bps": 1800}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": donation.id, "quantity": 1, "unit_price_cents": 500}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 0


def test_quantity_multiplied_correctly(db, tenant: Tenant, channel: Channel, product_standard: Product, india_region: TaxRegion) -> None:
    _add_rule(db, india_region, "standard", "GST 5%", [{"label": "GST", "rate_bps": 500}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_standard.id, "quantity": 3, "unit_price_cents": 10000}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 1500  # 10000 * 5% * 3 = 1500


def test_state_specific_rule_preferred_over_country_rule(db, tenant: Tenant, channel: Channel, product_standard: Product) -> None:
    country_region = TaxRegion(tenant_id=tenant.id, name="India Generic", country_code="IN")
    state_region = TaxRegion(tenant_id=tenant.id, name="Maharashtra", country_code="IN", state_code="MH")
    db.add(country_region)
    db.add(state_region)
    db.flush()

    _add_rule(db, country_region, "standard", "GST 18%", [{"label": "GST", "rate_bps": 1800}])
    _add_rule(db, state_region, "standard", "GST 12%", [{"label": "GST", "rate_bps": 1200}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        destination_state="MH",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 10000}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 1200  # State rule wins
