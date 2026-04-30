"""Admin analytics endpoints — designed for both web dashboard and mobile admin app."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import (
    PaymentAllocation,
    Product,
    PurchaseOrder,
    Shop,
    StockMovement,
    Tenant,
    Transaction,
    TransactionLine,
)

router = APIRouter(prefix="/v1/admin/analytics", tags=["Admin Analytics"])

from app.services.localisation import effective_timezone  # noqa: E402


# ---------------------------------------------------------------------------
# Auth helpers (mirrored from admin_web — no shared module yet)
# ---------------------------------------------------------------------------


def _require_operator_tenant(ctx: AdminContext) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy admin token is not allowed for this endpoint",
        )
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator account has no tenant assigned",
        )
    return ctx.tenant_id


def _coerce_tenant_scope(ctx: AdminContext, requested: UUID | None) -> UUID:
    operator_tenant = _require_operator_tenant(ctx)
    if requested is not None and requested != operator_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access is forbidden",
        )
    return operator_tenant


# ---------------------------------------------------------------------------
# Shared query helpers
# ---------------------------------------------------------------------------


def _tx_filters(tenant_id: UUID, days: int, shop_id: UUID | None) -> tuple[list, datetime]:
    start = datetime.now(UTC) - timedelta(days=days)
    filters = [
        Transaction.status == "posted",
        Transaction.created_at >= start,
        Transaction.tenant_id == tenant_id,
    ]
    if shop_id:
        filters.append(Transaction.shop_id == shop_id)
    return filters, start


def _prev_gross_cents(db: Session, tenant_id: UUID, days: int, shop_id: UUID | None) -> int:
    now = datetime.now(UTC)
    prev_start = now - timedelta(days=days * 2)
    prev_end = now - timedelta(days=days)
    filters = [
        Transaction.status == "posted",
        Transaction.created_at >= prev_start,
        Transaction.created_at < prev_end,
        Transaction.tenant_id == tenant_id,
    ]
    if shop_id:
        filters.append(Transaction.shop_id == shop_id)
    return int(
        db.execute(
            select(func.coalesce(func.sum(Transaction.total_cents), 0)).where(*filters)
        ).scalar_one()
    )


def _period_meta(days: int) -> tuple[str, str]:
    now = datetime.now(UTC)
    return (now - timedelta(days=days)).date().isoformat(), now.date().isoformat()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AnalyticsSummary(BaseModel):
    period_start: str
    period_end: str
    days: int
    gross_cents: int
    prev_gross_cents: int
    delta_pct: float
    transaction_count: int
    avg_ticket_cents: int
    top_category: str | None
    stock_alert_count: int
    pending_order_count: int


class SalesPoint(BaseModel):
    label: str
    gross_cents: int
    transaction_count: int


class SalesSeriesOut(BaseModel):
    period_start: str
    period_end: str
    granularity: str
    points: list[SalesPoint]


class CategoryItem(BaseModel):
    category: str
    gross_cents: int
    transaction_count: int
    pct: float


class CategoryRevenueOut(BaseModel):
    period_start: str
    period_end: str
    items: list[CategoryItem]


class TopProductItem(BaseModel):
    product_id: UUID
    product_name: str
    sku: str
    category: str | None
    qty_sold: int
    gross_cents: int


class TopProductsOut(BaseModel):
    period_start: str
    period_end: str
    items: list[TopProductItem]


class HourBucket(BaseModel):
    hour: int
    avg_gross_cents: int
    avg_tx_count: float


class HourlyHeatmapOut(BaseModel):
    period_start: str
    period_end: str
    days_sampled: int
    buckets: list[HourBucket]


class PaymentMethodItem(BaseModel):
    tender_type: str
    gross_cents: int
    transaction_count: int
    pct: float


class PaymentMethodsOut(BaseModel):
    period_start: str
    period_end: str
    items: list[PaymentMethodItem]


class ShopRevenueItem(BaseModel):
    shop_id: UUID
    shop_name: str
    gross_cents: int
    transaction_count: int
    pct: float
    stock_alert_count: int = 0


class ShopRevenueOut(BaseModel):
    period_start: str
    period_end: str
    items: list[ShopRevenueItem]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=AnalyticsSummary, dependencies=[require_permission("analytics:read")])
def analytics_summary(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
    shop_id: UUID | None = None,
) -> AnalyticsSummary:
    """Single-call bundle for mobile home screen — all above-the-fold KPIs."""
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    filters, start = _tx_filters(tenant_id, days, shop_id)
    period_start, period_end = _period_meta(days)

    gross_cents = int(
        db.execute(
            select(func.coalesce(func.sum(Transaction.total_cents), 0)).where(*filters)
        ).scalar_one()
    )
    transaction_count = int(
        db.execute(select(func.count()).select_from(Transaction).where(*filters)).scalar_one()
    )
    avg_ticket_cents = gross_cents // transaction_count if transaction_count > 0 else 0
    prev = _prev_gross_cents(db, tenant_id, days, shop_id)
    delta_pct = round((gross_cents - prev) / prev * 100, 1) if prev > 0 else 0.0

    # Top category by revenue
    cat_col = func.coalesce(Product.category, "Uncategorized").label("cat")
    cat_stmt = (
        select(cat_col, func.sum(TransactionLine.quantity * TransactionLine.unit_price_cents).label("g"))
        .join(Transaction, Transaction.id == TransactionLine.transaction_id)
        .join(Product, Product.id == TransactionLine.product_id)
        .where(*filters)
        .group_by(cat_col)
        .order_by(func.sum(TransactionLine.quantity * TransactionLine.unit_price_cents).desc())
        .limit(1)
    )
    top_cat_row = db.execute(cat_stmt).first()
    top_category = top_cat_row.cat if top_cat_row else None

    # Stock alerts
    alert_sub = (
        select(StockMovement.shop_id, StockMovement.product_id)
        .join(Product, Product.id == StockMovement.product_id)
        .where(StockMovement.tenant_id == tenant_id, Product.active.is_(True))
        .group_by(StockMovement.shop_id, StockMovement.product_id, Product.reorder_point)
        .having(func.coalesce(func.sum(StockMovement.quantity_delta), 0) <= Product.reorder_point)
        .subquery()
    )
    stock_alert_count = int(
        db.execute(select(func.count()).select_from(alert_sub)).scalar_one()
    )

    pending_order_count = int(
        db.execute(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.status == "ordered")
        ).scalar_one()
    )

    return AnalyticsSummary(
        period_start=period_start,
        period_end=period_end,
        days=days,
        gross_cents=gross_cents,
        prev_gross_cents=prev,
        delta_pct=delta_pct,
        transaction_count=transaction_count,
        avg_ticket_cents=avg_ticket_cents,
        top_category=top_category,
        stock_alert_count=stock_alert_count,
        pending_order_count=pending_order_count,
    )


@router.get("/sales-series", response_model=SalesSeriesOut, dependencies=[require_permission("analytics:read")])
def sales_series_v2(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
    granularity: str = Query(default="day", pattern="^(day|week|month)$"),
    shop_id: UUID | None = None,
) -> SalesSeriesOut:
    """Time-series sales data — shop-filterable, granularity-aware, for mobile charts."""
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    filters, _start = _tx_filters(tenant_id, days, shop_id)
    period_start, period_end = _period_meta(days)

    if granularity == "day":
        bucket = func.date_trunc("day", Transaction.created_at).label("bucket")
    elif granularity == "week":
        bucket = func.date_trunc("week", Transaction.created_at).label("bucket")
    else:
        bucket = func.date_trunc("month", Transaction.created_at).label("bucket")

    stmt = (
        select(
            bucket,
            func.coalesce(func.sum(Transaction.total_cents), 0).label("gross"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(*filters)
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = db.execute(stmt).all()
    points = []
    for r in rows:
        d = r.bucket
        if hasattr(d, "date"):
            label = d.date().isoformat()
        else:
            label = str(d)[:10]
        points.append(SalesPoint(label=label, gross_cents=int(r.gross), transaction_count=int(r.cnt)))

    return SalesSeriesOut(
        period_start=period_start,
        period_end=period_end,
        granularity=granularity,
        points=points,
    )


@router.get("/category-revenue", response_model=CategoryRevenueOut, dependencies=[require_permission("analytics:read")])
def category_revenue(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
    shop_id: UUID | None = None,
) -> CategoryRevenueOut:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    filters, _start = _tx_filters(tenant_id, days, shop_id)
    period_start, period_end = _period_meta(days)

    cat_col = func.coalesce(Product.category, "Uncategorized").label("category")
    stmt = (
        select(
            cat_col,
            func.sum(TransactionLine.quantity * TransactionLine.unit_price_cents).label("gross"),
            func.count(func.distinct(TransactionLine.transaction_id)).label("tx_count"),
        )
        .join(Transaction, Transaction.id == TransactionLine.transaction_id)
        .join(Product, Product.id == TransactionLine.product_id)
        .where(*filters)
        .group_by(cat_col)
        .order_by(func.sum(TransactionLine.quantity * TransactionLine.unit_price_cents).desc())
    )
    rows = db.execute(stmt).all()
    total = sum(int(r.gross) for r in rows) or 1
    items = [
        CategoryItem(
            category=r.category,
            gross_cents=int(r.gross),
            transaction_count=int(r.tx_count),
            pct=round(int(r.gross) / total * 100, 1),
        )
        for r in rows
    ]
    return CategoryRevenueOut(period_start=period_start, period_end=period_end, items=items)


@router.get("/top-products", response_model=TopProductsOut, dependencies=[require_permission("analytics:read")])
def top_products(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
    limit: int = Query(default=10, ge=1, le=50),
    shop_id: UUID | None = None,
) -> TopProductsOut:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    filters, _start = _tx_filters(tenant_id, days, shop_id)
    period_start, period_end = _period_meta(days)

    stmt = (
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.sku.label("sku"),
            Product.category.label("category"),
            func.sum(TransactionLine.quantity).label("qty_sold"),
            func.sum(TransactionLine.quantity * TransactionLine.unit_price_cents).label("gross"),
        )
        .join(Transaction, Transaction.id == TransactionLine.transaction_id)
        .join(Product, Product.id == TransactionLine.product_id)
        .where(*filters)
        .group_by(Product.id, Product.name, Product.sku, Product.category)
        .order_by(func.sum(TransactionLine.quantity * TransactionLine.unit_price_cents).desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    items = [
        TopProductItem(
            product_id=r.product_id,
            product_name=r.product_name,
            sku=r.sku,
            category=r.category,
            qty_sold=int(r.qty_sold),
            gross_cents=int(r.gross),
        )
        for r in rows
    ]
    return TopProductsOut(period_start=period_start, period_end=period_end, items=items)


@router.get("/hourly-heatmap", response_model=HourlyHeatmapOut, dependencies=[require_permission("analytics:read")])
def hourly_heatmap(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=14, ge=1, le=90),
    shop_id: UUID | None = None,
) -> HourlyHeatmapOut:
    """Returns avg revenue and transaction count per hour of day — identifies peak trading hours."""
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    tenant = db.get(Tenant, tenant_id)
    shop = db.get(Shop, shop_id) if shop_id else None
    tz = effective_timezone(shop, tenant)

    filters, start = _tx_filters(tenant_id, days, shop_id)
    period_start, period_end = _period_meta(days)

    local_ts = func.timezone(tz, Transaction.created_at)

    distinct_days = int(
        db.execute(
            select(func.count(func.distinct(func.date_trunc("day", local_ts)))).where(*filters)
        ).scalar_one()
    ) or 1

    hour_col = extract("hour", local_ts).label("hour")
    stmt = (
        select(
            hour_col,
            func.coalesce(func.sum(Transaction.total_cents), 0).label("gross"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(*filters)
        .group_by(hour_col)
        .order_by(hour_col)
    )
    rows = db.execute(stmt).all()
    raw: dict[int, tuple[int, int]] = {int(r.hour): (int(r.gross), int(r.cnt)) for r in rows}

    buckets = [
        HourBucket(
            hour=h,
            avg_gross_cents=raw[h][0] // distinct_days if h in raw else 0,
            avg_tx_count=round(raw[h][1] / distinct_days, 2) if h in raw else 0.0,
        )
        for h in range(24)
    ]
    return HourlyHeatmapOut(
        period_start=period_start,
        period_end=period_end,
        days_sampled=distinct_days,
        buckets=buckets,
    )


@router.get("/payment-methods", response_model=PaymentMethodsOut, dependencies=[require_permission("analytics:read")])
def payment_methods(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
    shop_id: UUID | None = None,
) -> PaymentMethodsOut:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    filters, _start = _tx_filters(tenant_id, days, shop_id)
    period_start, period_end = _period_meta(days)

    stmt = (
        select(
            PaymentAllocation.tender_type,
            func.sum(PaymentAllocation.amount_cents).label("gross"),
            func.count(func.distinct(PaymentAllocation.transaction_id)).label("tx_count"),
        )
        .join(Transaction, Transaction.id == PaymentAllocation.transaction_id)
        .where(*filters)
        .group_by(PaymentAllocation.tender_type)
        .order_by(func.sum(PaymentAllocation.amount_cents).desc())
    )
    rows = db.execute(stmt).all()
    total = sum(int(r.gross) for r in rows) or 1
    items = [
        PaymentMethodItem(
            tender_type=r.tender_type,
            gross_cents=int(r.gross),
            transaction_count=int(r.tx_count),
            pct=round(int(r.gross) / total * 100, 1),
        )
        for r in rows
    ]
    return PaymentMethodsOut(period_start=period_start, period_end=period_end, items=items)


@router.get("/shop-revenue", response_model=ShopRevenueOut, dependencies=[require_permission("analytics:read")])
def shop_revenue(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
) -> ShopRevenueOut:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    filters, _start = _tx_filters(tenant_id, days, shop_id=None)
    period_start, period_end = _period_meta(days)

    stmt = (
        select(
            Shop.id.label("shop_id"),
            Shop.name.label("shop_name"),
            func.coalesce(func.sum(Transaction.total_cents), 0).label("gross"),
            func.count(Transaction.id).label("cnt"),
        )
        .join(Transaction, Transaction.shop_id == Shop.id)
        .where(*filters)
        .group_by(Shop.id, Shop.name)
        .order_by(func.coalesce(func.sum(Transaction.total_cents), 0).desc())
    )
    rows = db.execute(stmt).all()
    total = sum(int(r.gross) for r in rows) or 1

    # Per-shop stock alert counts: distinct (shop, product) pairs at/below reorder point
    alert_sub = (
        select(
            StockMovement.shop_id.label("shop_id"),
            StockMovement.product_id.label("product_id"),
        )
        .join(Product, Product.id == StockMovement.product_id)
        .where(StockMovement.tenant_id == tenant_id, Product.active.is_(True))
        .group_by(StockMovement.shop_id, StockMovement.product_id, Product.reorder_point)
        .having(func.coalesce(func.sum(StockMovement.quantity_delta), 0) <= Product.reorder_point)
        .subquery()
    )
    alert_rows = db.execute(
        select(alert_sub.c.shop_id, func.count().label("cnt"))
        .select_from(alert_sub)
        .group_by(alert_sub.c.shop_id)
    ).all()
    alert_by_shop: dict[str, int] = {str(ar.shop_id): int(ar.cnt) for ar in alert_rows}

    items = [
        ShopRevenueItem(
            shop_id=r.shop_id,
            shop_name=r.shop_name,
            gross_cents=int(r.gross),
            transaction_count=int(r.cnt),
            pct=round(int(r.gross) / total * 100, 1),
            stock_alert_count=alert_by_shop.get(str(r.shop_id), 0),
        )
        for r in rows
    ]
    return ShopRevenueOut(period_start=period_start, period_end=period_end, items=items)
