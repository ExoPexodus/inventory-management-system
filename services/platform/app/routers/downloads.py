"""Public download endpoints — no authentication required.

Serves a branded download page per tenant and streams APK files.
Tenants share their unique /downloads/:token URL with team members.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tables import AppRelease, PlatformTenant
from app.services.rate_limiter import download_page_limiter, file_download_limiter, get_client_ip
from app.services.storage_service import get_file_path

router = APIRouter(tags=["Public Downloads"])


class AppManifestItem(BaseModel):
    app_name: str
    display_name: str
    description: str
    version: str | None
    version_code: int | None
    changelog: str | None
    size_mb: float | None
    available: bool


class DownloadManifest(BaseModel):
    tenant_name: str
    apps: list[AppManifestItem]

_jinja_env: Environment | None = None


def _get_jinja() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        import os
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
        _jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html"]),
        )
    return _jinja_env


def _resolve_tenant(db: Session, token: str) -> PlatformTenant:
    tenant = db.execute(
        select(PlatformTenant).where(PlatformTenant.download_token == token)
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid download link")
    return tenant


def _latest_releases(db: Session) -> dict[str, AppRelease | None]:
    """Get the latest active release for each app."""
    result: dict[str, AppRelease | None] = {"cashier": None, "admin_mobile": None}
    for app_name in result:
        row = db.execute(
            select(AppRelease)
            .where(AppRelease.app_name == app_name, AppRelease.is_active.is_(True))
            .order_by(AppRelease.version_code.desc())
            .limit(1)
        ).scalar_one_or_none()
        result[app_name] = row
    return result


@router.get("/downloads/{token}/manifest", response_model=DownloadManifest)
def download_manifest(
    token: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> DownloadManifest:
    """JSON manifest used by the platform-web download page (no auth required)."""
    download_page_limiter.check(get_client_ip(request))
    tenant = _resolve_tenant(db, token)
    releases = _latest_releases(db)

    apps = []
    meta = {
        "cashier": ("Cashier POS", "Offline-first point-of-sale app for your staff."),
        "admin_mobile": ("Admin Mobile", "Mobile companion for store owners and managers."),
    }
    for app_name, release in releases.items():
        display_name, description = meta[app_name]
        apps.append(AppManifestItem(
            app_name=app_name,
            display_name=display_name,
            description=description,
            version=release.version if release else None,
            version_code=release.version_code if release else None,
            changelog=release.changelog if release else None,
            size_mb=round(release.file_size_bytes / (1024 * 1024), 1) if release and release.file_size_bytes else None,
            available=release is not None,
        ))

    return DownloadManifest(tenant_name=tenant.name, apps=apps)


@router.get("/downloads/{token}", response_class=HTMLResponse)
def download_page(
    token: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    download_page_limiter.check(get_client_ip(request))
    tenant = _resolve_tenant(db, token)
    releases = _latest_releases(db)

    apps = []
    for app_name, release in releases.items():
        display_name = "Cashier POS" if app_name == "cashier" else "Admin Mobile"
        icon = "point_of_sale" if app_name == "cashier" else "admin_panel_settings"
        description = (
            "Offline-first point-of-sale app for your staff."
            if app_name == "cashier"
            else "Mobile companion for store owners."
        )
        apps.append({
            "app_name": app_name,
            "display_name": display_name,
            "icon": icon,
            "description": description,
            "version": release.version if release else None,
            "changelog": release.changelog if release else None,
            "size_mb": round(release.file_size_bytes / (1024 * 1024), 1) if release and release.file_size_bytes else None,
            "download_url": f"/downloads/{token}/{app_name}/latest" if release else None,
        })

    env = _get_jinja()
    tmpl = env.get_template("downloads.html")
    html = tmpl.render(tenant_name=tenant.name, apps=apps, token=token)
    return HTMLResponse(content=html)


@router.get("/downloads/{token}/{app_name}/latest")
def download_latest(
    token: str,
    app_name: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    file_download_limiter.check(get_client_ip(request))
    _resolve_tenant(db, token)

    release = db.execute(
        select(AppRelease)
        .where(AppRelease.app_name == app_name, AppRelease.is_active.is_(True))
        .order_by(AppRelease.version_code.desc())
        .limit(1)
    ).scalar_one_or_none()

    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No release found for {app_name}")

    file_path = get_file_path(release.file_path)
    if file_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release file not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=f"{app_name}-{release.version}.apk",
        media_type="application/vnd.android.package-archive",
    )
