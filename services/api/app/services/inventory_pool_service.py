"""Inventory pool helpers — default pool, membership lookup, available-stock calc.

`available_stock_for_channel` is the central function that channel-aware code
will consume. It SUMs `stock_movements.quantity_delta` across all shops in the
channel's pool, for the given product. (Soft reservations are NOT subtracted
yet; that hooks in when the stock-reservation engine sub-project ships.)
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Channel, InventoryPool, InventoryPoolShop, StockMovement


def default_pool_for_tenant(db: Session, tenant_id: UUID) -> InventoryPool | None:
    """Return the tenant's "All Shops" default pool."""
    return db.execute(
        select(InventoryPool).where(
            InventoryPool.tenant_id == tenant_id,
            InventoryPool.name == "All Shops",
        )
    ).scalar_one_or_none()


def pool_shops(db: Session, pool_id: UUID) -> list[UUID]:
    """Return the shop_ids that belong to a pool."""
    rows = db.execute(
        select(InventoryPoolShop.shop_id).where(InventoryPoolShop.pool_id == pool_id)
    ).scalars().all()
    return list(rows)


def available_stock_for_channel(
    db: Session,
    channel_id: UUID,
    product_id: UUID,
) -> int:
    """Return the available stock for a product on a channel.

    Sums stock_movements.quantity_delta across all shops in the channel's pool.
    Returns 0 if the channel doesn't exist or has no pool members.

    Soft reservations are NOT subtracted yet. When the stock reservation engine
    sub-project ships, this function gains a `- sum(active_reservations)` term.
    """
    channel = db.get(Channel, channel_id)
    if channel is None:
        return 0

    shop_ids = pool_shops(db, channel.inventory_pool_id)
    if not shop_ids:
        return 0

    total = db.execute(
        select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
        .where(
            StockMovement.product_id == product_id,
            StockMovement.shop_id.in_(shop_ids),
        )
    ).scalar_one()
    return int(total or 0)
