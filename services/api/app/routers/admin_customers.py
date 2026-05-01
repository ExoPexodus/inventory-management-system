"""Admin CRM — customer profiles, groups, and purchase history."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Customer, CustomerGroup, Shop, Transaction
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/admin", tags=["Admin CRM"])


def _require_tenant(ctx: AdminContext) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Legacy token not allowed")
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant assigned")
    return ctx.tenant_id


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class CustomerGroupOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    colour: str | None = None
    created_at: datetime


class CustomerOut(BaseModel):
    id: UUID
    tenant_id: UUID
    group_id: UUID | None = None
    group_name: str | None = None
    phone: str
    name: str | None = None
    email: str | None = None
    city: str | None = None
    created_at: datetime


class TxSummary(BaseModel):
    id: UUID
    created_at: datetime
    shop_name: str | None = None
    total_cents: int
    status: str


class CustomerDetailOut(BaseModel):
    id: UUID
    tenant_id: UUID
    group_id: UUID | None = None
    group_name: str | None = None
    phone: str
    name: str | None = None
    email: str | None = None
    address_line1: str | None = None
    city: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    transactions: list[TxSummary] = []


class CustomerLookupItem(BaseModel):
    id: UUID
    phone: str
    name: str | None = None
    group_name: str | None = None


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CreateCustomerBody(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    notes: str | None = None
    group_id: UUID | None = None


class PatchCustomerBody(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    notes: str | None = None
    group_id: UUID | None = None

    model_config = {"extra": "forbid"}


class CreateGroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    colour: str | None = Field(default=None, max_length=7)


class PatchGroupBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    colour: str | None = Field(default=None, max_length=7)

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_customer_out(c: Customer) -> CustomerOut:
    return CustomerOut(
        id=c.id,
        tenant_id=c.tenant_id,
        group_id=c.group_id,
        group_name=c.group.name if c.group else None,
        phone=c.phone,
        name=c.name,
        email=c.email,
        city=c.city,
        created_at=c.created_at,
    )


def _resolve_group(db: Session, tenant_id: UUID, group_id: UUID | None) -> CustomerGroup | None:
    if group_id is None:
        return None
    g = db.get(CustomerGroup, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer_group_not_found")
    if g.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross_tenant_access")
    return g


# ---------------------------------------------------------------------------
# Customer group endpoints
# ---------------------------------------------------------------------------


@router.get("/customer-groups", response_model=list[CustomerGroupOut],
            dependencies=[require_permission("customers:read")])
def list_customer_groups(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[CustomerGroupOut]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(CustomerGroup).where(CustomerGroup.tenant_id == tenant_id)
        .order_by(CustomerGroup.name.asc())
    ).scalars().all()
    return [CustomerGroupOut(id=r.id, tenant_id=r.tenant_id, name=r.name,
                             colour=r.colour, created_at=r.created_at) for r in rows]


@router.post("/customer-groups", response_model=CustomerGroupOut,
             dependencies=[require_permission("customers:write")])
def create_customer_group(
    body: CreateGroupBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CustomerGroupOut:
    tenant_id = _require_tenant(ctx)
    g = CustomerGroup(tenant_id=tenant_id, name=body.name.strip(), colour=body.colour)
    db.add(g)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="group_name_conflict")
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id,
                action="create_customer_group", resource_type="customer_group", resource_id=str(g.id))
    db.commit()
    db.refresh(g)
    return CustomerGroupOut(id=g.id, tenant_id=g.tenant_id, name=g.name,
                            colour=g.colour, created_at=g.created_at)


@router.patch("/customer-groups/{group_id}", response_model=CustomerGroupOut,
              dependencies=[require_permission("customers:write")])
def patch_customer_group(
    group_id: UUID,
    body: PatchGroupBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CustomerGroupOut:
    tenant_id = _require_tenant(ctx)
    g = db.get(CustomerGroup, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group_not_found")
    if g.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross_tenant_access")
    sent = body.model_fields_set
    if "name" in sent and body.name is not None:
        g.name = body.name.strip()
    if "colour" in sent:
        g.colour = body.colour
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id,
                action="update_customer_group", resource_type="customer_group", resource_id=str(group_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="group_name_conflict")
    db.refresh(g)
    return CustomerGroupOut(id=g.id, tenant_id=g.tenant_id, name=g.name,
                            colour=g.colour, created_at=g.created_at)


@router.delete("/customer-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("customers:write")])
def delete_customer_group(
    group_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    g = db.get(CustomerGroup, group_id)
    if g is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group_not_found")
    if g.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross_tenant_access")
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id,
                action="delete_customer_group", resource_type="customer_group", resource_id=str(group_id))
    db.delete(g)
    db.commit()


# ---------------------------------------------------------------------------
# Customer endpoints
# ---------------------------------------------------------------------------


@router.get("/customers/lookup", response_model=list[CustomerLookupItem],
            dependencies=[require_permission("customers:read")])
def lookup_customers(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    q: str = Query(min_length=2, max_length=100),
) -> list[CustomerLookupItem]:
    tenant_id = _require_tenant(ctx)
    q_esc = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    stmt = (
        select(Customer)
        .options(selectinload(Customer.group))
        .where(
            Customer.tenant_id == tenant_id,
            (
                Customer.phone.ilike(f"{q_esc}%", escape="\\")
                | Customer.name.ilike(f"%{q_esc}%", escape="\\")
            ),
        )
        .order_by(Customer.name.asc())
        .limit(10)
    )
    rows = db.execute(stmt).scalars().all()
    return [CustomerLookupItem(id=r.id, phone=r.phone, name=r.name,
                               group_name=r.group.name if r.group else None) for r in rows]


@router.get("/customers", response_model=list[CustomerOut],
            dependencies=[require_permission("customers:read")])
def list_customers(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    q: str | None = None,
    group_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CustomerOut]:
    tenant_id = _require_tenant(ctx)
    stmt = (
        select(Customer)
        .options(selectinload(Customer.group))
        .where(Customer.tenant_id == tenant_id)
        .order_by(Customer.created_at.desc())
        .limit(limit)
    )
    if q and q.strip():
        q_esc = q.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        stmt = stmt.where(
            Customer.phone.ilike(f"{q_esc}%", escape="\\")
            | Customer.name.ilike(f"%{q_esc}%", escape="\\")
        )
    if group_id:
        stmt = stmt.where(Customer.group_id == group_id)
    rows = db.execute(stmt).scalars().all()
    return [_to_customer_out(r) for r in rows]


@router.post("/customers", response_model=CustomerOut,
             dependencies=[require_permission("customers:write")])
def create_customer(
    body: CreateCustomerBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CustomerOut:
    tenant_id = _require_tenant(ctx)
    group = _resolve_group(db, tenant_id, body.group_id)
    c = Customer(
        tenant_id=tenant_id,
        group_id=group.id if group else None,
        phone=body.phone.strip(),
        name=(body.name.strip() or None) if body.name else None,
        email=(body.email.strip() or None) if body.email else None,
        address_line1=(body.address_line1.strip() or None) if body.address_line1 else None,
        city=(body.city.strip() or None) if body.city else None,
        notes=(body.notes.strip() or None) if body.notes else None,
    )
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="phone_conflict")
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id,
                action="create_customer", resource_type="customer", resource_id=str(c.id),
                after={"phone": c.phone})
    db.commit()
    db.refresh(c)
    if c.group_id:
        db.refresh(c, attribute_names=["group"])
    return _to_customer_out(c)


@router.get("/customers/{customer_id}", response_model=CustomerDetailOut,
            dependencies=[require_permission("customers:read")])
def get_customer(
    customer_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CustomerDetailOut:
    tenant_id = _require_tenant(ctx)
    c = db.execute(
        select(Customer).options(selectinload(Customer.group))
        .where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer_not_found")

    # Last 50 transactions for this customer
    txns = db.execute(
        select(Transaction, Shop.name.label("shop_name"))
        .join(Shop, Shop.id == Transaction.shop_id)
        .where(Transaction.customer_id == customer_id, Transaction.tenant_id == tenant_id)
        .order_by(Transaction.created_at.desc())
        .limit(50)
    ).all()

    tx_summaries = [
        TxSummary(
            id=row.Transaction.id,
            created_at=row.Transaction.created_at,
            shop_name=row.shop_name,
            total_cents=row.Transaction.total_cents,
            status=row.Transaction.status,
        )
        for row in txns
    ]

    return CustomerDetailOut(
        id=c.id,
        tenant_id=c.tenant_id,
        group_id=c.group_id,
        group_name=c.group.name if c.group else None,
        phone=c.phone,
        name=c.name,
        email=c.email,
        address_line1=c.address_line1,
        city=c.city,
        notes=c.notes,
        created_at=c.created_at,
        updated_at=c.updated_at,
        transactions=tx_summaries,
    )


@router.patch("/customers/{customer_id}", response_model=CustomerOut,
              dependencies=[require_permission("customers:write")])
def patch_customer(
    customer_id: UUID,
    body: PatchCustomerBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CustomerOut:
    tenant_id = _require_tenant(ctx)
    c = db.execute(
        select(Customer).options(selectinload(Customer.group))
        .where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer_not_found")

    sent = body.model_fields_set
    if "name" in sent:
        c.name = (body.name.strip() or None) if body.name else None
    if "email" in sent:
        c.email = (body.email.strip() or None) if body.email else None
    if "address_line1" in sent:
        c.address_line1 = (body.address_line1.strip() or None) if body.address_line1 else None
    if "city" in sent:
        c.city = (body.city.strip() or None) if body.city else None
    if "notes" in sent:
        c.notes = body.notes
    if "group_id" in sent:
        group = _resolve_group(db, tenant_id, body.group_id)
        c.group_id = group.id if group else None

    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id,
                action="update_customer", resource_type="customer", resource_id=str(customer_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="phone_conflict")
    db.refresh(c)
    if c.group_id:
        db.refresh(c, attribute_names=["group"])
    return _to_customer_out(c)


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("customers:write")])
def delete_customer(
    customer_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="customer_not_found")
    if c.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross_tenant_access")
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id,
                action="delete_customer", resource_type="customer", resource_id=str(customer_id))
    db.delete(c)
    db.commit()
