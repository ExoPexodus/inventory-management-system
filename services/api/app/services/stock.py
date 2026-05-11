from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StockMovement


def current_quantity(db: Session, shop_id: UUID, product_id: UUID) -> int:
    q = (
        select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
        .where(
            StockMovement.shop_id == shop_id,
            StockMovement.product_id == product_id,
        )
    )
    return int(db.execute(q).scalar_one())


def current_quantities(db: Session, shop_id: UUID, product_ids: Iterable[UUID]) -> dict[UUID, int]:
    """Batch version of current_quantity. Returns {product_id: qty} for every id in product_ids;
    missing rows are treated as 0."""
    ids = list(product_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(
            StockMovement.product_id,
            func.coalesce(func.sum(StockMovement.quantity_delta), 0),
        )
        .where(
            StockMovement.shop_id == shop_id,
            StockMovement.product_id.in_(ids),
        )
        .group_by(StockMovement.product_id)
    ).all()
    out: dict[UUID, int] = {pid: 0 for pid in ids}
    for pid, qty in rows:
        out[pid] = int(qty)
    return out


def get_committed_to_transfers(db: Session, shop_id: UUID, product_id: UUID) -> int:
    """Return quantity committed to outbound transfers (approved/in_transit) for a shop+product.

    This delegates to the transfer_orders service to avoid circular imports.
    """
    from app.services.transfer_orders import get_committed_to_transfers as _committed  # noqa: PLC0415
    return _committed(db, shop_id=shop_id, product_id=product_id)


def get_committed_to_transfers_batch(
    db: Session, shop_id: UUID, product_ids: Iterable[UUID],
) -> dict[UUID, int]:
    """Batch version. Returns {product_id: committed_qty} for every id in product_ids."""
    from app.services.transfer_orders import get_committed_to_transfers_batch as _committed_batch  # noqa: PLC0415
    return _committed_batch(db, shop_id=shop_id, product_ids=list(product_ids))
