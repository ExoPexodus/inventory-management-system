"""Storefront customer-facing RMA endpoints.

All endpoints require a valid customer JWT (CustomerAuthDep).
Customers can only see and manage their own refund requests.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.rls import set_rls_context
from app.db.session import get_db
from app.models import Order, OrderLine, Product, RefundRequest, RefundRequestLine, Transaction, TransactionLine
from app.routers.storefront.auth import CustomerAuthDep, StorefrontChannelDep
from app.services import rma_service as svc
from app.services.rma_service import CreateLineInput

router = APIRouter(prefix="/v1/storefront/refund-requests", tags=["Storefront RMA"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RefundRequestLineOut(BaseModel):
    id: UUID
    product_id: UUID | None
    product_name: str
    product_sku: str | None
    quantity_requested: int
    quantity_approved: int
    unit_price_cents: int
    line_refund_cents: int
    model_config = {"from_attributes": True}


class RefundRequestOut(BaseModel):
    id: UUID
    order_id: UUID | None
    refund_type: str
    status: str
    reason_code: str
    reason_note: str | None
    total_refund_cents: int
    currency_code: str
    lines: list[RefundRequestLineOut]
    created_at: datetime
    approved_at: datetime | None
    refunded_at: datetime | None
    model_config = {"from_attributes": True}


class LineInput(BaseModel):
    order_line_id: UUID | None = None
    quantity_requested: int = Field(ge=1)
    exchange_for_product_id: UUID | None = None


class CreateRefundBody(BaseModel):
    order_id: UUID
    refund_type: str
    reason_code: str
    reason_note: str | None = None
    lines: list[LineInput] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=RefundRequestOut, status_code=status.HTTP_201_CREATED)
def create_refund_request(
    body: CreateRefundBody,
    customer: CustomerAuthDep,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> RefundRequestOut:
    set_rls_context(db, is_admin=False, tenant_id=customer.tenant_id)

    if body.reason_code == "other" and not (body.reason_note or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reason_note is required when reason_code is 'other'",
        )

    # Verify order belongs to this customer
    order = db.execute(
        select(Order).where(
            Order.id == body.order_id,
            Order.tenant_id == customer.tenant_id,
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.customer_id != customer.customer_id and order.customer_email != customer.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This order does not belong to your account",
        )

    # Build line inputs from order lines
    lines = _build_storefront_lines(db, body.lines, order)

    req = svc.create_refund_request(
        db,
        tenant_id=customer.tenant_id,
        order=order,
        refund_type=body.refund_type,
        reason_code=body.reason_code,
        reason_note=body.reason_note,
        lines=lines,
        customer_id=customer.customer_id,
        customer_email=customer.email,
        channel_id=channel.id,
    )
    db.commit()
    db.refresh(req)
    return RefundRequestOut.model_validate(req)


@router.get("", response_model=list[RefundRequestOut])
def list_refund_requests(
    customer: CustomerAuthDep,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[RefundRequestOut]:
    set_rls_context(db, is_admin=False, tenant_id=customer.tenant_id)
    reqs = db.execute(
        select(RefundRequest).where(
            RefundRequest.tenant_id == customer.tenant_id,
            RefundRequest.customer_id == customer.customer_id,
        ).order_by(RefundRequest.created_at.desc())
    ).scalars().all()
    return [RefundRequestOut.model_validate(r) for r in reqs]


@router.get("/{rma_id}", response_model=RefundRequestOut)
def get_refund_request(
    rma_id: UUID,
    customer: CustomerAuthDep,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> RefundRequestOut:
    set_rls_context(db, is_admin=False, tenant_id=customer.tenant_id)
    req = db.execute(
        select(RefundRequest).where(
            RefundRequest.id == rma_id,
            RefundRequest.tenant_id == customer.tenant_id,
            RefundRequest.customer_id == customer.customer_id,
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund request not found")
    return RefundRequestOut.model_validate(req)


@router.post("/{rma_id}/cancel", response_model=RefundRequestOut)
def cancel_refund_request(
    rma_id: UUID,
    customer: CustomerAuthDep,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> RefundRequestOut:
    set_rls_context(db, is_admin=False, tenant_id=customer.tenant_id)
    req = db.execute(
        select(RefundRequest).where(
            RefundRequest.id == rma_id,
            RefundRequest.tenant_id == customer.tenant_id,
            RefundRequest.customer_id == customer.customer_id,
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund request not found")
    req = svc.cancel_refund_request(db, request=req, by_customer=True)
    db.commit()
    db.refresh(req)
    return RefundRequestOut.model_validate(req)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_storefront_lines(
    db: Session,
    line_inputs: list[LineInput],
    order: Order,
) -> list[CreateLineInput]:
    result = []
    for li in line_inputs:
        product_name = "Unknown"
        product_sku = None
        unit_price_cents = 0
        product_id = None

        if li.order_line_id:
            ol = db.execute(
                select(OrderLine).where(
                    OrderLine.id == li.order_line_id,
                    OrderLine.order_id == order.id,
                )
            ).scalar_one_or_none()
            if ol is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Order line {li.order_line_id} not found on this order",
                )
            product_name = ol.title or product_name
            product_sku = ol.sku
            unit_price_cents = ol.unit_price_cents
            product_id = ol.product_id

        result.append(CreateLineInput(
            order_line_id=li.order_line_id,
            transaction_line_id=None,
            product_id=product_id,
            product_name=product_name,
            product_sku=product_sku,
            quantity_requested=li.quantity_requested,
            unit_price_cents=unit_price_cents,
            exchange_for_product_id=li.exchange_for_product_id,
        ))
    return result
