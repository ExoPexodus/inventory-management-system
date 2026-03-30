from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import Product, Shop
from app.services.stock import current_quantity

router = APIRouter(prefix="/v1/notifications", tags=["Notifications"])


class StockAlertOut(BaseModel):
    shop_id: str
    shop_name: str
    product_id: str
    sku: str
    name: str
    quantity: int
    threshold: int


@router.get("/stock-alerts", response_model=list[StockAlertOut])
def stock_alerts(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    threshold: int = 5,
) -> list[StockAlertOut]:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant-scoped operator required",
        )
    out: list[StockAlertOut] = []
    shops = db.execute(select(Shop).where(Shop.tenant_id == ctx.tenant_id)).scalars().all()
    for shop in shops:
        prods = db.execute(select(Product).where(Product.tenant_id == shop.tenant_id, Product.active.is_(True))).scalars().all()
        for p in prods:
            q = current_quantity(db, shop.id, p.id)
            if q <= threshold:
                out.append(
                    StockAlertOut(
                        shop_id=str(shop.id),
                        shop_name=shop.name,
                        product_id=str(p.id),
                        sku=p.sku,
                        name=p.name,
                        quantity=q,
                        threshold=threshold,
                    )
                )
    return out

