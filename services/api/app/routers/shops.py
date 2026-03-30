from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import Shop

router = APIRouter(prefix="/v1/shops", tags=["Shops"])


class ShopOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str


@router.get("", response_model=list[ShopOut])
def list_shops(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[ShopOut]:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant-scoped operator required")
    if tenant_id is not None and tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")
    tenant_id = ctx.tenant_id
    stmt = select(Shop).order_by(Shop.created_at.desc())
    stmt = stmt.where(Shop.tenant_id == tenant_id)
    rows = db.execute(stmt).scalars().all()
    return [ShopOut(id=s.id, tenant_id=s.tenant_id, name=s.name) for s in rows]

