"""App distribution endpoints — OTA update check and APK download proxy."""
from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.auth.deps import DeviceAuth, get_device_auth
from app.config import settings
from app.db.admin_deps_db import get_db_admin
from app.db.session import get_db
from app.models import Tenant

router = APIRouter(tags=["App Updates"])
logger = logging.getLogger(__name__)

_MANIFEST_TIMEOUT = 8  # seconds

_APP_META: dict[str, tuple[str, str]] = {
    "cashier": ("Cashier POS", "Offline-first point-of-sale app for your staff."),
    "admin_mobile": ("Admin Mobile", "Mobile companion for store owners and managers."),
}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class UpdateCheckOut(BaseModel):
    app_name: str
    version: str | None
    version_code: int | None
    changelog: str | None
    size_mb: float | None
    download_url: str | None
    available: bool


class AppInfo(BaseModel):
    app_name: str
    display_name: str
    description: str
    version: str | None
    version_code: int | None
    changelog: str | None
    size_mb: float | None
    available: bool
    admin_download_url: str | None


class DownloadsOut(BaseModel):
    download_page_url: str
    apps: list[AppInfo]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _platform_download_base() -> str:
    base = settings.platform_download_base_url or settings.platform_base_url
    return base.rstrip("/")


def _fetch_manifest(download_token: str) -> list[dict]:
    """Proxy the platform manifest. Returns [] on any network/parse error."""
    url = f"{settings.platform_base_url.rstrip('/')}/downloads/{download_token}/manifest"
    try:
        resp = httpx.get(url, timeout=_MANIFEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("apps", [])
    except Exception as exc:
        logger.warning("Failed to fetch platform manifest: %s", exc)
        return []


def _find_app(apps: list[dict], app_name: str) -> dict | None:
    return next((a for a in apps if a.get("app_name") == app_name), None)


def _apk_redirect_url(download_token: str, app_name: str) -> str:
    base = settings.platform_download_base_url
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PLATFORM_DOWNLOAD_BASE_URL is not configured — contact your administrator.",
        )
    return f"{base.rstrip('/')}/downloads/{download_token}/{app_name}/latest"


# ── Device endpoints ──────────────────────────────────────────────────────────

@router.get("/v1/apps/update-check", response_model=UpdateCheckOut)
def update_check(
    ctx: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
    app_name: str = Query(...),
) -> UpdateCheckOut:
    if app_name not in _APP_META:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown app_name")

    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None or not tenant.download_token:
        return UpdateCheckOut(
            app_name=app_name, version=None, version_code=None,
            changelog=None, size_mb=None, download_url=None, available=False,
        )

    apps = _fetch_manifest(tenant.download_token)
    app = _find_app(apps, app_name)
    if app is None or not app.get("available"):
        return UpdateCheckOut(
            app_name=app_name, version=None, version_code=None,
            changelog=None, size_mb=None, download_url=None, available=False,
        )

    download_url = f"{settings.public_api_url.rstrip('/')}/v1/apps/{app_name}/download"
    return UpdateCheckOut(
        app_name=app_name,
        version=app.get("version"),
        version_code=app.get("version_code"),
        changelog=app.get("changelog"),
        size_mb=app.get("size_mb"),
        download_url=download_url,
        available=True,
    )


# ── Admin update-check (operator JWT) ────────────────────────────────────────

@router.get(
    "/v1/admin/apps/update-check",
    response_model=UpdateCheckOut,
    dependencies=[require_permission("settings:read")],
)
def admin_update_check(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    app_name: str = Query(...),
) -> UpdateCheckOut:
    """Update check for the admin mobile app using operator JWT (avoids device token expiry)."""
    if app_name not in _APP_META:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown app_name")
    if ctx.tenant_id is None:
        return UpdateCheckOut(
            app_name=app_name, version=None, version_code=None,
            changelog=None, size_mb=None, download_url=None, available=False,
        )

    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None or not tenant.download_token:
        return UpdateCheckOut(
            app_name=app_name, version=None, version_code=None,
            changelog=None, size_mb=None, download_url=None, available=False,
        )

    apps = _fetch_manifest(tenant.download_token)
    app = _find_app(apps, app_name)
    if app is None or not app.get("available"):
        return UpdateCheckOut(
            app_name=app_name, version=None, version_code=None,
            changelog=None, size_mb=None, download_url=None, available=False,
        )

    download_url = f"{settings.public_api_url.rstrip('/')}/v1/apps/{app_name}/download"
    return UpdateCheckOut(
        app_name=app_name,
        version=app.get("version"),
        version_code=app.get("version_code"),
        changelog=app.get("changelog"),
        size_mb=app.get("size_mb"),
        download_url=download_url,
        available=True,
    )


@router.get("/v1/apps/{app_name}/download")
def device_app_download(
    app_name: str,
    ctx: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    if app_name not in _APP_META:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown app_name")
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None or not tenant.download_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No download configured for this tenant")

    # Stream APK bytes from the platform service so devices only ever talk to the
    # tenant API — the platform URL is never exposed to clients.
    url = f"{settings.platform_base_url.rstrip('/')}/downloads/{tenant.download_token}/{app_name}/latest"
    client = httpx.Client()
    r = client.send(client.build_request("GET", url), stream=True)
    if r.status_code != 200:
        r.close()
        client.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No active release for {app_name}")

    def _stream():
        try:
            yield from r.iter_bytes()
        finally:
            r.close()
            client.close()

    headers = {"Content-Disposition": f'attachment; filename="{app_name}-latest.apk"'}
    if cl := r.headers.get("content-length"):
        headers["Content-Length"] = cl
    return StreamingResponse(_stream(), media_type="application/vnd.android.package-archive", headers=headers)


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.get(
    "/v1/admin/apps/downloads",
    response_model=DownloadsOut,
    dependencies=[require_permission("settings:read")],
)
def admin_downloads(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DownloadsOut:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context required")
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None or not tenant.download_token:
        return DownloadsOut(download_page_url="", apps=[])

    page_url = f"{_platform_download_base()}/downloads/{tenant.download_token}"
    raw_apps = _fetch_manifest(tenant.download_token)

    apps: list[AppInfo] = []
    for raw in raw_apps:
        app_name = raw.get("app_name", "")
        if app_name not in _APP_META:
            continue
        display_name, description = _APP_META[app_name]
        apps.append(AppInfo(
            app_name=app_name,
            display_name=raw.get("display_name") or display_name,
            description=raw.get("description") or description,
            version=raw.get("version"),
            version_code=raw.get("version_code"),
            changelog=raw.get("changelog"),
            size_mb=raw.get("size_mb"),
            available=raw.get("available", False),
            admin_download_url=f"/v1/admin/apps/{app_name}/download" if raw.get("available") else None,
        ))

    return DownloadsOut(download_page_url=page_url, apps=apps)


@router.get(
    "/v1/admin/apps/{app_name}/download",
    dependencies=[require_permission("settings:read")],
)
def admin_app_download(
    app_name: str,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RedirectResponse:
    if app_name not in _APP_META:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown app_name")
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context required")
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None or not tenant.download_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No download configured for this tenant")
    target = _apk_redirect_url(tenant.download_token, app_name)
    return RedirectResponse(url=target, status_code=302)
