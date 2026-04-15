"""Admin integrations endpoints — webhooks, API tokens, CSV import."""

from __future__ import annotations

import csv
import hashlib
import io
import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import ApiToken, Integration, Product, WebhookDelivery
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/admin/integrations", tags=["Admin Integrations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_tenant(ctx) -> UUID:
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


# ---------------------------------------------------------------------------
# Webhook models
# ---------------------------------------------------------------------------


class WebhookOut(BaseModel):
    id: UUID
    type: str
    status: str
    config_url: str | None
    config_events: list[str]
    last_sync_at: str | None
    created_at: str


class WebhookDeliveryOut(BaseModel):
    id: UUID
    event_type: str
    response_status: int | None
    attempts: int
    created_at: str


class CreateWebhookBody(BaseModel):
    url: str
    events: list[str]
    secret: str | None = None


# ---------------------------------------------------------------------------
# API token models
# ---------------------------------------------------------------------------


class ApiTokenOut(BaseModel):
    id: UUID
    name: str
    token_prefix: str
    scopes: list[str]
    last_used_at: str | None
    expires_at: str | None
    revoked_at: str | None
    created_at: str


class ApiTokenCreatedOut(ApiTokenOut):
    token: str  # full token, returned once only


class CreateApiTokenBody(BaseModel):
    name: str
    scopes: list[str] = []
    expires_at: str | None = None


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------


def _webhook_to_out(integ: Integration) -> WebhookOut:
    cfg = integ.config or {}
    return WebhookOut(
        id=integ.id,
        type=integ.type,
        status=integ.status,
        config_url=cfg.get("url"),
        config_events=cfg.get("events", []),
        last_sync_at=integ.last_sync_at.isoformat() if integ.last_sync_at else None,
        created_at=integ.created_at.isoformat(),
    )


@router.get("/webhooks", response_model=list[WebhookOut], dependencies=[require_permission("integrations:read")])
def list_webhooks(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[WebhookOut]:
    tenant_id = _require_tenant(ctx)
    items = db.execute(
        select(Integration).where(
            Integration.tenant_id == tenant_id,
            Integration.type == "webhook",
            Integration.status != "revoked",
        )
    ).scalars().all()
    return [_webhook_to_out(i) for i in items]


@router.post("/webhooks", response_model=WebhookOut, status_code=status.HTTP_201_CREATED, dependencies=[require_permission("integrations:write")])
def create_webhook(
    body: CreateWebhookBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> WebhookOut:
    tenant_id = _require_tenant(ctx)
    cfg: dict = {"url": body.url, "events": body.events}
    if body.secret:
        cfg["secret_hash"] = bcrypt.hashpw(body.secret.encode(), bcrypt.gensalt()).decode()
    integ = Integration(
        tenant_id=tenant_id,
        type="webhook",
        config=cfg,
        status="active",
    )
    db.add(integ)
    db.flush()
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="create_webhook", resource_type="webhook", resource_id=str(integ.id))
    db.commit()
    db.refresh(integ)
    return _webhook_to_out(integ)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[require_permission("integrations:write")])
def delete_webhook(
    webhook_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    integ = db.get(Integration, webhook_id)
    if integ is None or integ.tenant_id != tenant_id or integ.type != "webhook":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    integ.status = "revoked"
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="revoke_webhook", resource_type="webhook", resource_id=str(webhook_id))
    db.commit()


@router.get("/webhooks/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut], dependencies=[require_permission("integrations:read")])
def list_deliveries(
    webhook_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[WebhookDeliveryOut]:
    tenant_id = _require_tenant(ctx)
    integ = db.get(Integration, webhook_id)
    if integ is None or integ.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    items = db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.integration_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(20)
    ).scalars().all()
    return [
        WebhookDeliveryOut(
            id=d.id,
            event_type=d.event_type,
            response_status=d.response_status,
            attempts=d.attempts,
            created_at=d.created_at.isoformat(),
        )
        for d in items
    ]


# ---------------------------------------------------------------------------
# API token endpoints
# ---------------------------------------------------------------------------


def _token_to_out(t: ApiToken) -> ApiTokenOut:
    return ApiTokenOut(
        id=t.id,
        name=t.name,
        token_prefix=t.token_prefix,
        scopes=t.scopes or [],
        last_used_at=t.last_used_at.isoformat() if t.last_used_at else None,
        expires_at=t.expires_at.isoformat() if t.expires_at else None,
        revoked_at=t.revoked_at.isoformat() if t.revoked_at else None,
        created_at=t.created_at.isoformat(),
    )


@router.get("/api-tokens", response_model=list[ApiTokenOut], dependencies=[require_permission("integrations:read")])
def list_api_tokens(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ApiTokenOut]:
    tenant_id = _require_tenant(ctx)
    items = db.execute(
        select(ApiToken)
        .where(ApiToken.tenant_id == tenant_id)
        .order_by(ApiToken.created_at.desc())
    ).scalars().all()
    return [_token_to_out(t) for t in items]


@router.post("/api-tokens", response_model=ApiTokenCreatedOut, status_code=status.HTTP_201_CREATED, dependencies=[require_permission("integrations:write")])
def create_api_token(
    body: CreateApiTokenBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ApiTokenCreatedOut:
    tenant_id = _require_tenant(ctx)
    raw = "ims_" + secrets.token_urlsafe(32)
    prefix = raw[:12]
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()

    expires = None
    if body.expires_at:
        from datetime import datetime
        expires = datetime.fromisoformat(body.expires_at)

    tok = ApiToken(
        tenant_id=tenant_id,
        name=body.name,
        token_hash=hashed,
        token_prefix=prefix,
        scopes=body.scopes or [],
        expires_at=expires,
        created_by=ctx.operator_id,
    )
    db.add(tok)
    db.flush()
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="create_api_token", resource_type="api_token", resource_id=str(tok.id))
    db.commit()
    db.refresh(tok)
    out = _token_to_out(tok)
    return ApiTokenCreatedOut(**out.model_dump(), token=raw)


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[require_permission("integrations:write")])
def revoke_api_token(
    token_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    tok = db.get(ApiToken, token_id)
    if tok is None or tok.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    tok.revoked_at = datetime.now(UTC)
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="revoke_api_token", resource_type="api_token", resource_id=str(token_id))
    db.commit()


# ---------------------------------------------------------------------------
# CSV product import
# ---------------------------------------------------------------------------


class ImportResult(BaseModel):
    inserted: int
    updated: int
    errors: list[str]


@router.post("/products/import-csv", response_model=ImportResult, dependencies=[require_permission("integrations:write")])
async def import_products_csv(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    file: UploadFile = File(...),
) -> ImportResult:
    tenant_id = _require_tenant(ctx)

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    required_cols = {"sku", "name"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have columns: {', '.join(required_cols)}. Got: {reader.fieldnames}",
        )

    rows = list(reader)
    errors: list[str] = []
    validated = []
    for i, row in enumerate(rows, start=2):
        sku = (row.get("sku") or "").strip()
        name = (row.get("name") or "").strip()
        if not sku:
            errors.append(f"Row {i}: sku is required")
            continue
        if not name:
            errors.append(f"Row {i}: name is required")
            continue

        price_raw = (row.get("unit_price_cents") or "0").strip()
        try:
            price_cents = int(price_raw)
            if price_cents < 0:
                raise ValueError
        except ValueError:
            errors.append(f"Row {i}: unit_price_cents must be a non-negative integer, got '{price_raw}'")
            continue

        rp_raw = (row.get("reorder_point") or "0").strip()
        try:
            reorder_pt = int(rp_raw)
            if reorder_pt < 0:
                raise ValueError
        except ValueError:
            errors.append(f"Row {i}: reorder_point must be a non-negative integer, got '{rp_raw}'")
            continue

        validated.append({
            "sku": sku,
            "name": name,
            "category": (row.get("category") or "").strip() or None,
            "unit_price_cents": price_cents,
            "reorder_point": reorder_pt,
        })

    if errors:
        return ImportResult(inserted=0, updated=0, errors=errors)

    inserted = 0
    updated = 0
    existing_skus = {
        p.sku: p
        for p in db.execute(
            select(Product).where(
                Product.tenant_id == tenant_id,
                Product.sku.in_([r["sku"] for r in validated]),
            )
        ).scalars().all()
    }

    for r in validated:
        if r["sku"] in existing_skus:
            prod = existing_skus[r["sku"]]
            prod.name = r["name"]
            if r["category"] is not None:
                prod.category = r["category"]
            prod.unit_price_cents = r["unit_price_cents"]
            prod.reorder_point = r["reorder_point"]
            updated += 1
        else:
            prod = Product(
                tenant_id=tenant_id,
                sku=r["sku"],
                name=r["name"],
                category=r["category"],
                unit_price_cents=r["unit_price_cents"],
                reorder_point=r["reorder_point"],
                status="active",
            )
            db.add(prod)
            inserted += 1

    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="import_products_csv", resource_type="product", after={"inserted": inserted, "updated": updated})
    db.commit()
    return ImportResult(inserted=inserted, updated=updated, errors=[])
