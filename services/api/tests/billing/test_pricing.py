import uuid
from decimal import Decimal

import pytest

from app.billing.money import Money
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
        config={}, inventory_pool_id=pool.id, currency_code="USD", shop_id=None,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    """Product with unit_price_cents=1999 (in tenant default currency)."""
    p = Product(
        tenant_id=tenant.id, name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1999,
    )
    db.add(p)
    db.flush()
    return p


def test_explicit_channel_specific_price_wins(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """A ProductPrice with matching (product, channel, currency) is the highest priority."""
    from app.billing.pricing import price_for_product_in_currency

    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="USD", amount_cents=1999,
    ))
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=channel.id,
        currency_code="USD", amount_cents=1799,
    ))
    db.flush()

    price = price_for_product_in_currency(db, product.id, "USD", channel_id=channel.id)
    assert price == Money(1799, "USD")


def test_tenant_wide_price_when_no_channel_override(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """Falls back to the tenant-wide ProductPrice (channel_id IS NULL)."""
    from app.billing.pricing import price_for_product_in_currency

    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.flush()

    price = price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)
    assert price == Money(1899, "EUR")


def test_fx_fallback_uses_unit_price_with_rate(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """No ProductPrice for the currency → FX-derive from product.unit_price_cents."""
    from app.billing.fx import set_rate
    from app.billing.pricing import price_for_product_in_currency

    # Tenant default currency is USD. Set USD→INR rate.
    set_rate(db, tenant.id, "USD", "INR", Decimal("83.0"))
    db.flush()

    # 1999 USD cents × 83 = 165917 INR cents
    price = price_for_product_in_currency(db, product.id, "INR", channel_id=channel.id)
    assert price.currency_code == "INR"
    assert price.amount_cents == 165917


def test_no_price_no_rate_raises(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """Neither ProductPrice nor FX rate available → raise (caller decides UX)."""
    from app.billing.fx import FxRateMissingError
    from app.billing.pricing import price_for_product_in_currency

    with pytest.raises(FxRateMissingError):
        price_for_product_in_currency(db, product.id, "JPY", channel_id=channel.id)


def test_channel_id_none_skips_channel_lookup(db, tenant: Tenant, product: Product) -> None:
    """Calling without channel_id returns the tenant-wide price."""
    from app.billing.pricing import price_for_product_in_currency

    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.flush()

    price = price_for_product_in_currency(db, product.id, "EUR", channel_id=None)
    assert price == Money(1899, "EUR")


def test_unknown_product_raises(db, tenant: Tenant, channel: Channel) -> None:
    from app.billing.pricing import price_for_product_in_currency
    with pytest.raises(LookupError, match="product"):
        price_for_product_in_currency(db, uuid.uuid4(), "USD", channel_id=channel.id)
