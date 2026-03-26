import secrets
import bcrypt
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.auth.jwt import create_operator_access_token
from app.db.admin_deps_db import get_db_admin
from app.db.session import get_db
from app.models import AdminUser, Device, EnrollmentToken, Product, Shop, ShopProductTax, Tenant
from app.services.enrollment import hash_token

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


class AdminLoginBody(BaseModel):
    email: EmailStr
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/auth/login", response_model=AdminLoginResponse)
def admin_login(
    body: AdminLoginBody,
    db: Annotated[Session, Depends(get_db)],
) -> AdminLoginResponse:
    user = db.execute(
        select(AdminUser).where(AdminUser.email == body.email.strip().lower(), AdminUser.is_active.is_(True))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    raw_pw = body.password.strip().encode("utf-8")
    try:
        ok = bcrypt.checkpw(raw_pw, user.password_hash.encode("ascii"))
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    access, ttl = create_operator_access_token(operator_id=user.id)
    return AdminLoginResponse(access_token=access, expires_in=ttl)


class TenantOverview(BaseModel):
    id: UUID
    name: str
    slug: str
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None = None
    shop_count: int
    device_count: int


class AdminOverviewResponse(BaseModel):
    tenants: list[TenantOverview]


@router.get("/overview", response_model=AdminOverviewResponse)
def admin_overview(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> AdminOverviewResponse:
    tenants = db.execute(select(Tenant).order_by(Tenant.created_at)).scalars().all()
    out: list[TenantOverview] = []
    for t in tenants:
        shop_count = db.execute(
            select(func.count()).select_from(Shop).where(Shop.tenant_id == t.id)
        ).scalar_one()
        device_count = db.execute(
            select(func.count()).select_from(Device).where(Device.tenant_id == t.id)
        ).scalar_one()
        out.append(
            TenantOverview(
                id=t.id,
                name=t.name,
                slug=t.slug,
                default_currency_code=t.default_currency_code,
                currency_exponent=t.currency_exponent,
                currency_symbol_override=t.currency_symbol_override,
                shop_count=int(shop_count),
                device_count=int(device_count),
            )
        )
    return AdminOverviewResponse(tenants=out)


class UpdateTenantCurrencyBody(BaseModel):
    code: str = Field(min_length=3, max_length=3)
    exponent: int = Field(default=2, ge=0, le=4)
    symbol_override: str | None = Field(default=None, max_length=8)


class UpdateTenantCurrencyResponse(BaseModel):
    tenant_id: UUID
    code: str
    exponent: int
    symbol_override: str | None = None


@router.patch("/tenants/{tenant_id}/currency", response_model=UpdateTenantCurrencyResponse)
def update_tenant_currency(
    tenant_id: UUID,
    body: UpdateTenantCurrencyBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> UpdateTenantCurrencyResponse:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.default_currency_code = body.code.upper()
    tenant.currency_exponent = body.exponent
    tenant.currency_symbol_override = body.symbol_override
    db.commit()
    return UpdateTenantCurrencyResponse(
        tenant_id=tenant.id,
        code=tenant.default_currency_code,
        exponent=tenant.currency_exponent,
        symbol_override=tenant.currency_symbol_override,
    )


class MintEnrollmentBody(BaseModel):
    tenant_id: UUID
    shop_id: UUID
    ttl_hours: int = Field(default=168, ge=1, le=24 * 30)


class MintEnrollmentResponse(BaseModel):
    enrollment_token: str
    expires_at: datetime


@router.post("/enrollment-tokens", response_model=MintEnrollmentResponse)
def mint_enrollment_token(
    body: MintEnrollmentBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> MintEnrollmentResponse:
    shop = db.get(Shop, body.shop_id)
    if shop is None or shop.tenant_id != body.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found for tenant")

    raw = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(hours=body.ttl_hours)
    db.add(
        EnrollmentToken(
            tenant_id=body.tenant_id,
            shop_id=body.shop_id,
            token_hash=hash_token(raw),
            expires_at=expires_at,
        )
    )
    db.commit()
    return MintEnrollmentResponse(enrollment_token=raw, expires_at=expires_at)


class EnqueuePingResponse(BaseModel):
    job_id: str


@router.post("/jobs/ping", response_model=EnqueuePingResponse)
def enqueue_worker_ping(_: AdminAuthDep) -> EnqueuePingResponse:
    from app.worker.queue import task_queue
    from app.worker.tasks import ping

    job = task_queue().enqueue(ping)
    return EnqueuePingResponse(job_id=str(job.id))


class EnqueueAggregateBody(BaseModel):
    tenant_id: UUID


class EnqueueAggregateResponse(BaseModel):
    job_id: str


@router.post("/jobs/aggregate-report", response_model=EnqueueAggregateResponse)
def enqueue_aggregate_report(
    body: EnqueueAggregateBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EnqueueAggregateResponse:
    tenant = db.get(Tenant, body.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    from app.worker.queue import task_queue
    from app.worker.tasks import aggregate_report_placeholder

    job = task_queue().enqueue(aggregate_report_placeholder, str(body.tenant_id))
    return EnqueueAggregateResponse(job_id=str(job.id))


class UpdateShopDefaultTaxBody(BaseModel):
    default_tax_rate_bps: int = Field(ge=0, le=100_000)


class UpdateShopDefaultTaxResponse(BaseModel):
    shop_id: UUID
    default_tax_rate_bps: int


@router.patch("/shops/{shop_id}/default-tax", response_model=UpdateShopDefaultTaxResponse)
def update_shop_default_tax_rate(
    shop_id: UUID,
    body: UpdateShopDefaultTaxBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> UpdateShopDefaultTaxResponse:
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    shop.default_tax_rate_bps = body.default_tax_rate_bps
    db.commit()
    return UpdateShopDefaultTaxResponse(shop_id=shop.id, default_tax_rate_bps=shop.default_tax_rate_bps)


class UpsertShopProductTaxBody(BaseModel):
    tax_exempt: bool = False
    effective_tax_rate_bps: int | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def exempt_or_bps(self) -> "UpsertShopProductTaxBody":
        if not self.tax_exempt and self.effective_tax_rate_bps is None:
            raise ValueError("effective_tax_rate_bps is required when tax_exempt is false")
        return self


class ShopProductTaxOut(BaseModel):
    id: UUID
    tenant_id: UUID
    shop_id: UUID
    product_id: UUID
    tax_exempt: bool
    effective_tax_rate_bps: int | None


@router.get("/shops/{shop_id}/product-taxes", response_model=list[ShopProductTaxOut])
def list_shop_product_taxes(
    shop_id: UUID,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ShopProductTaxOut]:
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    rows = db.execute(select(ShopProductTax).where(ShopProductTax.shop_id == shop_id)).scalars().all()
    return [
        ShopProductTaxOut(
            id=r.id,
            tenant_id=r.tenant_id,
            shop_id=r.shop_id,
            product_id=r.product_id,
            tax_exempt=r.tax_exempt,
            effective_tax_rate_bps=r.effective_tax_rate_bps,
        )
        for r in rows
    ]


@router.put("/shops/{shop_id}/product-taxes/{product_id}", response_model=ShopProductTaxOut)
def upsert_shop_product_tax(
    shop_id: UUID,
    product_id: UUID,
    body: UpsertShopProductTaxBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShopProductTaxOut:
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    prod = db.get(Product, product_id)
    if prod is None or prod.tenant_id != shop.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found for shop tenant")

    existing = db.execute(
        select(ShopProductTax).where(
            ShopProductTax.shop_id == shop_id,
            ShopProductTax.product_id == product_id,
        )
    ).scalar_one_or_none()
    bps = None if body.tax_exempt else body.effective_tax_rate_bps
    if existing:
        existing.tax_exempt = body.tax_exempt
        existing.effective_tax_rate_bps = bps
        row = existing
    else:
        row = ShopProductTax(
            tenant_id=shop.tenant_id,
            shop_id=shop_id,
            product_id=product_id,
            tax_exempt=body.tax_exempt,
            effective_tax_rate_bps=bps,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return ShopProductTaxOut(
        id=row.id,
        tenant_id=row.tenant_id,
        shop_id=row.shop_id,
        product_id=row.product_id,
        tax_exempt=row.tax_exempt,
        effective_tax_rate_bps=row.effective_tax_rate_bps,
    )


@router.delete("/shops/{shop_id}/product-taxes/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shop_product_tax(
    shop_id: UUID,
    product_id: UUID,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    row = db.execute(
        select(ShopProductTax).where(
            ShopProductTax.shop_id == shop_id,
            ShopProductTax.product_id == product_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    db.delete(row)
    db.commit()
