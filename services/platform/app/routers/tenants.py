"""Tenant CRUD for the platform portal."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.db.session import get_db
from app.models import PlatformTenant
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/platform/tenants", tags=["Platform Tenants"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TenantCreate(BaseModel):
    name: str
    slug: str
    region: str = "in"
    api_base_url: str
    notes: str | None = None
    default_currency_code: str = Field(default="USD", min_length=3, max_length=3)
    currency_exponent: int = Field(default=2, ge=0, le=4)
    currency_symbol_override: str | None = Field(default=None, max_length=8)
    deployment_mode: str = Field(default="cloud", pattern="^(cloud|on_prem)$")


class TenantPatch(BaseModel):
    name: str | None = None
    region: str | None = None
    api_base_url: str | None = None
    notes: str | None = None
    deployment_mode: str | None = Field(default=None, pattern="^(cloud|on_prem)$")


class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    region: str
    api_base_url: str
    download_token: str
    notes: str | None
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    deployment_mode: str
    created_at: datetime
    updated_at: datetime


class TenantListResponse(BaseModel):
    items: list[TenantOut]
    total: int
    next_cursor: str | None = None


class TenantCurrencyOut(BaseModel):
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None


class PatchTenantCurrencyBody(BaseModel):
    default_currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    currency_exponent: int | None = Field(default=None, ge=0, le=4)
    currency_symbol_override: str | None = Field(default=None, max_length=8)

    model_config = {"extra": "forbid"}


class TenantCurrencyPatchResult(BaseModel):
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    push_status: str  # "success" | "failed" | "not_implemented"
    push_error: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=TenantListResponse)
def list_tenants(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    q: str | None = Query(default=None, description="Search by name or slug"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> TenantListResponse:
    stmt = select(PlatformTenant)
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(PlatformTenant.name.ilike(needle) | PlatformTenant.slug.ilike(needle))
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            stmt = stmt.where(PlatformTenant.created_at < cursor_dt)
        except ValueError:
            pass

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(PlatformTenant.created_at.desc()).limit(limit + 1)
    rows = list(db.execute(stmt).scalars().all())

    next_cur = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cur = rows[-1].created_at.isoformat()

    return TenantListResponse(
        items=[_to_out(t) for t in rows],
        total=total,
        next_cursor=next_cur,
    )


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantOut:
    tenant = PlatformTenant(
        name=body.name,
        slug=body.slug.lower().strip(),
        region=body.region,
        api_base_url=body.api_base_url,
        api_shared_secret=secrets.token_urlsafe(32),
        download_token=secrets.token_urlsafe(16),
        notes=body.notes,
        default_currency_code=body.default_currency_code,
        currency_exponent=body.currency_exponent,
        currency_symbol_override=body.currency_symbol_override,
        deployment_mode=body.deployment_mode,
    )
    db.add(tenant)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant slug already exists")

    write_audit(db, operator_id=ctx.operator_id, action="create_tenant", resource_type="tenant", resource_id=str(tenant.id))
    db.commit()
    db.refresh(tenant)
    return _to_out(tenant)


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantOut:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return _to_out(tenant)


@router.patch("/{tenant_id}", response_model=TenantOut)
def patch_tenant(
    tenant_id: UUID,
    body: TenantPatch,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantOut:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    patch = body.model_dump(exclude_unset=True)
    for key, val in patch.items():
        setattr(tenant, key, val)
    tenant.updated_at = datetime.now(UTC)

    write_audit(db, operator_id=ctx.operator_id, action="update_tenant", resource_type="tenant", resource_id=str(tenant_id), details=patch)
    db.commit()
    db.refresh(tenant)
    return _to_out(tenant)


@router.post("/{tenant_id}/regenerate-download-token", response_model=TenantOut)
def regenerate_download_token(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantOut:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.download_token = secrets.token_urlsafe(16)
    tenant.updated_at = datetime.now(UTC)
    write_audit(db, operator_id=ctx.operator_id, action="regenerate_download_token", resource_type="tenant", resource_id=str(tenant_id))
    db.commit()
    db.refresh(tenant)
    return _to_out(tenant)


@router.get("/{tenant_id}/currency", response_model=TenantCurrencyOut)
def get_tenant_currency(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantCurrencyOut:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantCurrencyOut(
        default_currency_code=tenant.default_currency_code,
        currency_exponent=tenant.currency_exponent,
        currency_symbol_override=tenant.currency_symbol_override,
    )


@router.patch("/{tenant_id}/currency", response_model=TenantCurrencyPatchResult)
def patch_tenant_currency(
    tenant_id: UUID,
    body: PatchTenantCurrencyBody,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantCurrencyPatchResult:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    sent = body.model_fields_set
    patch_data = body.model_dump(include=sent)
    for field, value in patch_data.items():
        setattr(tenant, field, value)

    write_audit(
        db,
        operator_id=ctx.operator_id,
        action="update_tenant_currency",
        resource_type="tenant",
        resource_id=str(tenant_id),
    )
    db.commit()
    db.refresh(tenant)

    # Push integration added in Task 6
    push_status = "not_implemented"
    push_error = None

    return TenantCurrencyPatchResult(
        default_currency_code=tenant.default_currency_code,
        currency_exponent=tenant.currency_exponent,
        currency_symbol_override=tenant.currency_symbol_override,
        push_status=push_status,
        push_error=push_error,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_out(t: PlatformTenant) -> TenantOut:
    return TenantOut(
        id=t.id,
        name=t.name,
        slug=t.slug,
        region=t.region,
        api_base_url=t.api_base_url,
        download_token=t.download_token,
        notes=t.notes,
        default_currency_code=t.default_currency_code,
        currency_exponent=t.currency_exponent,
        currency_symbol_override=t.currency_symbol_override,
        deployment_mode=t.deployment_mode,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )
