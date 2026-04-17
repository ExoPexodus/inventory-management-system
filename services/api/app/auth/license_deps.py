"""Feature-gating dependencies — enforce license restrictions on API endpoints.

Matches the pattern of require_permission() from admin_deps.py.
Reads from the local tenant_license_cache table (populated by license_service.py).

Design choices:
- Fail-open for new tenants (no cache = allowed) to avoid chicken-and-egg on provisioning
- POS/cashier operations are never blocked — only admin-level features are gated
- 402 Payment Required for expired licenses, 403 for missing add-ons / exceeded limits
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import TenantLicenseCache


@dataclass
class LicenseContext:
    tenant_id: UUID
    status: str
    plan_codename: str
    active_addons: list[str] = field(default_factory=list)
    max_shops: int = 999
    max_employees: int = 999
    storage_limit_mb: int = 99999
    is_in_grace_period: bool = False
    cache_present: bool = False


def _load_license_context(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> LicenseContext:
    """Load license context from cache. Fail-open if no cache exists."""
    if ctx.is_legacy_token or ctx.tenant_id is None:
        # Legacy token or no tenant — unrestricted
        return LicenseContext(
            tenant_id=ctx.tenant_id or UUID(int=0),
            status="active",
            plan_codename="legacy",
        )

    cache = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == ctx.tenant_id)
    ).scalar_one_or_none()

    if cache is None:
        # No cache = never synced. Fail-open.
        return LicenseContext(
            tenant_id=ctx.tenant_id,
            status="unknown",
            plan_codename="unknown",
        )

    return LicenseContext(
        tenant_id=ctx.tenant_id,
        status=cache.subscription_status,
        plan_codename=cache.plan_codename,
        active_addons=cache.active_addons or [],
        max_shops=cache.max_shops,
        max_employees=cache.max_employees,
        storage_limit_mb=cache.storage_limit_mb,
        is_in_grace_period=cache.is_in_grace_period,
        cache_present=True,
    )


LicenseContextDep = Annotated[LicenseContext, Depends(_load_license_context)]


def require_license_active():
    """Dependency that rejects requests if the license is expired past grace period or suspended."""
    def _check(license_ctx: LicenseContextDep) -> LicenseContext:
        if not license_ctx.cache_present:
            return license_ctx  # fail-open
        if license_ctx.status in ("expired", "suspended", "cancelled"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Subscription {license_ctx.status}. Please renew to continue.",
            )
        return license_ctx
    return Depends(_check)


def require_addon(*codenames: str):
    """Dependency that checks at least one of the given add-ons is active."""
    def _check(license_ctx: LicenseContextDep) -> LicenseContext:
        if not license_ctx.cache_present:
            return license_ctx  # fail-open
        if license_ctx.status == "trial":
            return license_ctx  # trial gets all features
        if set(codenames).intersection(license_ctx.active_addons):
            return license_ctx
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This feature requires one of: {', '.join(codenames)}",
        )
    return Depends(_check)


def require_within_limit(resource: str):
    """Dependency that checks usage against licensed limits.

    Supported resources: 'max_shops', 'max_employees'.
    Counts the current usage from the database and compares to the cached limit.
    """
    def _check(
        license_ctx: LicenseContextDep,
        db: Annotated[Session, Depends(get_db_admin)],
    ) -> LicenseContext:
        if not license_ctx.cache_present:
            return license_ctx  # fail-open
        if license_ctx.status == "trial":
            return license_ctx  # trial = unlimited

        limit = getattr(license_ctx, resource, None)
        if limit is None:
            return license_ctx  # unknown resource — allow

        # Count current usage
        from app.models import Shop, User
        if resource == "max_shops":
            count = db.execute(
                select(func.count(Shop.id)).where(Shop.tenant_id == license_ctx.tenant_id)
            ).scalar_one()
        elif resource == "max_employees":
            count = db.execute(
                select(func.count(User.id)).where(
                    User.tenant_id == license_ctx.tenant_id,
                    User.is_active.is_(True),
                )
            ).scalar_one()
        else:
            return license_ctx

        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Limit reached: {resource} ({count}/{limit}). Upgrade your plan to add more.",
            )
        return license_ctx
    return Depends(_check)
