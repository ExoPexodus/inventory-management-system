from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.admin_deps import require_admin_context
from app.db.rls import set_rls_context
from app.db.session import SessionLocal


def get_db_admin(
    _: Annotated[None, Depends(require_admin_context)],
) -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        set_rls_context(db, is_admin=True, tenant_id=None)
        yield db
    finally:
        db.close()
