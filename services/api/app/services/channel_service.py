"""Channel resolution helpers.

A POS-type channel exists 1:1 with a Shop. Existing shops got their POS channels
auto-created during migration; new shops created after the migration get one
created on first need (typically the first sale through that shop).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


def get_pos_channel_for_shop(db: Session, shop_id: UUID) -> Channel | None:
    """Return the POS channel for a given shop, or None if there isn't one yet."""
    return db.execute(
        select(Channel).where(Channel.shop_id == shop_id, Channel.type == "pos")
    ).scalar_one_or_none()


def get_or_create_pos_channel(db: Session, shop: Shop) -> Channel:
    """Return the shop's POS channel, creating it (and its single-shop pool) on demand.

    Used when a new shop is created post-migration and a sale happens before any
    explicit channel-management call has wired up the channel for it.
    """
    existing = get_pos_channel_for_shop(db, shop.id)
    if existing is not None:
        return existing

    # Resolve tenant currency. Column is `default_currency_code` on tenants.
    tenant = db.get(Tenant, shop.tenant_id)
    currency = (tenant.default_currency_code if tenant and tenant.default_currency_code else "USD")

    # Create a single-shop pool first (channel FK requires it to exist)
    pool = InventoryPool(
        tenant_id=shop.tenant_id,
        name=f"POS at {shop.name}",
        fulfillment_policy="fulfill_from_primary",
    )
    db.add(pool)
    db.flush()

    db.add(InventoryPoolShop(
        tenant_id=shop.tenant_id,
        pool_id=pool.id,
        shop_id=shop.id,
    ))
    db.flush()

    channel = Channel(
        tenant_id=shop.tenant_id,
        type="pos",
        name=f"POS at {shop.name}",
        status="active",
        config={},
        inventory_pool_id=pool.id,
        currency_code=currency,
        shop_id=shop.id,
    )
    db.add(channel)
    db.flush()
    return channel
