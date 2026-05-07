"""Admin endpoints for managing outbound webhook endpoints.

Merchants register HTTPS URLs that IMS will POST to when events occur
(e.g. order.confirmed). Each endpoint gets a signing secret for HMAC
verification on the merchant side.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import WebhookDeliveryLog, WebhookEndpoint
from app.services.webhook_service import SUPPORTED_EVENTS, generate_secret

router = APIRouter(
    prefix="/v1/admin/webhooks",
    tags=["Webhook Endpoints"],
    dependencies=[require_permission("webhooks:manage")],
)


class EndpointIn(BaseModel):
    url: str = Field(min_length=10, max_length=512)
    events: list[str] = Field(min_length=1)
    description: str = Field(default="", max_length=255)


class EndpointOut(BaseModel):
    id: UUID
    url: str
    events: list[str]
    status: str
    description: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class EndpointCreatedOut(EndpointOut):
    secret: str  # only returned on creation


class EndpointUpdateIn(BaseModel):
    events: list[str] | None = None
    status: str | None = None
    description: str | None = None


class DeliveryLogOut(BaseModel):
    id: UUID
    endpoint_id: UUID
    event_type: str
    status: str
    response_status: int | None
    attempt_count: int
    delivered_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_endpoint_or_404(db: Session, endpoint_id: UUID, tenant_id: UUID) -> WebhookEndpoint:
    ep = db.get(WebhookEndpoint, endpoint_id)
    if ep is None or ep.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    return ep


@router.get("/supported-events", response_model=list[str])
def list_supported_events() -> list[str]:
    return sorted(SUPPORTED_EVENTS)


@router.get("/endpoints", response_model=list[EndpointOut])
def list_endpoints(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[WebhookEndpoint]:
    tenant_id = _require_tenant(ctx)
    return list(db.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.tenant_id == tenant_id)
        .order_by(WebhookEndpoint.created_at.desc())
    ).scalars().all())


@router.post("/endpoints", response_model=EndpointCreatedOut, status_code=status.HTTP_201_CREATED)
def create_endpoint(
    body: EndpointIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EndpointCreatedOut:
    tenant_id = _require_tenant(ctx)
    unknown = [e for e in body.events if e not in SUPPORTED_EVENTS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported events: {', '.join(unknown)}")

    secret = generate_secret()
    ep = WebhookEndpoint(
        tenant_id=tenant_id,
        url=body.url.strip(),
        secret=secret,
        events=body.events,
        description=body.description.strip() or None,
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return EndpointCreatedOut(
        id=ep.id, url=ep.url, events=ep.events, status=ep.status,
        description=ep.description, created_at=ep.created_at, secret=secret,
    )


@router.patch("/endpoints/{endpoint_id}", response_model=EndpointOut)
def update_endpoint(
    endpoint_id: UUID,
    body: EndpointUpdateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> WebhookEndpoint:
    tenant_id = _require_tenant(ctx)
    ep = _get_endpoint_or_404(db, endpoint_id, tenant_id)
    if body.events is not None:
        unknown = [e for e in body.events if e not in SUPPORTED_EVENTS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unsupported events: {', '.join(unknown)}")
        ep.events = body.events
    if body.status is not None:
        if body.status not in ("active", "disabled"):
            raise HTTPException(status_code=400, detail="status must be 'active' or 'disabled'")
        ep.status = body.status
    if body.description is not None:
        ep.description = body.description.strip() or None
    db.commit()
    db.refresh(ep)
    return ep


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(
    endpoint_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    ep = _get_endpoint_or_404(db, endpoint_id, tenant_id)
    db.delete(ep)
    db.commit()


@router.post("/endpoints/{endpoint_id}/rotate-secret", response_model=EndpointCreatedOut)
def rotate_secret(
    endpoint_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EndpointCreatedOut:
    """Generate a new signing secret for an endpoint."""
    tenant_id = _require_tenant(ctx)
    ep = _get_endpoint_or_404(db, endpoint_id, tenant_id)
    new_secret = generate_secret()
    ep.secret = new_secret
    db.commit()
    db.refresh(ep)
    return EndpointCreatedOut(
        id=ep.id, url=ep.url, events=ep.events, status=ep.status,
        description=ep.description, created_at=ep.created_at, secret=new_secret,
    )


@router.get("/deliveries", response_model=list[DeliveryLogOut])
def list_deliveries(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    limit: int = 50,
) -> list[WebhookDeliveryLog]:
    tenant_id = _require_tenant(ctx)
    return list(db.execute(
        select(WebhookDeliveryLog)
        .where(WebhookDeliveryLog.tenant_id == tenant_id)
        .order_by(WebhookDeliveryLog.created_at.desc())
        .limit(min(limit, 200))
    ).scalars().all())
