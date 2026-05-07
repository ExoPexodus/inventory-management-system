"""Customer self-service portal — profile and order history."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Customer, Order, OrderLine
from app.routers.storefront.auth import CustomerAuthDep, StorefrontChannelDep

router = APIRouter(prefix="/v1/storefront/customers", tags=["Customer Portal"])


class CustomerProfileOut(BaseModel):
    email: str
    name: str | None
    customer_id: str | None


class OrderLineOut(BaseModel):
    title: str
    sku: str | None
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    model_config = {"from_attributes": True}


class CustomerOrderOut(BaseModel):
    id: UUID
    status: str
    total_cents: int
    currency_code: str
    placed_at: datetime
    lines: list[OrderLineOut]


@router.get("/me", response_model=CustomerProfileOut)
def get_profile(
    customer: CustomerAuthDep,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> CustomerProfileOut:
    cust = db.execute(
        select(Customer).where(
            Customer.tenant_id == customer.tenant_id,
            Customer.email == customer.email,
        )
    ).scalar_one_or_none()
    return CustomerProfileOut(
        email=customer.email,
        name=cust.name if cust else None,
        customer_id=str(cust.id) if cust else None,
    )


@router.get("/me/orders", response_model=list[CustomerOrderOut])
def get_order_history(
    customer: CustomerAuthDep,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[CustomerOrderOut]:
    orders = db.execute(
        select(Order)
        .where(
            Order.tenant_id == customer.tenant_id,
            Order.customer_email == customer.email,
        )
        .order_by(Order.placed_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    result = []
    for order in orders:
        lines = db.execute(
            select(OrderLine).where(OrderLine.order_id == order.id)
        ).scalars().all()
        result.append(CustomerOrderOut(
            id=order.id,
            status=order.status,
            total_cents=order.total_cents,
            currency_code=order.currency_code,
            placed_at=order.placed_at,
            lines=list(lines),
        ))
    return result
