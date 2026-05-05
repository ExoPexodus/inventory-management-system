"""FastAPI dependencies that expose entitlements and engineering flags to route handlers.

Usage in a route::

    from app.billing.deps import EntitlementsDep

    @router.get("/v1/admin/headless/products")
    def list_products(ents: EntitlementsDep, ...) -> ...:
        ents.require("headless_api")     # 403 if plan does not include
        return ...

For numeric limits::

    if existing_count >= ents.limit("max_channels"):
        raise HTTPException(...)

The dependency depends on the same admin auth chain as ``LicenseContextDep``
and reuses the cached license-context's plan_codename — no extra DB hit.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.license_deps import LicenseContextDep
from app.billing.entitlements import Entitlements, resolve_for_tenant
from app.db.admin_deps_db import get_db_admin


def _load_entitlements(
    license_ctx: LicenseContextDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> Entitlements:
    return resolve_for_tenant(db, license_ctx.tenant_id, license_ctx.plan_codename)


EntitlementsDep = Annotated[Entitlements, Depends(_load_entitlements)]
