from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import StockMovement, Transaction

router = APIRouter(prefix="/v1/audit", tags=["Audit"])


class AuditEntryOut(BaseModel):
    kind: str
    ref_id: UUID
    created_at: str
    detail: str


@router.get("/events", response_model=list[AuditEntryOut])
def list_audit_events(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    limit: int = 100,
) -> list[AuditEntryOut]:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant-scoped operator required",
        )
    txns = db.execute(
        select(Transaction)
        .where(Transaction.tenant_id == ctx.tenant_id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    ).scalars().all()
    moves = db.execute(
        select(StockMovement)
        .where(StockMovement.tenant_id == ctx.tenant_id)
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
    ).scalars().all()
    items: list[AuditEntryOut] = []
    for t in txns:
        items.append(
            AuditEntryOut(
                kind="transaction",
                ref_id=t.id,
                created_at=t.created_at.isoformat(),
                detail=f"{t.kind}:{t.status}:{t.total_cents}",
            )
        )
    for m in moves:
        items.append(
            AuditEntryOut(
                kind="stock_movement",
                ref_id=m.id,
                created_at=m.created_at.isoformat(),
                detail=f"{m.movement_type}:{m.quantity_delta}",
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:limit]

