"""Tenant CRUD for the platform portal."""

from __future__ import annotations

import secrets
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.db.session import get_db
from app.models import Plan, PlatformTenant, Subscription
from app.models.tables import TenantLimitOverride
from app.services.audit_service import write_audit
from app.services.feature_catalog import get_feature_catalog
from app.services.tenant_config_push import push_tenant_currency_config
from app.services.tenant_provision import provision_tenant

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
    initial_admin_email: str
    initial_admin_password: str = Field(min_length=8)
    # Storage configuration
    storage_mode: str = Field(default="platform", pattern="^(platform|byo)$")
    byo_storage_endpoint: str | None = None
    byo_storage_bucket: str | None = None
    byo_storage_access_key: str | None = None
    byo_storage_secret_key: str | None = None
    byo_storage_public_url: str | None = None
    byo_storage_region: str | None = "auto"
    # Billing configuration
    plan_codename: str = "starter"
    trial_days: int = Field(default=14, ge=0, le=90)


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

    # Validate plan and create initial Subscription
    plan = db.execute(
        select(Plan).where(Plan.codename == body.plan_codename, Plan.is_active == True)  # noqa: E712
    ).scalar_one_or_none()
    if plan is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{body.plan_codename}' not found or inactive",
        )

    now = datetime.now(UTC)
    trial_end = now + timedelta(days=body.trial_days) if body.trial_days > 0 else None
    sub = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status="trial" if trial_end else "active",
        billing_cycle="monthly",
        trial_ends_at=trial_end,
        current_period_start=now,
        current_period_end=trial_end or (now + timedelta(days=30)),
    )
    db.add(sub)
    db.flush()

    initial_license = {
        "subscription_status": sub.status,
        "plan_codename": plan.codename,
        "billing_cycle": sub.billing_cycle,
        "max_shops": plan.max_shops,
        "max_employees": plan.max_employees,
        "storage_limit_mb": plan.storage_limit_mb,
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "grace_period_days": sub.grace_period_days,
    }

    write_audit(db, operator_id=ctx.operator_id, action="create_tenant", resource_type="tenant", resource_id=str(tenant.id))

    # Provision the tenant in the main API (creates tenant + owner role + initial admin).
    # Roll back if the API call fails so no orphan platform tenant is created.
    result = provision_tenant(
        tenant,
        body.initial_admin_email,
        body.initial_admin_password,
        storage_mode=body.storage_mode,
        byo_storage_endpoint=body.byo_storage_endpoint,
        byo_storage_bucket=body.byo_storage_bucket,
        byo_storage_access_key=body.byo_storage_access_key,
        byo_storage_secret_key=body.byo_storage_secret_key,
        byo_storage_public_url=body.byo_storage_public_url,
        byo_storage_region=body.byo_storage_region,
        initial_license=initial_license,
    )
    if not result.ok:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Tenant created but API provisioning failed: {result.error}",
        )

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

    # Push tenant config to api (single attempt; failures logged and surfaced)
    push_result = push_tenant_currency_config(tenant)
    push_status = push_result.status
    push_error = push_result.error

    return TenantCurrencyPatchResult(
        default_currency_code=tenant.default_currency_code,
        currency_exponent=tenant.currency_exponent,
        currency_symbol_override=tenant.currency_symbol_override,
        push_status=push_status,
        push_error=push_error,
    )


# ---------------------------------------------------------------------------
# Overrides CRUD (per-tenant feature overrides)
# ---------------------------------------------------------------------------


class OverrideOut(BaseModel):
    id: UUID
    tenant_id: UUID
    limit_key: str
    value: Any
    reason: str | None
    created_at: datetime


class OverridePut(BaseModel):
    value: Any
    reason: str | None = None


class BulkOverrideBody(BaseModel):
    filter: dict[str, str | None] = {}
    feature_key: str
    value: Any
    reason: str | None = None


class BulkOverrideResult(BaseModel):
    count: int
    affected_tenant_ids: list[str]


def _override_value(o: TenantLimitOverride) -> Any:
    """Return the effective value for an override, preferring value_json."""
    if o.value_json is not None:
        v = o.value_json
        # If it came from the legacy backfill it's {"value": int}; unwrap that.
        if isinstance(v, dict) and list(v.keys()) == ["value"]:
            return v["value"]
        return v
    return o.limit_value


def _to_override_out(o: TenantLimitOverride) -> OverrideOut:
    return OverrideOut(
        id=o.id,
        tenant_id=o.tenant_id,
        limit_key=o.limit_key,
        value=_override_value(o),
        reason=o.reason,
        created_at=o.created_at,
    )


@router.get("/{tenant_id}/overrides", response_model=list[OverrideOut])
def list_overrides(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[OverrideOut]:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    rows = db.execute(
        select(TenantLimitOverride).where(TenantLimitOverride.tenant_id == tenant_id)
    ).scalars().all()
    return [_to_override_out(o) for o in rows]


@router.put("/{tenant_id}/overrides/{key}", response_model=OverrideOut)
def put_override(
    tenant_id: UUID,
    key: str,
    body: OverridePut,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> OverrideOut:
    """Upsert a feature override for a tenant. Validates key against the feature catalog."""
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Validate key against IMS catalog (best-effort)
    catalog = get_feature_catalog()
    if catalog and key not in catalog:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown feature key: {key!r}. Valid keys: {sorted(catalog.keys())}",
        )

    existing = db.execute(
        select(TenantLimitOverride).where(
            TenantLimitOverride.tenant_id == tenant_id,
            TenantLimitOverride.limit_key == key,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.value_json = body.value
        existing.reason = body.reason
        o = existing
    else:
        # Determine a safe integer sentinel for limit_value (required column)
        int_val = int(body.value) if isinstance(body.value, (int, float)) else 0
        o = TenantLimitOverride(
            id=_uuid.uuid4(),
            tenant_id=tenant_id,
            limit_key=key,
            limit_value=int_val,
            value_json=body.value,
            reason=body.reason,
        )
        db.add(o)

    write_audit(
        db, operator_id=ctx.operator_id, action="upsert_override",
        resource_type="tenant", resource_id=str(tenant_id),
        details={"key": key, "value": body.value},
    )
    db.commit()
    db.refresh(o)
    return _to_override_out(o)


@router.delete("/{tenant_id}/overrides/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_override(
    tenant_id: UUID,
    key: str,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Remove a feature override for a tenant."""
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    existing = db.execute(
        select(TenantLimitOverride).where(
            TenantLimitOverride.tenant_id == tenant_id,
            TenantLimitOverride.limit_key == key,
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")

    write_audit(
        db, operator_id=ctx.operator_id, action="delete_override",
        resource_type="tenant", resource_id=str(tenant_id),
        details={"key": key},
    )
    db.delete(existing)
    db.commit()


# ---------------------------------------------------------------------------
# Bulk overrides router (separate prefix)
# ---------------------------------------------------------------------------

bulk_router = APIRouter(prefix="/v1/platform/overrides", tags=["Platform Overrides"])


@bulk_router.post("/bulk", response_model=BulkOverrideResult)
def bulk_override(
    body: BulkOverrideBody,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> BulkOverrideResult:
    """Apply a feature override to all tenants matching the filter.

    Supported filter keys: plan_codename, region.
    (business_type is deferred to v2 — it lives on IMS-side Tenant, not platform.)
    """
    # Validate feature key (best-effort)
    catalog = get_feature_catalog()
    if catalog and body.feature_key not in catalog:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown feature key: {body.feature_key!r}",
        )

    stmt = (
        select(Subscription, PlatformTenant)
        .join(PlatformTenant, PlatformTenant.id == Subscription.tenant_id)
        .where(Subscription.cancelled_at.is_(None))
    )

    plan_codename = body.filter.get("plan_codename")
    region = body.filter.get("region")

    if plan_codename:
        plan = db.execute(
            select(Plan).where(Plan.codename == plan_codename)
        ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plan '{plan_codename}' not found",
            )
        stmt = stmt.where(Subscription.plan_id == plan.id)

    if region:
        stmt = stmt.where(PlatformTenant.region == region)

    results = db.execute(stmt).all()
    affected_ids: list[str] = []

    for sub, tenant in results:
        existing = db.execute(
            select(TenantLimitOverride).where(
                TenantLimitOverride.tenant_id == tenant.id,
                TenantLimitOverride.limit_key == body.feature_key,
            )
        ).scalar_one_or_none()

        int_val = int(body.value) if isinstance(body.value, (int, float)) else 0
        if existing is not None:
            existing.value_json = body.value
            existing.reason = body.reason
        else:
            db.add(TenantLimitOverride(
                id=_uuid.uuid4(),
                tenant_id=tenant.id,
                limit_key=body.feature_key,
                limit_value=int_val,
                value_json=body.value,
                reason=body.reason,
            ))
        affected_ids.append(str(tenant.id))

    write_audit(
        db, operator_id=ctx.operator_id, action="bulk_override",
        resource_type="override",
        details={"feature_key": body.feature_key, "filter": body.filter, "count": len(affected_ids)},
    )
    db.commit()
    return BulkOverrideResult(count=len(affected_ids), affected_tenant_ids=affected_ids)


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
