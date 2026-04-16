"""Tenant-facing billing endpoints.

Serves subscription status, usage, invoices, and app download info
to tenant admins through the admin-web dashboard.
Reads from the local license cache (synced from platform service).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Employee, Shop, Tenant, TenantLicenseCache

router = APIRouter(prefix="/v1/admin/billing", tags=["Admin Billing"])


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Legacy token not allowed")
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BillingStatusOut(BaseModel):
    subscription_status: str
    plan_codename: str
    billing_cycle: str | None
    active_addons: list[str]
    max_shops: int
    max_employees: int
    storage_limit_mb: int
    trial_ends_at: str | None
    current_period_end: str | None
    grace_period_days: int
    is_in_grace_period: bool
    last_synced_at: str | None


class UsageOut(BaseModel):
    shops_used: int
    shops_limit: int
    employees_used: int
    employees_limit: int
    storage_used_mb: int
    storage_limit_mb: int


class AppDownloadOut(BaseModel):
    download_token: str | None
    download_url_template: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=BillingStatusOut, dependencies=[require_permission("settings:read")])
def get_billing_status(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BillingStatusOut:
    tenant_id = _require_tenant(ctx)
    cache = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)
    ).scalar_one_or_none()

    if cache is None:
        return BillingStatusOut(
            subscription_status="unknown",
            plan_codename="unknown",
            billing_cycle=None,
            active_addons=[],
            max_shops=0,
            max_employees=0,
            storage_limit_mb=0,
            trial_ends_at=None,
            current_period_end=None,
            grace_period_days=0,
            is_in_grace_period=False,
            last_synced_at=None,
        )

    return BillingStatusOut(
        subscription_status=cache.subscription_status,
        plan_codename=cache.plan_codename,
        billing_cycle=cache.billing_cycle,
        active_addons=cache.active_addons or [],
        max_shops=cache.max_shops,
        max_employees=cache.max_employees,
        storage_limit_mb=cache.storage_limit_mb,
        trial_ends_at=cache.trial_ends_at.isoformat() if cache.trial_ends_at else None,
        current_period_end=cache.current_period_end.isoformat() if cache.current_period_end else None,
        grace_period_days=cache.grace_period_days,
        is_in_grace_period=cache.is_in_grace_period,
        last_synced_at=cache.last_synced_at.isoformat() if cache.last_synced_at else None,
    )


@router.get("/usage", response_model=UsageOut, dependencies=[require_permission("settings:read")])
def get_billing_usage(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> UsageOut:
    tenant_id = _require_tenant(ctx)

    shops_used = db.execute(
        select(func.count(Shop.id)).where(Shop.tenant_id == tenant_id)
    ).scalar_one()

    employees_used = db.execute(
        select(func.count(Employee.id)).where(
            Employee.tenant_id == tenant_id,
            Employee.is_active.is_(True),
        )
    ).scalar_one()

    cache = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)
    ).scalar_one_or_none()

    return UsageOut(
        shops_used=shops_used,
        shops_limit=cache.max_shops if cache else 999,
        employees_used=employees_used,
        employees_limit=cache.max_employees if cache else 999,
        storage_used_mb=0,  # TODO: calculate actual storage usage
        storage_limit_mb=cache.storage_limit_mb if cache else 999,
    )


@router.get("/app-downloads", response_model=AppDownloadOut, dependencies=[require_permission("settings:read")])
def get_app_downloads(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> AppDownloadOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return AppDownloadOut(
        download_token=tenant.download_token,
        download_url_template="/downloads/{token}",
    )
