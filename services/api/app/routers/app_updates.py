"""App distribution endpoints — OTA update check and APK download proxy."""
from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
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
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Failed to fetch platform manifest: %s", exc)
        return []


def _find_app(apps: list[dict], app_name: str) -> dict | None:
    return next((a for a in apps if a.get("app_name") == app_name), None)
