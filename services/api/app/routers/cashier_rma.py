"""Cashier-initiated RMA endpoint.

Cashier creates a refund request against a POS transaction.
Auth: device JWT.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import DeviceAuth, get_device_auth
from app.db.session import get_db
from app.models import Product, RefundRequest, Transaction, TransactionLine
from app.services import rma_service as svc
from app.services.rma_service import CreateLineInput

router = APIRouter(prefix="/v1/cashier/refund-requests", tags=["Cashier RMA"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CashierLineInput(BaseModel):
    transaction_line_id: UUID
    quantity_requested: int = Field(ge=1)


class CashierCreateRefundBody(BaseModel):
    sale_transaction_id: UUID
    refund_type: str = "refund_only"
    reason_code: str
    reason_note: str | None = None
    customer_email: str | None = None
    customer_name: str | None = None
    lines: list[CashierLineInput] = Field(min_length=1)


class RefundRequestOut(BaseModel):
    id: UUID
    sale_transaction_id: UUID | None
    refund_type: str
    status: str
    reason_code: str
    total_refund_cents: int
    currency_code: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=RefundRequestOut, status_code=status.HTTP_201_CREATED)
def create_cashier_refund_request(
    body: CashierCreateRefundBody,
    device: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> RefundRequestOut:
    from app.db.rls import set_rls_context
    set_rls_context(db, is_admin=False, tenant_id=device.tenant_id)

    if body.reason_code == "other" and not (body.reason_note or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reason_note is required when reason_code is 'other'",
        )

    # Validate transaction belongs to this device's tenant
    txn = db.execute(
        select(Transaction).where(
            Transaction.id == body.sale_transaction_id,
            Transaction.tenant_id == device.tenant_id,
        )
    ).scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # Build lines from transaction_lines
    lines = []
    for li in body.lines:
        tl = db.execute(
            select(TransactionLine).where(
                TransactionLine.id == li.transaction_line_id,
                TransactionLine.transaction_id == txn.id,
            )
        ).scalar_one_or_none()
        if tl is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction line {li.transaction_line_id} not found",
            )
        product_name = "Unknown"
        product_sku = None
        if tl.product_id:
            prod = db.get(Product, tl.product_id)
            if prod:
                product_name = prod.name or product_name
                product_sku = prod.sku

        lines.append(CreateLineInput(
            order_line_id=None,
            transaction_line_id=tl.id,
            product_id=tl.product_id,
            product_name=product_name,
            product_sku=product_sku,
            quantity_requested=li.quantity_requested,
            unit_price_cents=tl.unit_price_cents,
        ))

    req = svc.create_refund_request(
        db,
        tenant_id=device.tenant_id,
        sale_transaction=txn,
        refund_type=body.refund_type,
        reason_code=body.reason_code,
        reason_note=body.reason_note,
        lines=lines,
        customer_id=txn.customer_id,
        customer_email=body.customer_email,
        customer_name=body.customer_name,
    )
    db.commit()
    db.refresh(req)
    return RefundRequestOut.model_validate(req)
