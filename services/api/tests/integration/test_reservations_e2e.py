"""End-to-end smoke test for the stock reservation engine.

Covers:
- Reserve → available stock drops by reserved quantity
- Commit → reservation flips to 'committed', stock_movement created with
  source_channel_id, available stock unchanged from commit (because the
  reservation no longer subtracts AND a new movement decremented stock)
- Release → reservation flips to 'released', available stock recovers
- Expire path: past-expires_at active reservation is excluded from
  available_stock immediately; sweep_expired flips its status
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement,
    StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="manual", name=f"E2E channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD", shop_id=None,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product_with_10_stock(db, tenant: Tenant, shop: Shop) -> Product:
    p = Product(tenant_id=tenant.id, name="E2E Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=p.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.flush()
    return p


def test_full_lifecycle_reserve_commit(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """Reserve 3 → available=7. Commit → status='committed', movement created, available=7 (10 stock - 3 sold)."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import commit_reservation, reserve

    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 10

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=3, cart_token="cart_lifecycle_commit",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 7

    movement = commit_reservation(db, res.id)
    db.flush()
    assert movement is not None
    assert movement.quantity_delta == -3
    assert movement.source_channel_id == channel.id

    db.refresh(res)
    assert res.status == "committed"
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 7


def test_full_lifecycle_reserve_release(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """Reserve → available drops, release → recovers."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import release_reservation, reserve

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=4, cart_token="cart_lifecycle_release",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 6

    release_reservation(db, res.id)
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 10


def test_full_lifecycle_reserve_expire(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """An active reservation past expires_at no longer holds stock; sweep_expired flips status."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import sweep_expired

    expired = StockReservation(
        tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=2, cart_token="cart_lifecycle_expire",
        purpose="cart", status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(expired)
    db.flush()

    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 10

    count = sweep_expired(db)
    assert count == 1

    db.refresh(expired)
    assert expired.status == "expired"


def test_idempotent_reserve_updates_quantity(db, tenant: Tenant, shop: Shop, channel: Channel, product_with_10_stock: Product) -> None:
    """Re-reserving the same (channel, cart_token, product, shop) updates quantity, doesn't create a new row."""
    from app.services.inventory_pool_service import available_stock_for_channel
    from app.services.reservation_service import reserve

    reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=2, cart_token="cart_idem_e2e",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 8

    reserve(
        db, tenant_id=tenant.id, channel_id=channel.id,
        product_id=product_with_10_stock.id, shop_id=shop.id,
        quantity=5, cart_token="cart_idem_e2e",
    )
    db.flush()
    assert available_stock_for_channel(db, channel.id, product_with_10_stock.id) == 5
