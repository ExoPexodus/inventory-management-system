"""Per-request Postgres session variables for row-level security policies."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def set_rls_context(db: Session, *, is_admin: bool, tenant_id: UUID | None) -> None:
    """Maps to GUCs read by RLS policies (see alembic RLS migration). Uses transaction-local set_config."""
    if is_admin:
        db.execute(text("SELECT set_config('ims.is_admin', 'true', true)"))
        db.execute(text("SELECT set_config('ims.tenant_id', '', true)"))
        return
    db.execute(text("SELECT set_config('ims.is_admin', '', true)"))
    tid = str(tenant_id) if tenant_id is not None else ""
    db.execute(text("SELECT set_config('ims.tenant_id', :tid, true)"), {"tid": tid})
