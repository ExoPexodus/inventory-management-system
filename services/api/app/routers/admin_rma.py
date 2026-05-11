"""Admin endpoints for the RMA / Refund Request flow."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import (
    Channel,
    Order,
    OrderLine,
    Product,
    RefundRequest,
    RefundRequestEvent,
    RefundRequestLine,
    Tenant,
    Transaction,
    TransactionLine,
)
from app.services import rma_service as svc
from app.services.rma_service import ApprovalLineInput, CreateLineInput

router = APIRouter(prefix="/v1/admin/rma", tags=["Admin RMA"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class EventOut(BaseModel):
    id: UUID
    event_type: str
    from_status: str | None
    to_status: str | None
    actor_user_id: UUID | None
    actor_kind: str
    event_metadata: Any | None
    created_at: datetime
    model_config = {"from_attributes": True}


class LineOut(BaseModel):
    id: UUID
    order_line_id: UUID | None
    transaction_line_id: UUID | None
    product_id: UUID | None
    product_name: str
    product_sku: str | None
    quantity_requested: int
    quantity_approved: int
    unit_price_cents: int
    restock_on_approval: bool
    line_refund_cents: int
    exchange_for_product_id: UUID | None
    model_config = {"from_attributes": True}


class RefundRequestListItem(BaseModel):
    id: UUID
    customer_email: str | None
    customer_name: str | None
    refund_type: str
    status: str
    reason_code: str
    total_refund_cents: int
    currency_code: str
    order_id: UUID | None
    sale_transaction_id: UUID | None
    created_at: datetime
    model_config = {"from_attributes": True}


class RefundRequestDetail(BaseModel):
    id: UUID
    tenant_id: UUID
    order_id: UUID | None
    sale_transaction_id: UUID | None
    channel_id: UUID | None
    customer_id: UUID | None
    customer_email: str | None
    customer_name: str | None
    refund_type: str
    status: str
    reason_code: str
    reason_note: str | None
    refund_shipping: bool
    return_shipping_required: bool
    return_shipping_awb: str | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    rejected_reason: str | None
    rejected_at: datetime | None
    cancelled_at: datetime | None
    received_at: datetime | None
    refunded_at: datetime | None
    closed_at: datetime | None
    total_refund_cents: int
    currency_code: str
    provider_refund_ref: str | None
    cash_returned: bool
    cash_returned_at: datetime | None
    auto_approved: bool
    created_at: datetime
    updated_at: datetime
    lines: list[LineOut]
    events: list[EventOut]
    model_config = {"from_attributes": True}


class LineApprovalInput(BaseModel):
    line_id: UUID
    quantity_approved: int = Field(ge=0)
    restock: bool = True


class ApproveBody(BaseModel):
    line_approvals: list[LineApprovalInput] = Field(default_factory=list)
    refund_shipping: bool = False


class RejectBody(BaseModel):
    reason: str = Field(min_length=1)


class CommentBody(BaseModel):
    comment: str = Field(min_length=1)


class AdminCreateLineInput(BaseModel):
    order_line_id: UUID | None = None
    transaction_line_id: UUID | None = None
    product_id: UUID | None = None
    quantity_requested: int = Field(ge=1)
    exchange_for_product_id: UUID | None = None


class CreateRefundBody(BaseModel):
    order_id: UUID | None = None
    sale_transaction_id: UUID | None = None
    refund_type: str
    reason_code: str
    reason_note: str | None = None
    customer_email: str | None = None
    customer_name: str | None = None
    lines: list[AdminCreateLineInput] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_request(db: Session, rma_id: UUID, tenant_id: UUID) -> RefundRequest:
    req = db.execute(
        select(RefundRequest).where(
            RefundRequest.id == rma_id,
            RefundRequest.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund request not found")
    return req


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=dict, dependencies=[require_permission("rma:read")])
def list_refund_requests(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    status_filter: list[str] = Query(default=[], alias="status"),
    channel_id: UUID | None = Query(default=None),
    customer_email: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")

    stmt = select(RefundRequest).where(RefundRequest.tenant_id == ctx.tenant_id)

    if status_filter:
        stmt = stmt.where(RefundRequest.status.in_(status_filter))
    if channel_id is not None:
        stmt = stmt.where(RefundRequest.channel_id == channel_id)
    if customer_email:
        stmt = stmt.where(RefundRequest.customer_email.ilike(f"%{customer_email}%"))
    if date_from:
        stmt = stmt.where(RefundRequest.created_at >= date_from)
    if date_to:
        stmt = stmt.where(RefundRequest.created_at <= date_to)
    if q:
        q_like = f"%{q}%"
        stmt = stmt.where(
            or_(
                RefundRequest.customer_email.ilike(q_like),
                RefundRequest.customer_name.ilike(q_like),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    count = db.execute(count_stmt).scalar_one()

    stmt = stmt.order_by(RefundRequest.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    items = db.execute(stmt).scalars().all()

    return {
        "items": [RefundRequestListItem.model_validate(r) for r in items],
        "total": count,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{rma_id}", response_model=RefundRequestDetail, dependencies=[require_permission("rma:read")])
def get_refund_request(
    rma_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)
    return RefundRequestDetail.model_validate(req)


@router.get("/{rma_id}/events", response_model=list[EventOut], dependencies=[require_permission("rma:read")])
def get_refund_request_events(
    rma_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[EventOut]:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)
    events = db.execute(
        select(RefundRequestEvent)
        .where(RefundRequestEvent.refund_request_id == req.id)
        .order_by(RefundRequestEvent.created_at)
    ).scalars().all()
    return [EventOut.model_validate(e) for e in events]


@router.post("", response_model=RefundRequestDetail, status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("rma:write")])
def create_refund_request_admin(
    body: CreateRefundBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    """Admin-initiated refund request (e.g. on behalf of a phone-in customer)."""
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")

    order = None
    sale_txn = None

    if body.order_id:
        order = db.execute(
            select(Order).where(Order.id == body.order_id, Order.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if body.sale_transaction_id:
        sale_txn = db.execute(
            select(Transaction).where(Transaction.id == body.sale_transaction_id, Transaction.tenant_id == ctx.tenant_id)
        ).scalar_one_or_none()
        if sale_txn is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    lines = _build_lines_from_admin_input(db, body.lines, order, sale_txn)

    req = svc.create_refund_request(
        db,
        tenant_id=ctx.tenant_id,
        order=order,
        sale_transaction=sale_txn,
        refund_type=body.refund_type,
        reason_code=body.reason_code,
        reason_note=body.reason_note,
        lines=lines,
        customer_email=body.customer_email or (order.customer_email if order else None),
        customer_name=body.customer_name,
    )
    db.commit()
    db.refresh(req)
    return RefundRequestDetail.model_validate(req)


@router.post("/{rma_id}/approve", response_model=RefundRequestDetail,
             dependencies=[require_permission("rma:write")])
def approve_refund_request(
    rma_id: UUID,
    body: ApproveBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)

    line_approvals: dict[UUID, ApprovalLineInput] = {}
    # Build a lookup of all lines by ID for default approvals
    for line in req.lines:
        line_approvals[line.id] = ApprovalLineInput(
            quantity_approved=line.quantity_requested,
            restock_on_approval=True,
        )
    # Override with explicitly provided approvals
    for la in body.line_approvals:
        line_approvals[la.line_id] = ApprovalLineInput(
            quantity_approved=la.quantity_approved,
            restock_on_approval=la.restock,
        )

    req = svc.approve_refund_request(
        db,
        request=req,
        approving_user_id=ctx.user_id,
        line_approvals=line_approvals,
        refund_shipping=body.refund_shipping,
    )
    db.commit()
    db.refresh(req)
    return RefundRequestDetail.model_validate(req)


@router.post("/{rma_id}/reject", response_model=RefundRequestDetail,
             dependencies=[require_permission("rma:write")])
def reject_refund_request(
    rma_id: UUID,
    body: RejectBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)
    req = svc.reject_refund_request(db, request=req, rejecting_user_id=ctx.user_id, reason=body.reason)
    db.commit()
    db.refresh(req)
    return RefundRequestDetail.model_validate(req)


@router.post("/{rma_id}/mark-received", response_model=RefundRequestDetail,
             dependencies=[require_permission("rma:write")])
def mark_received(
    rma_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)
    req = svc.mark_received(db, request=req, receiving_user_id=ctx.user_id)
    db.commit()
    db.refresh(req)
    return RefundRequestDetail.model_validate(req)


@router.post("/{rma_id}/mark-cash-returned", response_model=RefundRequestDetail,
             dependencies=[require_permission("rma:write")])
def mark_cash_returned(
    rma_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)
    req = svc.mark_cash_returned(db, request=req, user_id=ctx.user_id)
    db.commit()
    db.refresh(req)
    return RefundRequestDetail.model_validate(req)


@router.post("/{rma_id}/close", response_model=RefundRequestDetail,
             dependencies=[require_permission("rma:write")])
def close_refund_request(
    rma_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)
    req = svc.close_refund_request(db, request=req, user_id=ctx.user_id)
    db.commit()
    db.refresh(req)
    return RefundRequestDetail.model_validate(req)


@router.post("/{rma_id}/comment", response_model=EventOut,
             dependencies=[require_permission("rma:write")])
def add_comment(
    rma_id: UUID,
    body: CommentBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EventOut:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)
    evt = svc.add_comment(db, request=req, comment=body.comment, user_id=ctx.user_id)
    db.commit()
    db.refresh(evt)
    return EventOut.model_validate(evt)


@router.post("/{rma_id}/issue-return-awb", response_model=RefundRequestDetail,
             dependencies=[require_permission("rma:write")])
def issue_return_awb(
    rma_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RefundRequestDetail:
    """Issue a return (reverse) shipment AWB via the channel's configured shipping provider."""
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required")
    req = _get_request(db, rma_id, ctx.tenant_id)

    if req.status not in ("approved", "received"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Return AWB can only be issued for approved or received requests",
        )
    if not req.return_shipping_required:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This request does not require return shipping",
        )
    if req.return_shipping_awb:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Return AWB has already been issued for this request",
        )
    if req.order_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Return shipping is only supported for ecommerce orders, not POS sales",
        )

    channel = db.get(Channel, req.channel_id) if req.channel_id else None
    provider_name = (channel.config or {}).get("shipping_provider", "") if channel else ""

    if not provider_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No shipping provider configured for this channel. Issue return shipping manually.",
        )

    from app.services.shipping.base import ShippingProviderError
    from app.services.shipping.registry import get_provider
    try:
        provider = get_provider(provider_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown shipping provider '{provider_name}'",
        )
    if not hasattr(provider, "create_reverse_shipment"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Shipping provider '{provider_name}' does not support automated return AWB issuance",
        )

    order = db.get(Order, req.order_id)
    tenant = db.get(Tenant, ctx.tenant_id)
    lines_to_return = [ln for ln in req.lines if (ln.quantity_approved or ln.quantity_requested) > 0]

    try:
        result = provider.create_reverse_shipment(req, order, lines_to_return, tenant, channel.config or {})
    except ShippingProviderError as exc:
        svc._write_event(
            db, request=req, event_type="awb_issue_failed",
            metadata={"provider": provider_name, "error": str(exc)},
            actor_kind="system",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shipping provider rejected the return shipment: {exc}",
        )

    req.return_shipping_awb = result.awb_code
    svc._write_event(
        db, request=req, event_type="awb_issued",
        metadata={
            "provider": provider_name,
            "awb_code": result.awb_code,
            "carrier": result.carrier_name,
            "tracking_url": result.tracking_url,
        },
        actor_kind="merchant",
        actor_user_id=ctx.user_id,
    )
    db.commit()
    db.refresh(req)
    return _to_detail(db, req)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_lines_from_admin_input(
    db: Session,
    line_inputs: list[AdminCreateLineInput],
    order,
    sale_txn,
) -> list[CreateLineInput]:
    result = []
    for li in line_inputs:
        product_name = "Unknown"
        product_sku = None
        unit_price_cents = 0

        if li.order_line_id and order:
            ol = db.execute(
                select(OrderLine).where(OrderLine.id == li.order_line_id, OrderLine.order_id == order.id)
            ).scalar_one_or_none()
            if ol:
                product_name = ol.title or product_name
                product_sku = ol.sku
                unit_price_cents = ol.unit_price_cents

        elif li.transaction_line_id and sale_txn:
            tl = db.execute(
                select(TransactionLine).where(
                    TransactionLine.id == li.transaction_line_id,
                    TransactionLine.transaction_id == sale_txn.id,
                )
            ).scalar_one_or_none()
            if tl and tl.product_id:
                prod = db.get(Product, tl.product_id)
                if prod:
                    product_name = prod.name or product_name
                    product_sku = prod.sku
                unit_price_cents = tl.unit_price_cents

        elif li.product_id:
            prod = db.get(Product, li.product_id)
            if prod:
                product_name = prod.name or product_name
                product_sku = prod.sku

        result.append(CreateLineInput(
            order_line_id=li.order_line_id,
            transaction_line_id=li.transaction_line_id,
            product_id=li.product_id,
            product_name=product_name,
            product_sku=product_sku,
            quantity_requested=li.quantity_requested,
            unit_price_cents=unit_price_cents,
            exchange_for_product_id=li.exchange_for_product_id,
        ))
    return result
