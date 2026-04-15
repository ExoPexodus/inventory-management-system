from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.orm import Session, selectinload

from app.auth.deps import DeviceAuth, get_device_auth
from app.db.session import get_db
from app.models import Product, Transaction, TransactionLine

router = APIRouter(prefix="/v1/transactions", tags=["Transactions"])

ALLOWED_TX_STATUSES = frozenset({"posted", "refunded", "pending"})


class TransactionLineOut(BaseModel):
    product_id: UUID
    product_sku: str | None = None
    product_name: str | None = None
    quantity: int
    unit_price_cents: int


class PaymentOut(BaseModel):
    tender_type: str
    amount_cents: int


class TransactionOut(BaseModel):
    id: UUID
    shop_id: UUID
    kind: str
    status: str
    total_cents: int
    tax_cents: int
    client_mutation_id: str
    created_at: datetime
    lines: list[TransactionLineOut]
    payments: list[PaymentOut]
    cashier_name: str | None = None


class TransactionListResponse(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None = None


class ShiftSummaryOut(BaseModel):
    transaction_count: int
    total_cents: int
    since: datetime


def _encode_cursor(created_at: datetime, txn_id: UUID) -> str:
    payload = f"{created_at.isoformat()}|{txn_id}"
    raw = base64.urlsafe_b64encode(payload.encode())
    return raw.decode().rstrip("=")


def _decode_cursor(cur: str) -> tuple[datetime, UUID]:
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


def _parse_status_filter(raw: str | None) -> list[str] | None:
    if raw is None or not raw.strip():
        return None
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    bad = [p for p in parts if p not in ALLOWED_TX_STATUSES]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid_status:{','.join(bad)}",
        )
    return parts


def _transactions_base_stmt(
    auth: DeviceAuth,
    shop_id: UUID,
    *,
    statuses: list[str] | None,
    search: str | None,
) -> Select:
    stmt = (
        select(Transaction)
        .where(
            Transaction.tenant_id == auth.tenant_id,
            Transaction.shop_id == shop_id,
            Transaction.device_id == auth.device_id,
        )
        .options(selectinload(Transaction.lines), selectinload(Transaction.payments))
    )
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


def _product_labels_for_lines(db: Session, rows: list[Transaction]) -> dict[UUID, tuple[str, str]]:
    pids: set[UUID] = set()
    for t in rows:
        for ln in t.lines:
            pids.add(ln.product_id)
    if not pids:
        return {}
    products = db.execute(select(Product).where(Product.id.in_(pids))).scalars().all()
    return {p.id: (p.sku, p.name) for p in products}


def _line_dto(ln: TransactionLine, labels: dict[UUID, tuple[str, str]]) -> TransactionLineOut:
    lab = labels.get(ln.product_id)
    return TransactionLineOut(
        product_id=ln.product_id,
        product_sku=lab[0] if lab else None,
        product_name=lab[1] if lab else None,
        quantity=ln.quantity,
        unit_price_cents=ln.unit_price_cents,
    )


@router.get("/shift-summary", response_model=ShiftSummaryOut)
def shift_summary(
    shop_id: UUID,
    auth: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
    since: datetime | None = Query(
        default=None,
        description="ISO UTC timestamp; default start of current UTC day.",
    ),
) -> ShiftSummaryOut:
    if shop_id not in auth.shop_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shop not allowed")
    since_eff = since
    if since_eff is None:
        now = datetime.now(UTC)
        since_eff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if since_eff.tzinfo is None:
        since_eff = since_eff.replace(tzinfo=UTC)

    cnt, total = db.execute(
        select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.total_cents), 0)).where(
            Transaction.tenant_id == auth.tenant_id,
            Transaction.shop_id == shop_id,
            Transaction.device_id == auth.device_id,
            Transaction.created_at >= since_eff,
        )
    ).one()

    return ShiftSummaryOut(
        transaction_count=int(cnt),
        total_cents=int(total),
        since=since_eff,
    )


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    shop_id: UUID,
    auth: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    status: str | None = Query(
        default=None,
        description="Comma-separated: posted,refunded,pending",
    ),
    q: str | None = Query(default=None, description="Filter by line product name or SKU (substring)."),
) -> TransactionListResponse:
    if shop_id not in auth.shop_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shop not allowed")
    statuses = _parse_status_filter(status)

    stmt = _transactions_base_stmt(auth, shop_id, statuses=statuses, search=q)
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
