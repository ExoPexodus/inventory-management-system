import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement,
    StockReservation, Tenant,
)


@pytest.fixture()
def channel_with_pool(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
        type="pos",
        name=f"POS at {shop.name}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="USD",
        shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product_with_stock(db, tenant: Tenant, shop: Shop) -> Product:
    p = Product(tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=p.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.flush()
    return p


def _add_reservation(db, *, tenant_id, channel_id, product_id, shop_id, quantity, status, expires_at):
    db.add(StockReservation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        product_id=product_id,
        shop_id=shop_id,
        quantity=quantity,
        cart_token=f"cart-{uuid.uuid4().hex[:8]}",
        purpose="cart",
        status=status,
        expires_at=expires_at,
    ))
    db.flush()


def test_active_reservations_subtract_from_available(db, tenant: Tenant, shop: Shop, channel_with_pool: Channel, product_with_stock: Product) -> None:
    from app.services.inventory_pool_service import available_stock_for_channel

    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=3, status="active",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    assert available_stock_for_channel(db, channel_with_pool.id, product_with_stock.id) == 7


def test_expired_reservations_dont_subtract(db, tenant: Tenant, shop: Shop, channel_with_pool: Channel, product_with_stock: Product) -> None:
    from app.services.inventory_pool_service import available_stock_for_channel

    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=3, status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    assert available_stock_for_channel(db, channel_with_pool.id, product_with_stock.id) == 10


def test_committed_or_released_reservations_dont_subtract(db, tenant: Tenant, shop: Shop, channel_with_pool: Channel, product_with_stock: Product) -> None:
    from app.services.inventory_pool_service import available_stock_for_channel

    future = datetime.now(UTC) + timedelta(minutes=10)
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=2, status="committed", expires_at=future,
    )
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=2, status="released", expires_at=future,
    )
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel_with_pool.id,
        product_id=product_with_stock.id, shop_id=shop.id,
        quantity=2, status="expired", expires_at=future,
    )
    assert available_stock_for_channel(db, channel_with_pool.id, product_with_stock.id) == 10


def test_reservations_summed_across_pool_shops(db, tenant: Tenant) -> None:
    from app.services.inventory_pool_service import available_stock_for_channel

    shop_a = Shop(tenant_id=tenant.id, name=f"shop-a-{uuid.uuid4().hex[:6]}")
    shop_b = Shop(tenant_id=tenant.id, name=f"shop-b-{uuid.uuid4().hex[:6]}")
    db.add(shop_a)
    db.add(shop_b)
    db.flush()

    product = Product(tenant_id=tenant.id, name="Gadget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(product)
    db.flush()

    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop_a.id, product_id=product.id,
        quantity_delta=5, movement_type="purchase_receipt",
        idempotency_key=f"a-{uuid.uuid4().hex}",
    ))
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop_b.id, product_id=product.id,
        quantity_delta=5, movement_type="purchase_receipt",
        idempotency_key=f"b-{uuid.uuid4().hex}",
    ))
    db.flush()

    pool = InventoryPool(tenant_id=tenant.id, name=f"multi-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop_a.id))
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop_b.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="manual", name=f"multi-channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(channel)
    db.flush()

    future = datetime.now(UTC) + timedelta(minutes=10)
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product.id, shop_id=shop_a.id,
        quantity=1, status="active", expires_at=future,
    )
    _add_reservation(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product.id, shop_id=shop_b.id,
        quantity=2, status="active", expires_at=future,
    )

    assert available_stock_for_channel(db, channel.id, product.id) == 7
