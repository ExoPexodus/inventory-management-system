"""Tenant-facing billing endpoints.

Serves subscription status, usage, invoices, and self-service billing actions
to tenant admins through the admin-web dashboard.

Read-only data comes from the local license cache.
Write operations (upgrade, cancel, renew) proxy to the platform service via HMAC-signed HTTP.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.config import settings
from app.db.admin_deps_db import get_db_admin
from app.models import Employee, Shop, Tenant, TenantLicenseCache
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/billing", tags=["Admin Billing"])


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Legacy token not allowed")
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _platform_headers(tenant_id: UUID) -> dict[str, str]:
    """Build HMAC auth headers for platform service calls."""
    ts = str(int(time.time()))
    msg = f"{ts}|{tenant_id}"
    sig = hmac.new(settings.platform_api_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {"X-Platform-Auth": sig, "X-Platform-Timestamp": ts}


def _platform_get(path: str, tenant_id: UUID) -> dict | list | None:
    """GET from platform service with HMAC auth."""
    if not settings.platform_api_url:
        return None
    try:
        resp = httpx.get(
            f"{settings.platform_api_url}{path}",
            headers=_platform_headers(tenant_id),
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        logger.warning("Platform service unreachable for %s", path, exc_info=True)
        return None


def _platform_post(path: str, tenant_id: UUID, body: dict | None = None) -> tuple[int, dict]:
    """POST to platform service with operator JWT. Returns (status_code, response_json)."""
    if not settings.platform_api_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Platform service not configured")
    try:
        resp = httpx.post(
            f"{settings.platform_api_url}{path}",
            headers={**_platform_headers(tenant_id), "Content-Type": "application/json"},
            json=body or {},
            timeout=10.0,
        )
        return resp.status_code, resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"detail": resp.text}
    except Exception as e:
        logger.warning("Platform service unreachable for POST %s", path, exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Platform service unavailable")


def _platform_patch(path: str, tenant_id: UUID, body: dict) -> tuple[int, dict]:
    """PATCH to platform service."""
    if not settings.platform_api_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Platform service not configured")
    try:
        resp = httpx.patch(
            f"{settings.platform_api_url}{path}",
            headers={**_platform_headers(tenant_id), "Content-Type": "application/json"},
            json=body,
            timeout=10.0,
        )
        return resp.status_code, resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"detail": resp.text}
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Platform service unavailable")


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


class PlanOptionOut(BaseModel):
    id: str
    codename: str
    display_name: str
    description: str | None
    base_price_cents: int
    currency_code: str
    yearly_discount_pct: int
    max_shops: int
    max_employees: int
    storage_limit_mb: int


class AddonOptionOut(BaseModel):
    id: str
    codename: str
    display_name: str
    description: str | None
    price_cents: int
    currency_code: str
    is_active_on_subscription: bool


class InvoiceOut(BaseModel):
    id: str
    invoice_number: str
    status: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency_code: str
    issued_at: str | None
    line_items: list[dict]


class AppDownloadOut(BaseModel):
    download_token: str | None
    download_base_url: str | None


class UpgradePlanRequest(BaseModel):
    plan_codename: str


class ChangeCycleRequest(BaseModel):
    billing_cycle: str  # "monthly" or "yearly"


class ToggleAddonRequest(BaseModel):
    addon_codename: str
    enable: bool


class BillingDetailsIn(BaseModel):
    company_name: str | None = None
    gstin: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


class BillingDetailsOut(BaseModel):
    company_name: str | None
    gstin: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None


# ---------------------------------------------------------------------------
# Read-only endpoints (from local cache)
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
    shops_used = db.execute(select(func.count(Shop.id)).where(Shop.tenant_id == tenant_id)).scalar_one()
    employees_used = db.execute(
        select(func.count(Employee.id)).where(Employee.tenant_id == tenant_id, Employee.is_active.is_(True))
    ).scalar_one()
    cache = db.execute(select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)).scalar_one_or_none()

    return UsageOut(
        shops_used=shops_used,
        shops_limit=cache.max_shops if cache else 999,
        employees_used=employees_used,
        employees_limit=cache.max_employees if cache else 999,
        storage_used_mb=0,
        storage_limit_mb=cache.storage_limit_mb if cache else 999,
    )


# ---------------------------------------------------------------------------
# Available plans & addons (proxied from platform)
# ---------------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanOptionOut], dependencies=[require_permission("settings:read")])
def get_available_plans(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[PlanOptionOut]:
    tenant_id = _require_tenant(ctx)
    data = _platform_get("/v1/platform/tenant-api/plans", tenant_id)
    if data is None:
        return []
    return [
        PlanOptionOut(
            id=p["id"], codename=p["codename"], display_name=p["display_name"],
            description=p.get("description"), base_price_cents=p["base_price_cents"],
            currency_code=p["currency_code"], yearly_discount_pct=p.get("yearly_discount_pct", 0),
            max_shops=p["max_shops"], max_employees=p["max_employees"], storage_limit_mb=p["storage_limit_mb"],
        )
        for p in data if p.get("is_active", True)
    ]


@router.get("/addons", response_model=list[AddonOptionOut], dependencies=[require_permission("settings:read")])
def get_available_addons(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[AddonOptionOut]:
    tenant_id = _require_tenant(ctx)
    cache = db.execute(select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)).scalar_one_or_none()
    active_addons = set(cache.active_addons or []) if cache else set()

    data = _platform_get("/v1/platform/tenant-api/addons", tenant_id)
    if data is None:
        return []
    return [
        AddonOptionOut(
            id=a["id"], codename=a["codename"], display_name=a["display_name"],
            description=a.get("description"), price_cents=a["price_cents"],
            currency_code=a["currency_code"],
            is_active_on_subscription=a["codename"] in active_addons,
        )
        for a in data if a.get("is_active", True)
    ]


# ---------------------------------------------------------------------------
# Invoices (proxied from platform)
# ---------------------------------------------------------------------------


@router.get("/invoices", response_model=list[InvoiceOut], dependencies=[require_permission("settings:read")])
def get_invoices(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[InvoiceOut]:
    tenant_id = _require_tenant(ctx)
    data = _platform_get(f"/v1/platform/tenant-api/tenants/{tenant_id}/invoices", tenant_id)
    if data is None:
        return []
    return [
        InvoiceOut(
            id=inv["id"], invoice_number=inv["invoice_number"], status=inv["status"],
            subtotal_cents=inv["subtotal_cents"], tax_cents=inv["tax_cents"],
            total_cents=inv["total_cents"], currency_code=inv["currency_code"],
            issued_at=inv.get("issued_at"), line_items=inv.get("line_items", []),
        )
        for inv in data
    ]


# ---------------------------------------------------------------------------
# App downloads
# ---------------------------------------------------------------------------


@router.get("/app-downloads", response_model=AppDownloadOut, dependencies=[require_permission("settings:read")])
def get_app_downloads(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> AppDownloadOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    base_url = None
    if tenant.download_token and settings.platform_api_url:
        # In production, platform_api_url is the public-facing platform URL
        # For dev, we use the public port (8002)
        platform_public = settings.platform_api_url.replace("http://platform:8000", "http://localhost:8002")
        base_url = f"{platform_public}/downloads/{tenant.download_token}"
    return AppDownloadOut(
        download_token=tenant.download_token,
        download_base_url=base_url,
    )


# ---------------------------------------------------------------------------
# Billing details (stored on Tenant model — local)
# ---------------------------------------------------------------------------


@router.get("/details", response_model=BillingDetailsOut, dependencies=[require_permission("settings:read")])
def get_billing_details(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BillingDetailsOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return BillingDetailsOut(
        company_name=getattr(tenant, "billing_company_name", None),
        gstin=getattr(tenant, "billing_gstin", None),
        address_line1=getattr(tenant, "billing_address_line1", None),
        address_line2=getattr(tenant, "billing_address_line2", None),
        city=getattr(tenant, "billing_city", None),
        state=getattr(tenant, "billing_state", None),
        postal_code=getattr(tenant, "billing_postal_code", None),
        country=getattr(tenant, "billing_country", None),
    )


@router.put("/details", response_model=BillingDetailsOut, dependencies=[require_permission("settings:write")])
def update_billing_details(
    body: BillingDetailsIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BillingDetailsOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    for field in ["company_name", "gstin", "address_line1", "address_line2", "city", "state", "postal_code", "country"]:
        val = getattr(body, field, None)
        setattr(tenant, f"billing_{field}", val)

    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="update_billing_details", resource_type="tenant", resource_id=str(tenant_id))
    db.commit()
    db.refresh(tenant)
    return BillingDetailsOut(
        company_name=tenant.billing_company_name,
        gstin=tenant.billing_gstin,
        address_line1=tenant.billing_address_line1,
        address_line2=tenant.billing_address_line2,
        city=tenant.billing_city,
        state=tenant.billing_state,
        postal_code=tenant.billing_postal_code,
        country=tenant.billing_country,
    )


# ---------------------------------------------------------------------------
# Self-service actions (proxied to platform)
# ---------------------------------------------------------------------------


@router.post("/cancel", dependencies=[require_permission("settings:write")])
def cancel_subscription(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict:
    tenant_id = _require_tenant(ctx)
    code, data = _platform_post(f"/v1/platform/tenant-api/tenants/{tenant_id}/subscription/cancel", tenant_id)
    if code >= 400:
        raise HTTPException(status_code=code, detail=data.get("detail", "Failed to cancel"))
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="cancel_subscription", resource_type="subscription")
    db.commit()
    return {"status": "cancelled"}


@router.post("/renew", dependencies=[require_permission("settings:write")])
def renew_subscription(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict:
    tenant_id = _require_tenant(ctx)
    code, data = _platform_post(f"/v1/platform/tenant-api/tenants/{tenant_id}/subscription/activate", tenant_id)
    if code >= 400:
        raise HTTPException(status_code=code, detail=data.get("detail", "Failed to renew"))
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="renew_subscription", resource_type="subscription")
    db.commit()
    return {"status": "renewed"}


@router.post("/change-cycle", dependencies=[require_permission("settings:write")])
def change_billing_cycle(
    body: ChangeCycleRequest,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict:
    if body.billing_cycle not in ("monthly", "yearly"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="billing_cycle must be 'monthly' or 'yearly'")
    tenant_id = _require_tenant(ctx)
    code, data = _platform_patch(f"/v1/platform/tenant-api/tenants/{tenant_id}/subscription", tenant_id, {"billing_cycle": body.billing_cycle})
    if code >= 400:
        raise HTTPException(status_code=code, detail=data.get("detail", "Failed to change cycle"))
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="change_billing_cycle", resource_type="subscription", after={"billing_cycle": body.billing_cycle})
    db.commit()
    return {"billing_cycle": body.billing_cycle}
