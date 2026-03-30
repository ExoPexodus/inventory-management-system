from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import Shop, Transaction

router = APIRouter(prefix="/v1/reporting", tags=["Reporting"])


class ShopSalesSummary(BaseModel):
    shop_id: UUID
    shop_name: str
    sale_count: int
    gross_cents: int


@router.get("/sales-summary", response_model=list[ShopSalesSummary])
def sales_summary(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[ShopSalesSummary]:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant-scoped operator required",
        )
    if tenant_id is not None and tenant_id != ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access is forbidden",
        )
    effective_tenant = ctx.tenant_id
    shops = db.execute(select(Shop).where(Shop.tenant_id == effective_tenant)).scalars().all()
    out: list[ShopSalesSummary] = []
    for s in shops:
        count = db.execute(
            select(func.count()).select_from(Transaction).where(
                Transaction.shop_id == s.id,
                Transaction.status == "posted",
            )
        ).scalar_one()
        gross = db.execute(
            select(func.coalesce(func.sum(Transaction.total_cents), 0)).where(
                Transaction.shop_id == s.id,
                Transaction.status == "posted",
            )
        ).scalar_one()
        out.append(
            ShopSalesSummary(
                shop_id=s.id,
                shop_name=s.name,
                sale_count=int(count),
                gross_cents=int(gross),
            )
        )
    return out

