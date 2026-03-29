"""Admin console endpoints for the web dashboard (operator JWT or legacy admin token)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import (
    AdminUser,
    Product,
    ProductGroup,
    Shop,
    StockMovement,
    Supplier,
    Tenant,
    Transaction,
    TransactionLine,
)
from app.routers.transactions import (
    PaymentOut,
    TransactionListResponse,
    TransactionOut,
    _decode_cursor,
    _encode_cursor,
    _line_dto,
    _parse_status_filter,
    _product_labels_for_lines,
)
from app.services.stock import current_quantity

router = APIRouter(prefix="/v1/admin", tags=["Admin Console"])


def _admin_transactions_base_stmt(
    tenant_id: UUID | None,
    shop_id: UUID | None,
    statuses: list[str] | None,
    search: str | None,
) -> Select:
    stmt = select(Transaction).options(
        selectinload(Transaction.lines),
        selectinload(Transaction.payments),
    )
    if tenant_id is not None:
        stmt = stmt.where(Transaction.tenant_id == tenant_id)
    if shop_id is not None:
        stmt = stmt.where(Transaction.shop_id == shop_id)
    if statuses:
        stmt = stmt.where(Transaction.status.in_(statuses))
    if search and search.strip():
        needle = f"%{search.strip()}%"
        matching = (
            select(TransactionLine.transaction_id)
            .join(Product, Product.id == TransactionLine.product_id)
            .where(or_(Product.name.ilike(needle), Product.sku.ilike(needle)))
            .distinct()
        )
        stmt = stmt.where(Transaction.id.in_(matching))
    return stmt


@router.get("/transactions", response_model=TransactionListResponse)
def admin_list_transactions(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    shop_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    status: str | None = Query(
        default=None,
        description="Comma-separated: posted,refunded,pending",
    ),
    q: str | None = Query(default=None, description="Filter by line product name or SKU (substring)."),
) -> TransactionListResponse:
    statuses = _parse_status_filter(status)
    stmt = _admin_transactions_base_stmt(tenant_id, shop_id, statuses=statuses, search=q)
    stmt = stmt.order_by(Transaction.created_at.desc(), Transaction.id.desc())

    if cursor:
        c_at, c_id = _decode_cursor(cursor)
        stmt = stmt.where(tuple_(Transaction.created_at, Transaction.id) < tuple_(c_at, c_id))

    stmt = stmt.limit(limit + 1)
    rows = list(db.execute(stmt).scalars().unique().all())

    next_cur: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cur = _encode_cursor(last.created_at, last.id)

    labels = _product_labels_for_lines(db, rows)
    items: list[TransactionOut] = []
    for t in rows:
        items.append(
            TransactionOut(
                id=t.id,
                shop_id=t.shop_id,
                kind=t.kind,
                status=t.status,
                total_cents=t.total_cents,
                tax_cents=t.tax_cents,
                client_mutation_id=t.client_mutation_id,
                created_at=t.created_at,
                lines=[_line_dto(ln, labels) for ln in t.lines],
                payments=[
                    PaymentOut(tender_type=p.tender_type, amount_cents=p.amount_cents) for p in t.payments
                ],
            )
        )
    return TransactionListResponse(items=items, next_cursor=next_cur)


def _stock_alert_qty(db: Session, tenant_id: UUID | None, threshold: int) -> int:
    cnt = 0
    shop_stmt = select(Shop)
    if tenant_id is not None:
        shop_stmt = shop_stmt.where(Shop.tenant_id == tenant_id)
    shops = db.execute(shop_stmt).scalars().all()
    for shop in shops:
        prods = db.execute(
            select(Product).where(Product.tenant_id == shop.tenant_id, Product.active.is_(True))
        ).scalars().all()
        for p in prods:
            q = current_quantity(db, shop.id, p.id)
            if q <= threshold:
                cnt += 1
    return cnt


class RecentActivityItem(BaseModel):
    kind: str
    ref_id: UUID
    created_at: str
    detail: str


class DashboardSummaryOut(BaseModel):
    posted_transaction_count: int
    gross_sales_cents: int
    stock_alert_count: int
    supplier_count: int
    shop_count: int
    product_count: int
    tenant_count: int
    recent_activity: list[RecentActivityItem]


@router.get("/dashboard-summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    stock_alert_threshold: int = Query(default=5, ge=0, le=1_000_000),
    activity_limit: int = Query(default=12, ge=1, le=50),
) -> DashboardSummaryOut:
    txn_filters = [Transaction.status == "posted"]
    if tenant_id is not None:
        txn_filters.append(Transaction.tenant_id == tenant_id)

    posted_transaction_count = int(
        db.execute(select(func.count()).select_from(Transaction).where(*txn_filters)).scalar_one()
    )
    gross_sales_cents = int(
        db.execute(
            select(func.coalesce(func.sum(Transaction.total_cents), 0)).where(*txn_filters)
        ).scalar_one()
    )

    def count_model(model, tenant_col) -> int:
        c = select(func.count()).select_from(model)
        if tenant_id is not None:
            c = c.where(tenant_col == tenant_id)
        return int(db.execute(c).scalar_one())

    shop_count = count_model(Shop, Shop.tenant_id)
    product_count = count_model(Product, Product.tenant_id)
    supplier_count = count_model(Supplier, Supplier.tenant_id)
    tenant_count = (
        1
        if tenant_id is not None
        else int(db.execute(select(func.count()).select_from(Tenant)).scalar_one())
    )

    stock_alert_count = _stock_alert_qty(db, tenant_id, stock_alert_threshold)

    txns = db.execute(
        select(Transaction)
        .where(*txn_filters)
        .order_by(Transaction.created_at.desc())
        .limit(activity_limit)
    ).scalars().all()
    move_stmt = select(StockMovement).order_by(StockMovement.created_at.desc()).limit(activity_limit)
    if tenant_id is not None:
        move_stmt = move_stmt.where(StockMovement.tenant_id == tenant_id)
    moves = db.execute(move_stmt).scalars().all()

    items: list[RecentActivityItem] = []
    for t in txns:
        items.append(
            RecentActivityItem(
                kind="transaction",
                ref_id=t.id,
                created_at=t.created_at.isoformat(),
                detail=f"{t.kind}:{t.status}:{t.total_cents}",
            )
        )
    for m in moves:
        items.append(
            RecentActivityItem(
                kind="stock_movement",
                ref_id=m.id,
                created_at=m.created_at.isoformat(),
                detail=f"{m.movement_type}:{m.quantity_delta}",
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    items = items[:activity_limit]

    return DashboardSummaryOut(
        posted_transaction_count=posted_transaction_count,
        gross_sales_cents=gross_sales_cents,
        stock_alert_count=stock_alert_count,
        supplier_count=supplier_count,
        shop_count=shop_count,
        product_count=product_count,
        tenant_count=tenant_count,
        recent_activity=items,
    )


class SalesSeriesPoint(BaseModel):
    day: str
    gross_cents: int
    transaction_count: int


class SalesSeriesResponse(BaseModel):
    points: list[SalesSeriesPoint]


@router.get("/analytics/sales-series", response_model=SalesSeriesResponse)
def sales_series(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
) -> SalesSeriesResponse:
    start = datetime.now(UTC) - timedelta(days=days)
    day_bucket = func.date_trunc("day", Transaction.created_at).label("day")
    stmt = (
        select(
            day_bucket,
            func.coalesce(func.sum(Transaction.total_cents), 0).label("gross"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(Transaction.status == "posted", Transaction.created_at >= start)
    )
    if tenant_id is not None:
        stmt = stmt.where(Transaction.tenant_id == tenant_id)
    stmt = stmt.group_by(day_bucket).order_by(day_bucket)
    rows = db.execute(stmt).all()
    points: list[SalesSeriesPoint] = []
    for r in rows:
        d = r.day
        if isinstance(d, datetime):
            day_str = d.date().isoformat()
        elif hasattr(d, "isoformat"):
            day_str = d.isoformat()[:10]
        else:
            day_str = str(d)[:10]
        points.append(
            SalesSeriesPoint(
                day=day_str,
                gross_cents=int(r.gross),
                transaction_count=int(r.cnt),
            )
        )
    return SalesSeriesResponse(points=points)


class SupplierOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    status: str
    contact_email: str | None
    contact_phone: str | None
    notes: str | None
    created_at: datetime


class CreateSupplierBody(BaseModel):
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=255)
    status: str = Field(default="active", max_length=32)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class PatchSupplierBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=32)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = None


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[SupplierOut]:
    stmt = select(Supplier).order_by(Supplier.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(Supplier.tenant_id == tenant_id)
    rows = db.execute(stmt).scalars().all()
    return [
        SupplierOut(
            id=r.id,
            tenant_id=r.tenant_id,
            name=r.name,
            status=r.status,
            contact_email=r.contact_email,
            contact_phone=r.contact_phone,
            notes=r.notes,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/suppliers", response_model=SupplierOut)
def create_supplier(
    body: CreateSupplierBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SupplierOut:
    if db.get(Tenant, body.tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    row = Supplier(
        tenant_id=body.tenant_id,
        name=body.name.strip(),
        status=body.status.strip().lower(),
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SupplierOut(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        status=row.status,
        contact_email=row.contact_email,
        contact_phone=row.contact_phone,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def patch_supplier(
    supplier_id: UUID,
    body: PatchSupplierBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SupplierOut:
    row = db.get(Supplier, supplier_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if body.name is not None:
        row.name = body.name.strip()
    if body.status is not None:
        row.status = body.status.strip().lower()
    if body.contact_email is not None:
        row.contact_email = body.contact_email
    if body.contact_phone is not None:
        row.contact_phone = body.contact_phone
    if body.notes is not None:
        row.notes = body.notes
    db.commit()
    db.refresh(row)
    return SupplierOut(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        status=row.status,
        contact_email=row.contact_email,
        contact_phone=row.contact_phone,
        notes=row.notes,
        created_at=row.created_at,
    )


def _movement_encode_cursor(created_at: datetime, mid: UUID) -> str:
    payload = f"{created_at.isoformat()}|{mid}"
    raw = base64.urlsafe_b64encode(payload.encode())
    return raw.decode().rstrip("=")


def _movement_decode_cursor(cur: str) -> tuple[datetime, UUID]:
    pad = "=" * (-len(cur) % 4)
    try:
        decoded = base64.urlsafe_b64decode(cur + pad).decode()
        ts, sid = decoded.split("|", 1)
        return datetime.fromisoformat(ts), UUID(sid)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_cursor",
        ) from exc


class StockMovementOut(BaseModel):
    id: UUID
    tenant_id: UUID
    shop_id: UUID
    shop_name: str | None = None
    product_id: UUID
    product_sku: str | None = None
    product_name: str | None = None
    quantity_delta: int
    movement_type: str
    transaction_id: UUID | None
    created_at: datetime


class StockMovementListResponse(BaseModel):
    items: list[StockMovementOut]
    next_cursor: str | None = None


@router.get("/inventory/movements", response_model=StockMovementListResponse)
def list_stock_movements(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    shop_id: UUID | None = None,
    product_id: UUID | None = None,
    movement_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> StockMovementListResponse:
    stmt = select(StockMovement).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    if tenant_id is not None:
        stmt = stmt.where(StockMovement.tenant_id == tenant_id)
    if shop_id is not None:
        stmt = stmt.where(StockMovement.shop_id == shop_id)
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if movement_type is not None and movement_type.strip():
        stmt = stmt.where(StockMovement.movement_type == movement_type.strip())

    if cursor:
        c_at, c_id = _movement_decode_cursor(cursor)
        stmt = stmt.where(tuple_(StockMovement.created_at, StockMovement.id) < tuple_(c_at, c_id))

    stmt = stmt.limit(limit + 1)
    rows = list(db.execute(stmt).scalars().all())
    next_cur: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cur = _movement_encode_cursor(last.created_at, last.id)

    shop_ids = {r.shop_id for r in rows}
    prod_ids = {r.product_id for r in rows}
    shops = {s.id: s for s in db.execute(select(Shop).where(Shop.id.in_(shop_ids))).scalars().all()} if shop_ids else {}
    prods = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(prod_ids))).scalars().all()} if prod_ids else {}

    items = [
        StockMovementOut(
            id=r.id,
            tenant_id=r.tenant_id,
            shop_id=r.shop_id,
            shop_name=shops[r.shop_id].name if r.shop_id in shops else None,
            product_id=r.product_id,
            product_sku=prods[r.product_id].sku if r.product_id in prods else None,
            product_name=prods[r.product_id].name if r.product_id in prods else None,
            quantity_delta=r.quantity_delta,
            movement_type=r.movement_type,
            transaction_id=r.transaction_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return StockMovementListResponse(items=items, next_cursor=next_cur)


class OperatorOut(BaseModel):
    id: UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime


class PatchOperatorBody(BaseModel):
    role: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


@router.get("/operators", response_model=list[OperatorOut])
def list_operators(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[OperatorOut]:
    rows = db.execute(select(AdminUser).order_by(AdminUser.created_at.desc())).scalars().all()
    return [
        OperatorOut(id=r.id, email=r.email, role=r.role, is_active=r.is_active, created_at=r.created_at)
        for r in rows
    ]


@router.patch("/operators/{operator_id}", response_model=OperatorOut)
def patch_operator(
    operator_id: UUID,
    body: PatchOperatorBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> OperatorOut:
    row = db.get(AdminUser, operator_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    if body.role is not None:
        row.role = body.role.strip()
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return OperatorOut(
        id=row.id, email=row.email, role=row.role, is_active=row.is_active, created_at=row.created_at
    )


class CreateShopBody(BaseModel):
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=255)


class CreateShopResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str


class ShopSummaryOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str


@router.get("/shops", response_model=list[ShopSummaryOut])
def admin_list_shops(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[ShopSummaryOut]:
    stmt = select(Shop).order_by(Shop.tenant_id, Shop.name)
    if tenant_id is not None:
        stmt = stmt.where(Shop.tenant_id == tenant_id)
    rows = db.execute(stmt).scalars().all()
    return [ShopSummaryOut(id=r.id, tenant_id=r.tenant_id, name=r.name) for r in rows]


@router.post("/shops", response_model=CreateShopResponse)
def admin_create_shop(
    body: CreateShopBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CreateShopResponse:
    if db.get(Tenant, body.tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    shop = Shop(tenant_id=body.tenant_id, name=body.name.strip())
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return CreateShopResponse(id=shop.id, tenant_id=shop.tenant_id, name=shop.name)


class CreateProductBody(BaseModel):
    tenant_id: UUID
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit_price_cents: int = Field(ge=0)
    category: str | None = Field(default=None, max_length=128)
    product_group_id: UUID | None = None
    variant_label: str | None = Field(default=None, max_length=128)


class CreateProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    unit_price_cents: int
    category: str | None
    product_group_id: UUID | None = None
    group_title: str | None = None
    variant_label: str | None = None


def _resolve_product_group(
    db: Session, tenant_id: UUID, product_group_id: UUID | None
) -> ProductGroup | None:
    if product_group_id is None:
        return None
    g = db.get(ProductGroup, product_group_id)
    if g is None or g.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="product_group_not_found",
        )
    return g


class ProductListItem(BaseModel):
    id: UUID
    sku: str
    name: str
    status: str
    category: str | None
    unit_price_cents: int
    reorder_point: int
    variant_label: str | None = None
    group_title: str | None = None


@router.get("/products", response_model=list[ProductListItem])
def admin_list_products(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
) -> list[ProductListItem]:
    stmt = select(Product).options(selectinload(Product.product_group)).order_by(Product.name.asc())
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if status_filter:
        stmt = stmt.where(Product.status == status_filter)
    if category and category.strip():
        stmt = stmt.where(Product.category == category.strip())
    rows = db.execute(stmt).scalars().all()
    return [
        ProductListItem(
            id=r.id,
            sku=r.sku,
            name=r.name,
            status=r.status,
            category=r.category,
            unit_price_cents=r.unit_price_cents,
            reorder_point=r.reorder_point,
            variant_label=r.variant_label,
            group_title=r.product_group.title if r.product_group else None,
        )
        for r in rows
    ]


@router.post("/products", response_model=CreateProductResponse)
def admin_create_product(
    body: CreateProductBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CreateProductResponse:
    if db.get(Tenant, body.tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    group = _resolve_product_group(db, body.tenant_id, body.product_group_id)
    prod = Product(
        tenant_id=body.tenant_id,
        product_group_id=group.id if group else None,
        sku=body.sku.strip(),
        name=body.name.strip(),
        unit_price_cents=body.unit_price_cents,
        category=body.category.strip() if body.category else None,
        variant_label=body.variant_label.strip() if body.variant_label else None,
    )
    db.add(prod)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="sku_conflict") from None
    db.refresh(prod)
    return CreateProductResponse(
        id=prod.id,
        tenant_id=prod.tenant_id,
        sku=prod.sku,
        name=prod.name,
        unit_price_cents=prod.unit_price_cents,
        category=prod.category,
        product_group_id=prod.product_group_id,
        group_title=group.title if group else None,
        variant_label=prod.variant_label,
    )


class ProductGroupOut(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    notes: str | None
    created_at: datetime


class CreateProductGroupBody(BaseModel):
    tenant_id: UUID
    title: str = Field(min_length=1, max_length=255)
    notes: str | None = None


@router.post("/product-groups", response_model=ProductGroupOut)
def admin_create_product_group(
    body: CreateProductGroupBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductGroupOut:
    if db.get(Tenant, body.tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    row = ProductGroup(
        tenant_id=body.tenant_id,
        title=body.title.strip(),
        notes=body.notes.strip() if body.notes else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProductGroupOut(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.get("/product-groups", response_model=list[ProductGroupOut])
def admin_list_product_groups(
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID,
) -> list[ProductGroupOut]:
    rows = db.execute(
        select(ProductGroup)
        .where(ProductGroup.tenant_id == tenant_id)
        .order_by(ProductGroup.title.asc())
    ).scalars().all()
    return [
        ProductGroupOut(
            id=r.id,
            tenant_id=r.tenant_id,
            title=r.title,
            notes=r.notes,
            created_at=r.created_at,
        )
        for r in rows
    ]


class PatchProductBody(BaseModel):
    product_group_id: UUID | None = None
    variant_label: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)


@router.patch("/products/{product_id}", response_model=CreateProductResponse)
def admin_patch_product(
    product_id: UUID,
    body: PatchProductBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CreateProductResponse:
    prod = db.get(Product, product_id)
    if prod is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    patch = body.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"] is not None:
        prod.name = patch["name"].strip()

    if "variant_label" in patch:
        vl = patch["variant_label"]
        prod.variant_label = vl.strip() if isinstance(vl, str) and vl.strip() else None

    group_title: str | None = None
    if "product_group_id" in patch:
        gid = patch["product_group_id"]
        if gid is None:
            prod.product_group_id = None
        else:
            g = _resolve_product_group(db, prod.tenant_id, gid)
            prod.product_group_id = g.id
            group_title = g.title

    db.commit()
    db.refresh(prod)
    if prod.product_group_id is not None:
        g_out = db.get(ProductGroup, prod.product_group_id)
        group_title = g_out.title if g_out else None

    return CreateProductResponse(
        id=prod.id,
        tenant_id=prod.tenant_id,
        sku=prod.sku,
        name=prod.name,
        unit_price_cents=prod.unit_price_cents,
        category=prod.category,
        product_group_id=prod.product_group_id,
        group_title=group_title,
        variant_label=prod.variant_label,
    )
