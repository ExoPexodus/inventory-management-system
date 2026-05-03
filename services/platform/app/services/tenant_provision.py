"""Provision a newly created tenant in the main API.

Called after a platform tenant record is persisted. Makes a best-effort POST to
the API's provision endpoint. On failure, the caller is expected to roll back the
platform tenant so no orphan record is left behind.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.config import settings
from app.models.tables import PlatformTenant

logger = logging.getLogger(__name__)


@dataclass
class ProvisionResult:
    ok: bool
    tenant_status: str = ""
    operator_status: str = ""
    error: str = ""


def provision_tenant(
    tenant: PlatformTenant,
    admin_email: str,
    admin_password: str,
) -> ProvisionResult:
    """Call the main API to provision the tenant + initial admin operator."""
    url = f"{settings.main_api_url}/v1/admin/provision-tenant"
    try:
        resp = httpx.post(
            url,
            json={
                "tenant_id": str(tenant.id),
                "name": tenant.name,
                "slug": tenant.slug,
                "admin_email": admin_email,
                "admin_password": admin_password,
            },
            headers={"X-Admin-Token": settings.admin_api_token},
            timeout=15.0,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return ProvisionResult(
                ok=True,
                tenant_status=data.get("tenant_status", ""),
                operator_status=data.get("operator_status", ""),
            )
        error_msg = resp.json().get("detail", f"HTTP {resp.status_code}")
        logger.error("Tenant provision failed for %s: %s", tenant.slug, error_msg)
        return ProvisionResult(ok=False, error=error_msg)
    except Exception as exc:
        logger.exception("Tenant provision request failed for %s", tenant.slug)
        return ProvisionResult(ok=False, error=str(exc))
