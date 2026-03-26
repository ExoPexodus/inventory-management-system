from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
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


@router.get("", response_model=list[TenantOut])
def list_tenants(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TenantOut]:
    rows = db.execute(select(Tenant).order_by(Tenant.created_at.desc())).scalars().all()
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
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TenantOut:
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

