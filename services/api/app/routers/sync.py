from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import DeviceAuth, get_device_auth
from app.db.session import get_db
from app.models import Product, ProductGroup, Shop, ShopProductTax, Tenant, TenantLicenseCache, User
from app.services.stock import current_quantity
from app.services.sync_push import process_push_batch
from app.services.tax import effective_tax_bps_for_product

router = APIRouter(prefix="/v1/sync", tags=["Sync"])


class TenantOfflinePolicyOut(BaseModel):
    tier: str
    max_offline_minutes: int
    employee_session_timeout_minutes: int


class TenantCurrencyOut(BaseModel):
    code: str
    exponent: int
    symbol_override: str | None = None


class ProductDTO(BaseModel):
    id: UUID
    sku: str
    name: str
    category: str | None = None
    unit_price_cents: int
    active: bool
    effective_tax_rate_bps: int
    tax_exempt: bool
    product_group_id: UUID | None = None
    group_title: str | None = None
    variant_label: str | None = None


class StockSnapshotDTO(BaseModel):
    shop_id: UUID
    product_id: UUID
    quantity: int


class SyncPullResponse(BaseModel):
    cursor: str
    products: list[ProductDTO]
    stock_snapshots: list[StockSnapshotDTO]
    policy: TenantOfflinePolicyOut
    currency: TenantCurrencyOut
    shop_default_tax_rate_bps: int
    employee_active: bool | None = None
    license_status: str | None = None
    license_trial_ends_at: str | None = None
    license_grace_ends_at: str | None = None


class PushBatchRequest(BaseModel):
    device_id: UUID
    idempotency_key: str
    events: list[dict[str, Any]]


class AppliedEventResult(BaseModel):
    client_mutation_id: str
    server_transaction_id: UUID | None
    status: str
    detail: str | None = None
    conflict: dict[str, Any] | None = None


class PushBatchResponse(BaseModel):
    results: list[AppliedEventResult]
    new_cursor: str


def _license_fields(db: Session, tenant_id: UUID) -> dict:
    """Build license fields for the sync pull response from local cache."""
    cache = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if cache is None:
        return {}

    result: dict[str, str | None] = {"license_status": cache.subscription_status}
    if cache.trial_ends_at:
        result["license_trial_ends_at"] = cache.trial_ends_at.isoformat()
    if cache.is_in_grace_period and cache.current_period_end:
        from datetime import timedelta
        grace_end = cache.current_period_end + timedelta(days=cache.grace_period_days)
        result["license_grace_ends_at"] = grace_end.isoformat()
    return result


@router.get("/pull", response_model=SyncPullResponse)
def sync_pull(
    shop_id: UUID,
    auth: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
    cursor: str | None = None,
) -> SyncPullResponse:
    if shop_id not in auth.shop_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shop not allowed")
    tenant = db.get(Tenant, auth.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant missing")

    shop_row = db.get(Shop, shop_id)
    if shop_row is None or shop_row.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop missing")

    products = db.execute(
        select(Product).where(Product.tenant_id == auth.tenant_id, Product.active.is_(True))
    ).scalars().all()

    pids = [p.id for p in products]
    tax_rows = (
        db.execute(
            select(ShopProductTax).where(
                ShopProductTax.shop_id == shop_id,
                ShopProductTax.product_id.in_(pids),
            )
        ).scalars().all()
        if pids
        else []
    )
    tax_by_pid: dict = {r.product_id: r for r in tax_rows}

    group_ids = {p.product_group_id for p in products if p.product_group_id is not None}
    group_title_by_id: dict[UUID, str] = {}
    if group_ids:
        for g in db.execute(select(ProductGroup).where(ProductGroup.id.in_(group_ids))).scalars().all():
            group_title_by_id[g.id] = g.title

    snaps: list[StockSnapshotDTO] = []
    product_dtos: list[ProductDTO] = []
    for p in products:
        snaps.append(
            StockSnapshotDTO(
                shop_id=shop_id,
                product_id=p.id,
                quantity=current_quantity(db, shop_id, p.id),
            )
        )
        bps, exempt = effective_tax_bps_for_product(shop_row, p, tax_by_pid.get(p.id))
        gid = p.product_group_id
        product_dtos.append(
            ProductDTO(
                id=p.id,
                sku=p.sku,
                name=p.name,
                category=p.category,
                unit_price_cents=p.unit_price_cents,
                active=p.active,
                effective_tax_rate_bps=bps,
                tax_exempt=exempt,
                product_group_id=gid,
                group_title=group_title_by_id.get(gid) if gid is not None else None,
                variant_label=p.variant_label,
            )
        )

    # Check active status of the employee linked to this device (if any).
    linked_employee = db.execute(
        select(User).where(
            User.tenant_id == auth.tenant_id,
            User.device_id == auth.device_id,
        )
    ).scalar_one_or_none()
    employee_active: bool | None = None if linked_employee is None else linked_employee.is_active

    return SyncPullResponse(
        cursor=cursor or "0",
        products=product_dtos,
        stock_snapshots=snaps,
        policy=TenantOfflinePolicyOut(
            tier=tenant.offline_tier,
            max_offline_minutes=tenant.max_offline_minutes,
            employee_session_timeout_minutes=tenant.employee_session_timeout_minutes,
        ),
        currency=TenantCurrencyOut(
            code=tenant.default_currency_code,
            exponent=tenant.currency_exponent,
            symbol_override=tenant.currency_symbol_override,
        ),
        shop_default_tax_rate_bps=shop_row.default_tax_rate_bps,
        employee_active=employee_active,
        **_license_fields(db, auth.tenant_id),
    )


@router.post("/push", response_model=PushBatchResponse)
def sync_push(
    body: PushBatchRequest,
    auth: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> PushBatchResponse:
    if body.device_id != auth.device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="device_id mismatch")
    try:
        results, new_cursor = process_push_batch(
            db,
            tenant_id=auth.tenant_id,
            device_id=auth.device_id,
            allowed_shop_ids=auth.shop_ids,
            idempotency_key=body.idempotency_key,
            events=body.events,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return PushBatchResponse(
        results=[
            AppliedEventResult(
                client_mutation_id=r.client_mutation_id,
                server_transaction_id=r.server_transaction_id,
                status=r.status,
                detail=r.detail,
                conflict=r.conflict,
            )
            for r in results
        ],
        new_cursor=new_cursor,
    )
