from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
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
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[ShopOut]:
    stmt = select(Shop).order_by(Shop.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(Shop.tenant_id == tenant_id)
    rows = db.execute(stmt).scalars().all()
    return [ShopOut(id=s.id, tenant_id=s.tenant_id, name=s.name) for s in rows]

