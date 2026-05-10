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


def get_committed_to_transfers(db: Session, shop_id: UUID, product_id: UUID) -> int:
    """Return quantity committed to outbound transfers (approved/in_transit) for a shop+product.

    This delegates to the transfer_orders service to avoid circular imports.
    """
    from app.services.transfer_orders import get_committed_to_transfers as _committed  # noqa: PLC0415
    return _committed(db, shop_id=shop_id, product_id=product_id)
