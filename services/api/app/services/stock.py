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
