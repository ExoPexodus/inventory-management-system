from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.db.session import get_db
from app.models import Tenant

router = APIRouter(prefix="/v1/tenants", tags=["Tenants"])


class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None = None
    offline_tier: str
    max_offline_minutes: int


class TenantLookupOut(BaseModel):
    id: UUID
    name: str
    slug: str


@router.get("/by-slug/{slug}", response_model=TenantLookupOut)
def get_tenant_by_slug(slug: str, db: Annotated[Session, Depends(get_db)]) -> TenantLookupOut:
    row = db.execute(select(Tenant).where(Tenant.slug == slug.strip().lower())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantLookupOut(id=row.id, name=row.name, slug=row.slug)


@router.get("", response_model=list[TenantOut])
def list_tenants(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TenantOut]:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant-scoped operator required")
    rows = db.execute(
        select(Tenant).where(Tenant.id == ctx.tenant_id).order_by(Tenant.created_at.desc())
    ).scalars().all()
    return [
        TenantOut(
            id=t.id,
            name=t.name,
            slug=t.slug,
            default_currency_code=t.default_currency_code,
            currency_exponent=t.currency_exponent,
            currency_symbol_override=t.currency_symbol_override,
            offline_tier=t.offline_tier,
            max_offline_minutes=t.max_offline_minutes,
        )
        for t in rows
    ]


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TenantOut:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant-scoped operator required")
    if tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")
    t = db.get(Tenant, tenant_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantOut(
        id=t.id,
        name=t.name,
        slug=t.slug,
        default_currency_code=t.default_currency_code,
        currency_exponent=t.currency_exponent,
        currency_symbol_override=t.currency_symbol_override,
        offline_tier=t.offline_tier,
        max_offline_minutes=t.max_offline_minutes,
    )

