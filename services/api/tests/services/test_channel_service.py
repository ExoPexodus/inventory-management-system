import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def shop_with_pos_channel(db, tenant: Tenant, shop: Shop) -> tuple[Shop, Channel]:
    # Test shops are created post-migration, so no POS channel is auto-created.
    # Build one here the same way the migration does: pool → pool_shop → channel.
    currency = (
        tenant.default_currency_code if tenant and tenant.default_currency_code else "USD"
    )
    pool = InventoryPool(
        tenant_id=tenant.id,
        name=f"POS at {shop.name}",
        fulfillment_policy="fulfill_from_primary",
    )
    db.add(pool)
    db.flush()

    db.add(InventoryPoolShop(
        tenant_id=tenant.id,
        pool_id=pool.id,
        shop_id=shop.id,
    ))
    db.flush()

    ch = Channel(
        tenant_id=tenant.id,
        type="pos",
        name=f"POS at {shop.name}",
        status="active",
        config={},
        inventory_pool_id=pool.id,
        currency_code=currency,
        shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return shop, ch


def test_get_pos_channel_for_shop_returns_existing(db, shop_with_pos_channel) -> None:
    from app.services.channel_service import get_pos_channel_for_shop
    shop, ch = shop_with_pos_channel
    found = get_pos_channel_for_shop(db, shop.id)
    assert found is not None
    assert found.id == ch.id
    assert found.type == "pos"
    assert found.shop_id == shop.id


def test_get_pos_channel_for_shop_returns_none_for_unknown(db, tenant: Tenant) -> None:
    from app.services.channel_service import get_pos_channel_for_shop
    assert get_pos_channel_for_shop(db, uuid.uuid4()) is None


def test_get_or_create_pos_channel_creates_when_missing(db, tenant: Tenant) -> None:
    """A new shop added after the migration won't have a POS channel until a sale happens.
    get_or_create_pos_channel handles that case by creating both the channel and a
    single-shop pool on demand."""
    from app.services.channel_service import get_or_create_pos_channel

    new_shop = Shop(tenant_id=tenant.id, name=f"new-shop-{uuid.uuid4().hex[:6]}")
    db.add(new_shop)
    db.flush()

    ch = get_or_create_pos_channel(db, new_shop)
    assert ch.type == "pos"
    assert ch.shop_id == new_shop.id
    assert ch.tenant_id == tenant.id
    # And the channel's pool is a single-shop pool with just this shop
    from sqlalchemy import select
    pool_shops = db.execute(
        select(InventoryPoolShop).where(InventoryPoolShop.pool_id == ch.inventory_pool_id)
    ).scalars().all()
    assert len(pool_shops) == 1
    assert pool_shops[0].shop_id == new_shop.id


def test_get_or_create_pos_channel_is_idempotent(db, shop_with_pos_channel) -> None:
    from app.services.channel_service import get_or_create_pos_channel
    shop, ch = shop_with_pos_channel
    again = get_or_create_pos_channel(db, shop)
    assert again.id == ch.id
