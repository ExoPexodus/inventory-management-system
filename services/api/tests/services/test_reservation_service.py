import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement,
    StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    """Mirror migration: POS channel + single-shop pool for the test shop."""
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
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1000,
    )
    db.add(p)
    db.flush()
    return p


def test_reserve_creates_active_row_with_default_ttl(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import reserve

    res = reserve(
        db,
        tenant_id=tenant.id,
        channel_id=channel.id,
        product_id=product.id,
        shop_id=shop.id,
        quantity=2,
        cart_token="cart_abc",
        purpose="cart",
    )
    assert res.status == "active"
    assert res.quantity == 2
    assert res.purpose == "cart"
    delta = (res.expires_at - datetime.now(UTC)).total_seconds()
    assert 800 < delta < 1000  # ~900s


def test_reserve_uses_payment_ttl_when_purpose_is_payment_pending(
    db, tenant: Tenant, shop: Shop, channel: Channel, product: Product,
) -> None:
    from app.services.reservation_service import reserve

    res = reserve(
        db,
        tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_pay",
        purpose="payment_pending",
    )
    delta = (res.expires_at - datetime.now(UTC)).total_seconds()
    assert 86_000 < delta < 87_000


def test_reserve_uses_channel_config_override(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import reserve

    channel.config = {"cart_ttl_seconds": 60}
    db.flush()

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_override",
    )
    delta = (res.expires_at - datetime.now(UTC)).total_seconds()
    assert 50 < delta < 70


def test_reserve_is_idempotent_for_same_cart_line(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from sqlalchemy import select
    from app.services.reservation_service import reserve

    first = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=2, cart_token="cart_idem",
    )
    second = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=5, cart_token="cart_idem",
    )
    assert first.id == second.id
    assert second.quantity == 5

    rows = db.execute(
        select(StockReservation).where(StockReservation.cart_token == "cart_idem")
    ).scalars().all()
    assert len(rows) == 1


def test_commit_converts_reservation_to_stock_movement(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import reserve, commit_reservation

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=3, cart_token="cart_commit",
    )

    movement = commit_reservation(db, res.id)
    assert movement is not None
    assert movement.quantity_delta == -3
    assert movement.movement_type == "sale"
    assert movement.shop_id == shop.id
    assert movement.product_id == product.id
    assert movement.source_channel_id == channel.id

    db.refresh(res)
    assert res.status == "committed"


def test_release_marks_reservation_released(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import reserve, release_reservation

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_release",
    )
    release_reservation(db, res.id)
    db.refresh(res)
    assert res.status == "released"


def test_sweep_expired_marks_past_due_active_rows(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import sweep_expired

    expired = StockReservation(
        tenant_id=tenant.id,
        channel_id=channel.id,
        product_id=product.id,
        shop_id=shop.id,
        quantity=1,
        cart_token="cart_old",
        purpose="cart",
        status="active",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(expired)
    fresh = StockReservation(
        tenant_id=tenant.id,
        channel_id=channel.id,
        product_id=product.id,
        shop_id=shop.id,
        quantity=1,
        cart_token="cart_fresh",
        purpose="cart",
        status="active",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    db.add(fresh)
    db.flush()

    count = sweep_expired(db)
    assert count == 1

    db.refresh(expired)
    db.refresh(fresh)
    assert expired.status == "expired"
    assert fresh.status == "active"


def test_commit_returns_none_for_already_committed(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.reservation_service import reserve, commit_reservation

    res = reserve(
        db, tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_double",
    )
    movement1 = commit_reservation(db, res.id)
    assert movement1 is not None

    movement2 = commit_reservation(db, res.id)
    assert movement2 is None  # Already committed
