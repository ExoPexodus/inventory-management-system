# App Distribution & OTA Update — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let tenant admins share app download links with staff and let Cashier/Admin Mobile Flutter apps detect and self-install new APK versions at launch.

**Architecture:** The platform service already stores APKs and serves a public manifest. The tenant API gains a proxy router (device JWT for Flutter, operator JWT for admin web). The admin web gains a "Get Apps" page with a QR code and download links. Both Flutter apps gain an `UpdateService` that checks for a newer `version_code` on launch and drives an in-app download + Android install intent.

**Tech Stack:** FastAPI + httpx (tenant API), Next.js 15 server components + `qrcode` npm (admin web), Flutter + `package_info_plus` + `open_file` + `http` (both Flutter apps).

---

## File Map

| File | Action |
|------|--------|
| `services/platform/app/routers/downloads.py` | Modify — add `version_code` to `AppManifestItem` |
| `services/api/app/config.py` | Modify — add `platform_download_base_url` |
| `services/api/app/routers/app_updates.py` | Create — 4 endpoints |
| `services/api/app/main.py` | Modify — register new router |
| `docker-compose.yml` | Modify — add `PLATFORM_DOWNLOAD_BASE_URL` env var |
| `services/api/tests/routers/test_app_updates.py` | Create — unit tests |
| `apps/admin-web/package.json` | Modify — add `qrcode` dep |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Modify — add "Get Apps" nav item |
| `apps/admin-web/src/app/(main)/apps/page.tsx` | Create — server component |
| `apps/admin-web/src/app/(main)/apps/apps-client.tsx` | Create — client island (QR + copy) |
| `apps/cashier/pubspec.yaml` | Modify — add `package_info_plus`, `open_file` |
| `apps/cashier/android/app/src/main/AndroidManifest.xml` | Modify — add install permission |
| `apps/cashier/lib/services/update_service.dart` | Create — OTA service + dialog |
| `apps/cashier/lib/main.dart` | Modify — wire update check |
| `apps/admin_mobile/pubspec.yaml` | Modify — add `package_info_plus`, `open_file`, `path_provider` |
| `apps/admin_mobile/android/app/src/main/AndroidManifest.xml` | Modify — add install permission |
| `apps/admin_mobile/lib/services/update_service.dart` | Create — same OTA service |
| `apps/admin_mobile/lib/main.dart` | Modify — wire update check |

---

## Task 1: Platform Service — Expose `version_code` in Manifest

The Flutter app compares integer `version_code` values to detect updates. The manifest currently only exposes the human-readable `version` string. This task adds `version_code` so Flutter can compare directly.

**Files:**
- Modify: `services/platform/app/routers/downloads.py`

- [ ] **Step 1.1: Add `version_code` field to `AppManifestItem`**

In `services/platform/app/routers/downloads.py`, update the `AppManifestItem` model (around line 26):

```python
class AppManifestItem(BaseModel):
    app_name: str
    display_name: str
    description: str
    version: str | None
    version_code: int | None          # ← add this line
    changelog: str | None
    size_mb: float | None
    available: bool
```

- [ ] **Step 1.2: Populate `version_code` in `download_manifest()`**

In the same file, update the `download_manifest()` function body where it builds `apps`:

```python
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
            version_code=release.version_code if release else None,   # ← add this line
            changelog=release.changelog if release else None,
            size_mb=round(release.file_size_bytes / (1024 * 1024), 1) if release and release.file_size_bytes else None,
            available=release is not None,
        ))
```

- [ ] **Step 1.3: Commit**

```bash
git add services/platform/app/routers/downloads.py
git commit -m "feat(platform): expose version_code in download manifest"
```

---

## Task 2: Tenant API — Config + Router Skeleton + Registration

Sets up the new router file, registers it, and adds the config field. All endpoints are stubs at this point — they get filled in Task 3.

**Files:**
- Modify: `services/api/app/config.py`
- Create: `services/api/app/routers/app_updates.py`
- Modify: `services/api/app/main.py`
- Modify: `docker-compose.yml`

- [ ] **Step 2.1: Add config field to `services/api/app/config.py`**

After the existing `platform_base_url` field, add:

```python
    platform_download_base_url: str = ""
    # Public-facing URL of the platform service used to build shareable download page
    # links. Falls back to platform_base_url when empty.
```

- [ ] **Step 2.2: Create router skeleton at `services/api/app/routers/app_updates.py`**

```python
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
```

- [ ] **Step 2.3: Register router in `services/api/app/main.py`**

Add the import alongside the existing router imports:

```python
from app.routers import (
    ...
    app_updates,
    ...
)
```

And after the last `app.include_router(...)` line at the bottom of the file:

```python
app.include_router(app_updates.router)
```

- [ ] **Step 2.4: Add `PLATFORM_DOWNLOAD_BASE_URL` to docker-compose**

In `docker-compose.yml`, inside the `api:` service `environment:` block, add after `PLATFORM_WEB_URL`:

```yaml
      PLATFORM_DOWNLOAD_BASE_URL: ${PLATFORM_DOWNLOAD_BASE_URL:-http://localhost:8002}
```

- [ ] **Step 2.5: Commit skeleton**

```bash
git add services/api/app/config.py services/api/app/routers/app_updates.py services/api/app/main.py docker-compose.yml
git commit -m "feat(api): add app_updates router skeleton and config"
```

---

## Task 3: Tenant API — Implement All Four Endpoints + Tests

**Files:**
- Modify: `services/api/app/routers/app_updates.py` (add endpoint bodies)
- Create: `services/api/tests/routers/test_app_updates.py`

- [ ] **Step 3.1: Write the failing tests first**

Create `services/api/tests/routers/test_app_updates.py`:

```python
"""Tests for the app_updates router — OTA update check and download proxy."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminContext
from app.auth.deps import DeviceAuth
from app.models import Tenant
from app.routers.app_updates import (
    DownloadsOut,
    UpdateCheckOut,
    admin_app_download,
    admin_downloads,
    device_app_download,
    update_check,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _device_ctx(tenant_id) -> DeviceAuth:
    return DeviceAuth(
        device_id=uuid.uuid4(),
        tenant_id=tenant_id,
        shop_ids=[],
    )


def _admin_ctx(tenant_id) -> AdminContext:
    return AdminContext(
        user_id=None,
        tenant_id=tenant_id,
        role="admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )


_SAMPLE_MANIFEST = [
    {
        "app_name": "cashier",
        "display_name": "Cashier POS",
        "description": "POS app",
        "version": "1.2.0",
        "version_code": 12,
        "changelog": "Bug fixes",
        "size_mb": 45.3,
        "available": True,
    },
    {
        "app_name": "admin_mobile",
        "display_name": "Admin Mobile",
        "description": "Admin app",
        "version": "1.0.5",
        "version_code": 5,
        "changelog": "Improvements",
        "size_mb": 38.1,
        "available": True,
    },
]


# ── update_check tests ────────────────────────────────────────────────────────

def test_update_check_unknown_app_name_raises_400(db: Session, tenant: Tenant) -> None:
    with pytest.raises(HTTPException) as exc:
        update_check(ctx=_device_ctx(tenant.id), db=db, app_name="unknown_app")
    assert exc.value.status_code == 400


def test_update_check_no_download_token_returns_unavailable(db: Session, tenant: Tenant) -> None:
    tenant.download_token = None
    db.commit()

    result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="cashier")

    assert result.available is False
    assert result.version is None
    assert result.download_url is None


def test_update_check_platform_error_returns_unavailable(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "test-token-abc"
    db.commit()

    with patch("app.routers.app_updates._fetch_manifest", return_value=[]):
        result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="cashier")

    assert result.available is False


def test_update_check_returns_full_info(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "test-token-abc"
    db.commit()

    with patch("app.routers.app_updates._fetch_manifest", return_value=_SAMPLE_MANIFEST):
        result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="cashier")

    assert result.available is True
    assert result.version == "1.2.0"
    assert result.version_code == 12
    assert result.changelog == "Bug fixes"
    assert result.size_mb == 45.3
    assert result.download_url is not None
    assert "/v1/apps/cashier/download" in result.download_url


def test_update_check_admin_mobile(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "test-token-abc"
    db.commit()

    with patch("app.routers.app_updates._fetch_manifest", return_value=_SAMPLE_MANIFEST):
        result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="admin_mobile")

    assert result.available is True
    assert result.version_code == 5
    assert "/v1/apps/admin_mobile/download" in result.download_url


# ── admin_downloads tests ─────────────────────────────────────────────────────

def test_admin_downloads_no_token_still_returns_structure(db: Session, tenant: Tenant) -> None:
    tenant.download_token = None
    db.commit()

    result = admin_downloads(ctx=_admin_ctx(tenant.id), db=db)

    assert isinstance(result, DownloadsOut)
    assert result.download_page_url == ""
    assert result.apps == []


def test_admin_downloads_returns_page_url_and_both_apps(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "tok123"
    db.commit()

    with patch("app.routers.app_updates._fetch_manifest", return_value=_SAMPLE_MANIFEST):
        result = admin_downloads(ctx=_admin_ctx(tenant.id), db=db)

    assert "tok123" in result.download_page_url
    assert len(result.apps) == 2
    cashier = next(a for a in result.apps if a.app_name == "cashier")
    assert cashier.version == "1.2.0"
    assert cashier.admin_download_url == "/v1/admin/apps/cashier/download"
```

- [ ] **Step 3.2: Run the tests — confirm they all fail**

```bash
cd services/api
python -m pytest tests/routers/test_app_updates.py -v 2>&1 | head -40
```

Expected: `ImportError` or `AttributeError` because the endpoint functions don't exist yet.

- [ ] **Step 3.3: Implement the four endpoints in `app_updates.py`**

Append the following endpoint functions to `services/api/app/routers/app_updates.py` (after the helpers added in Task 2):

```python
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


@router.get("/v1/apps/{app_name}/download")
def device_app_download(
    app_name: str,
    ctx: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    if app_name not in _APP_META:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown app_name")

    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None or not tenant.download_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No download configured for this tenant")

    target = f"{settings.platform_base_url.rstrip('/')}/downloads/{tenant.download_token}/{app_name}/latest"
    return RedirectResponse(url=target, status_code=302)


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

    target = f"{settings.platform_base_url.rstrip('/')}/downloads/{tenant.download_token}/{app_name}/latest"
    return RedirectResponse(url=target, status_code=302)
```

- [ ] **Step 3.4: Run the tests — confirm they all pass**

```bash
cd services/api
python -m pytest tests/routers/test_app_updates.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add services/api/app/routers/app_updates.py services/api/tests/routers/test_app_updates.py
git commit -m "feat(api): implement app update-check and download endpoints"
```

---

## Task 4: Admin Web — "Get Apps" Page

Adds the nav item and a new page that shows the shareable download link (with QR code) and per-app cards with version info and download buttons.

**Files:**
- Modify: `apps/admin-web/package.json`
- Modify: `apps/admin-web/src/components/dashboard/AppShell.tsx`
- Create: `apps/admin-web/src/app/(main)/apps/apps-client.tsx`
- Create: `apps/admin-web/src/app/(main)/apps/page.tsx`

- [ ] **Step 4.1: Install `qrcode` package**

```bash
cd apps/admin-web
npm install qrcode
npm install --save-dev @types/qrcode
```

Verify the install succeeded:

```bash
ls node_modules/qrcode/lib/index.js
```

Expected: file exists (no error).

- [ ] **Step 4.2: Add "Get Apps" nav item to `AppShell.tsx`**

In `apps/admin-web/src/components/dashboard/AppShell.tsx`, find the `NAV` array (around line 84) and add the new entry **before** the Settings item:

```ts
  { href: "/billing",         label: "Billing",         icon: "payments",          permission: "settings:read" },
  { href: "/apps",            label: "Get Apps",         icon: "install_mobile",    permission: "settings:read" },
  { href: "/settings",        label: "Settings",         icon: "settings",          permission: "settings:read" },
```

- [ ] **Step 4.3: Create the client island at `apps/admin-web/src/app/(main)/apps/apps-client.tsx`**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";

export function ShareCard({ url }: { url: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!canvasRef.current || !url) return;
    void QRCode.toCanvas(canvasRef.current, url, { width: 160, margin: 1 });
  }, [url]);

  const handleCopy = () => {
    void navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!url) {
    return (
      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <p className="text-sm text-on-surface-variant">
          No download link configured for this tenant. Contact your platform administrator.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm sm:flex-row sm:items-start">
      <canvas ref={canvasRef} className="shrink-0 rounded-lg border border-outline-variant/10" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Share with your team</p>
          <p className="mt-1 text-sm text-on-surface-variant">
            Scan the QR code or share this link. Opening it on an Android device lets staff download and install the apps.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={url}
            className="min-w-0 flex-1 rounded-lg border border-outline-variant/20 bg-surface-container-low px-3 py-2 font-mono text-xs text-on-surface outline-none"
          />
          <button
            type="button"
            onClick={handleCopy}
            className="shrink-0 rounded-lg border border-outline-variant/20 px-4 py-2 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
          >
            {copied ? "Copied!" : "Copy link"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function DownloadButton({ appName, adminDownloadUrl }: { appName: string; adminDownloadUrl: string | null }) {
  if (!adminDownloadUrl) return null;
  return (
    <a
      href={`/api/ims${adminDownloadUrl}`}
      className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 px-4 py-2 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high"
      download
    >
      <span className="material-symbols-outlined text-lg leading-none" aria-hidden="true">download</span>
      Download APK
    </a>
  );
}
```

- [ ] **Step 4.4: Create the server component at `apps/admin-web/src/app/(main)/apps/page.tsx`**

```tsx
import { serverJsonGet } from "@/lib/api/server-json";
import { ShareCard, DownloadButton } from "./apps-client";

type AppInfo = {
  app_name: string;
  display_name: string;
  description: string;
  version: string | null;
  version_code: number | null;
  changelog: string | null;
  size_mb: number | null;
  available: boolean;
  admin_download_url: string | null;
};

type DownloadsResponse = {
  download_page_url: string;
  apps: AppInfo[];
};

const APP_ICONS: Record<string, string> = {
  cashier: "point_of_sale",
  admin_mobile: "admin_panel_settings",
};

export default async function GetAppsPage() {
  const res = await serverJsonGet<DownloadsResponse>("/v1/admin/apps/downloads");

  const downloadPageUrl = res.ok ? res.data.download_page_url : "";
  const apps: AppInfo[] = res.ok ? res.data.apps : [];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">App distribution</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Get Apps</h2>
        <p className="mt-2 text-on-surface-variant">
          Download and distribute the Cashier POS and Admin Mobile apps to your team.
        </p>
      </div>

      <ShareCard url={downloadPageUrl} />

      {apps.length === 0 && res.ok && (
        <p className="text-sm text-on-surface-variant">No releases published yet. Ask your platform administrator to upload APK builds.</p>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {apps.map((app) => (
          <div
            key={app.app_name}
            className="flex flex-col gap-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm"
          >
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                <span className="material-symbols-outlined text-2xl text-primary" aria-hidden="true">
                  {APP_ICONS[app.app_name] ?? "smartphone"}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-headline text-lg font-bold text-on-surface">{app.display_name}</h3>
                  {app.version && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-bold text-primary">
                      v{app.version}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-sm text-on-surface-variant">{app.description}</p>
                {app.size_mb && (
                  <p className="mt-1 text-xs text-on-surface-variant/60">{app.size_mb.toFixed(1)} MB</p>
                )}
              </div>
            </div>

            {app.changelog && (
              <div className="rounded-lg bg-surface-container-low px-4 py-3">
                <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">What&apos;s new</p>
                <p className="mt-1 line-clamp-3 text-sm text-on-surface-variant">{app.changelog}</p>
              </div>
            )}

            {!app.available && (
              <p className="text-sm text-on-surface-variant/60">Not yet available — no active release.</p>
            )}

            <DownloadButton appName={app.app_name} adminDownloadUrl={app.admin_download_url} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4.5: Verify the page builds without TypeScript errors**

```bash
cd apps/admin-web
npm run build 2>&1 | tail -20
```

Expected: Build succeeds. If there are TypeScript errors, fix them before proceeding.

- [ ] **Step 4.6: Commit**

```bash
git add apps/admin-web/package.json apps/admin-web/package-lock.json \
  apps/admin-web/src/components/dashboard/AppShell.tsx \
  apps/admin-web/src/app/(main)/apps/
git commit -m "feat(admin-web): add Get Apps page with QR code and download links"
```

---

## Task 5: Cashier — OTA Update Service + Wiring

Adds the two new packages, the `UpdateService` (with its update dialog), and wires the update check into `main.dart`.

**Files:**
- Modify: `apps/cashier/pubspec.yaml`
- Modify: `apps/cashier/android/app/src/main/AndroidManifest.xml`
- Create: `apps/cashier/lib/services/update_service.dart`
- Modify: `apps/cashier/lib/main.dart`

- [ ] **Step 5.1: Add packages to `apps/cashier/pubspec.yaml`**

In the `dependencies:` block, add after `mobile_scanner`:

```yaml
  package_info_plus: ^8.0.0
  open_file: ^3.5.0
```

Then run:

```bash
cd apps/cashier
../../tools/flutter/bin/flutter pub get
```

Expected: `Got dependencies!` with no errors. If Gradle issues appear, diff `pubspec.lock` against the known-good baseline (see CLAUDE.md).

- [ ] **Step 5.2: Add `REQUEST_INSTALL_PACKAGES` permission to cashier AndroidManifest**

In `apps/cashier/android/app/src/main/AndroidManifest.xml`, add after the existing `<uses-permission android:name="android.permission.INTERNET" />` line:

```xml
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
```

- [ ] **Step 5.3: Create `apps/cashier/lib/services/update_service.dart`**

```dart
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:open_file/open_file.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';

class UpdateInfo {
  const UpdateInfo({
    required this.version,
    required this.versionCode,
    required this.downloadUrl,
    this.changelog,
    this.sizeMb,
  });

  final String version;
  final int versionCode;
  final String downloadUrl;
  final String? changelog;
  final double? sizeMb;
}

class UpdateService {
  UpdateService._();

  /// Calls the update-check endpoint and returns [UpdateInfo] if a newer
  /// version is available, or null if up to date / on any network error.
  static Future<UpdateInfo?> checkForUpdate({
    required String baseUrl,
    required String accessToken,
    required String appName,
  }) async {
    try {
      final uri = Uri.parse('${baseUrl.trimRight('/')}/v1/apps/update-check')
          .replace(queryParameters: {'app_name': appName});
      final resp = await http
          .get(uri, headers: {'Authorization': 'Bearer $accessToken'})
          .timeout(const Duration(seconds: 10));

      if (resp.statusCode != 200) return null;

      final json = _parseJson(resp.body);
      if (json == null || json['available'] != true) return null;

      final remoteCode = (json['version_code'] as num?)?.toInt();
      if (remoteCode == null) return null;

      final info = await PackageInfo.fromPlatform();
      final installedCode = int.tryParse(info.buildNumber) ?? 0;
      if (remoteCode <= installedCode) return null;

      return UpdateInfo(
        version: json['version'] as String? ?? '',
        versionCode: remoteCode,
        downloadUrl: json['download_url'] as String? ?? '',
        changelog: json['changelog'] as String?,
        sizeMb: (json['size_mb'] as num?)?.toDouble(),
      );
    } catch (_) {
      // Update check must never crash the app.
      return null;
    }
  }

  /// Downloads the APK from [downloadUrl] (with Bearer [accessToken]) to a
  /// temp file, calling [onProgress] (0.0–1.0) as data arrives.
  /// Returns the local file path on success.
  static Future<String> downloadApk({
    required String downloadUrl,
    required String accessToken,
    required void Function(double) onProgress,
  }) async {
    final request = http.Request('GET', Uri.parse(downloadUrl));
    request.headers['Authorization'] = 'Bearer $accessToken';

    final client = http.Client();
    try {
      final streamed = await client.send(request);
      final total = streamed.contentLength ?? 0;
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/ims_update.apk');
      final sink = file.openWrite();

      int received = 0;
      await for (final chunk in streamed.stream) {
        sink.add(chunk);
        received += chunk.length;
        if (total > 0) onProgress(received / total);
      }
      await sink.close();
      return file.path;
    } finally {
      client.close();
    }
  }

  /// Opens the APK at [filePath] with the Android install intent.
  static Future<void> installApk(String filePath) async {
    await OpenFile.open(filePath, type: 'application/vnd.android.package-archive');
  }

  static Map<String, dynamic>? _parseJson(String body) {
    try {
      // ignore: avoid_dynamic_calls
      final dynamic raw = (body.isNotEmpty)
          ? (throw UnimplementedError()) // will be replaced below
          : null;
      _ = raw;
    } catch (_) {}
    // Use dart:convert directly to avoid extra dependency.
    try {
      import 'dart:convert'; // this won't compile here — see corrected version below
    } catch (_) {
      return null;
    }
    return null;
  }
}
```

Wait — the `_parseJson` helper above has an error (can't use `import` mid-function). Use `dart:convert` at the top of the file instead. Here is the correct, complete file:

```dart
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:open_file/open_file.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';

class UpdateInfo {
  const UpdateInfo({
    required this.version,
    required this.versionCode,
    required this.downloadUrl,
    this.changelog,
    this.sizeMb,
  });

  final String version;
  final int versionCode;
  final String downloadUrl;
  final String? changelog;
  final double? sizeMb;
}

class UpdateService {
  UpdateService._();

  /// Returns [UpdateInfo] if a newer version is available, null otherwise.
  /// Never throws — any error returns null so startup is never blocked.
  static Future<UpdateInfo?> checkForUpdate({
    required String baseUrl,
    required String accessToken,
    required String appName,
  }) async {
    try {
      final uri = Uri.parse('${baseUrl.trimRight('/')}/v1/apps/update-check')
          .replace(queryParameters: {'app_name': appName});
      final resp = await http
          .get(uri, headers: {'Authorization': 'Bearer $accessToken'})
          .timeout(const Duration(seconds: 10));

      if (resp.statusCode != 200) return null;
      final json = jsonDecode(resp.body) as Map<String, dynamic>;
      if (json['available'] != true) return null;

      final remoteCode = (json['version_code'] as num?)?.toInt();
      if (remoteCode == null) return null;

      final info = await PackageInfo.fromPlatform();
      final installedCode = int.tryParse(info.buildNumber) ?? 0;
      if (remoteCode <= installedCode) return null;

      return UpdateInfo(
        version: json['version'] as String? ?? '',
        versionCode: remoteCode,
        downloadUrl: json['download_url'] as String? ?? '',
        changelog: json['changelog'] as String?,
        sizeMb: (json['size_mb'] as num?)?.toDouble(),
      );
    } catch (_) {
      return null;
    }
  }

  /// Streams the APK from [downloadUrl] to a temp file. Calls [onProgress]
  /// with a 0.0–1.0 fraction as data arrives. Returns the local file path.
  static Future<String> downloadApk({
    required String downloadUrl,
    required String accessToken,
    required void Function(double) onProgress,
  }) async {
    final request = http.Request('GET', Uri.parse(downloadUrl));
    request.headers['Authorization'] = 'Bearer $accessToken';

    final client = http.Client();
    try {
      final streamed = await client.send(request);
      final total = streamed.contentLength ?? 0;
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/ims_update.apk');
      final sink = file.openWrite();
      int received = 0;
      await for (final chunk in streamed.stream) {
        sink.add(chunk);
        received += chunk.length;
        if (total > 0) onProgress(received / total);
      }
      await sink.close();
      return file.path;
    } finally {
      client.close();
    }
  }

  /// Opens the downloaded APK with the Android install intent.
  static Future<void> installApk(String filePath) async {
    await OpenFile.open(filePath, type: 'application/vnd.android.package-archive');
  }
}


// ── Update dialog ─────────────────────────────────────────────────────────────

/// Shows a modal update dialog. Call after confirming a newer version exists.
Future<void> showUpdateDialog(
  BuildContext context,
  UpdateInfo info,
  String accessToken,
) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _UpdateDialog(info: info, accessToken: accessToken),
  );
}

enum _Phase { prompt, downloading, done, error }

class _UpdateDialog extends StatefulWidget {
  const _UpdateDialog({required this.info, required this.accessToken});
  final UpdateInfo info;
  final String accessToken;

  @override
  State<_UpdateDialog> createState() => _UpdateDialogState();
}

class _UpdateDialogState extends State<_UpdateDialog> {
  _Phase _phase = _Phase.prompt;
  double _progress = 0;
  String? _errorMessage;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _phase == _Phase.prompt || _phase == _Phase.error,
      child: AlertDialog(
        title: Text('Update available  v${widget.info.version}'),
        content: _buildContent(),
        actions: _buildActions(),
      ),
    );
  }

  Widget _buildContent() {
    switch (_phase) {
      case _Phase.prompt:
        final sizePart = widget.info.sizeMb != null
            ? '${widget.info.sizeMb!.toStringAsFixed(1)} MB'
            : '';
        final changelog = widget.info.changelog ?? '';
        final detail = [sizePart, changelog].where((s) => s.isNotEmpty).join(' · ');
        return Text(detail.isEmpty ? 'A new version is ready to install.' : detail,
            style: const TextStyle(fontSize: 13));

      case _Phase.downloading:
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            LinearProgressIndicator(value: _progress > 0 ? _progress : null),
            const SizedBox(height: 8),
            Text('${(_progress * 100).toStringAsFixed(0)}%  Downloading…'),
          ],
        );

      case _Phase.done:
        return const Text('Installing…');

      case _Phase.error:
        return Text(_errorMessage ?? 'Download failed. Please try again later.');
    }
  }

  List<Widget>? _buildActions() {
    switch (_phase) {
      case _Phase.prompt:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Later'),
          ),
          ElevatedButton(
            onPressed: _startDownload,
            child: const Text('Update Now'),
          ),
        ];
      case _Phase.downloading:
      case _Phase.done:
        return null;
      case _Phase.error:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Dismiss'),
          ),
        ];
    }
  }

  Future<void> _startDownload() async {
    setState(() => _phase = _Phase.downloading);
    try {
      final path = await UpdateService.downloadApk(
        downloadUrl: widget.info.downloadUrl,
        accessToken: widget.accessToken,
        onProgress: (p) {
          if (mounted) setState(() => _progress = p);
        },
      );
      if (!mounted) return;
      setState(() => _phase = _Phase.done);
      await UpdateService.installApk(path);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _phase = _Phase.error;
        _errorMessage = 'Download failed. Please try again later.';
      });
    }
  }
}
```

- [ ] **Step 5.4: Verify the Flutter app analyzes cleanly**

```bash
cd apps/cashier
../../tools/flutter/bin/flutter analyze lib/services/update_service.dart
```

Expected: `No issues found!`

- [ ] **Step 5.5: Wire update check into `apps/cashier/lib/main.dart`**

The update check fires after a valid device session loads. In `_CashierBootstrapState`, add the following method and call it from `_check()`.

Replace the existing `_check()` method with:

```dart
  Future<void> _check() async {
    var s = await SessionStore.load();
    if (s != null && s.hasEmployeeSession) {
      final timedOut = await SessionStore.isEmployeeSessionTimedOut();
      if (timedOut) {
        await SessionStore.clearEmployeeSession();
        s = await SessionStore.load();
      }
    }
    setState(() {
      _session = s;
      _loading = false;
    });
    // Fire update check after UI settles — never blocks startup.
    if (s != null) {
      unawaited(_checkForUpdate(s));
    }
  }

  Future<void> _checkForUpdate(SessionData session) async {
    await Future<void>.delayed(const Duration(seconds: 2));
    final update = await UpdateService.checkForUpdate(
      baseUrl: session.baseUrl,
      accessToken: session.accessToken,
      appName: 'cashier',
    );
    if (update == null || !mounted) return;
    await showUpdateDialog(context, update, session.accessToken);
  }
```

Also add the imports at the top of `main.dart` (after existing imports):

```dart
import 'services/update_service.dart';
```

- [ ] **Step 5.6: Analyze the full cashier app**

```bash
cd apps/cashier
../../tools/flutter/bin/flutter analyze
```

Expected: `No issues found!`

- [ ] **Step 5.7: Commit**

```bash
git add apps/cashier/pubspec.yaml apps/cashier/pubspec.lock \
  apps/cashier/android/app/src/main/AndroidManifest.xml \
  apps/cashier/lib/services/update_service.dart \
  apps/cashier/lib/main.dart
git commit -m "feat(cashier): add OTA update check and in-app install dialog"
```

---

## Task 6: Admin Mobile — OTA Update Service + Wiring

The admin mobile follows the same pattern as the cashier, but uses `getDeviceToken()` (the device JWT from enrollment) for the update check rather than the operator login token.

**Files:**
- Modify: `apps/admin_mobile/pubspec.yaml`
- Modify: `apps/admin_mobile/android/app/src/main/AndroidManifest.xml`
- Create: `apps/admin_mobile/lib/services/update_service.dart`
- Modify: `apps/admin_mobile/lib/main.dart`

- [ ] **Step 6.1: Add packages to `apps/admin_mobile/pubspec.yaml`**

In the `dependencies:` block, add after `mobile_scanner`:

```yaml
  package_info_plus: ^8.0.0
  open_file: ^3.5.0
  path_provider: ^2.1.5
```

The `path_provider_android` override is already present in this app's `pubspec.yaml` — leave it as is.

Then run:

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter pub get
```

Expected: `Got dependencies!`

- [ ] **Step 6.2: Add `REQUEST_INSTALL_PACKAGES` permission to admin_mobile AndroidManifest**

In `apps/admin_mobile/android/app/src/main/AndroidManifest.xml`, add after the existing `<uses-permission android:name="android.permission.INTERNET" />`:

```xml
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
```

- [ ] **Step 6.3: Create `apps/admin_mobile/lib/services/update_service.dart`**

This file is identical to the cashier version except for the class comment. Copy it exactly:

```dart
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:open_file/open_file.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';

class UpdateInfo {
  const UpdateInfo({
    required this.version,
    required this.versionCode,
    required this.downloadUrl,
    this.changelog,
    this.sizeMb,
  });

  final String version;
  final int versionCode;
  final String downloadUrl;
  final String? changelog;
  final double? sizeMb;
}

class UpdateService {
  UpdateService._();

  static Future<UpdateInfo?> checkForUpdate({
    required String baseUrl,
    required String accessToken,
    required String appName,
  }) async {
    try {
      final uri = Uri.parse('${baseUrl.trimRight('/')}/v1/apps/update-check')
          .replace(queryParameters: {'app_name': appName});
      final resp = await http
          .get(uri, headers: {'Authorization': 'Bearer $accessToken'})
          .timeout(const Duration(seconds: 10));

      if (resp.statusCode != 200) return null;
      final json = jsonDecode(resp.body) as Map<String, dynamic>;
      if (json['available'] != true) return null;

      final remoteCode = (json['version_code'] as num?)?.toInt();
      if (remoteCode == null) return null;

      final info = await PackageInfo.fromPlatform();
      final installedCode = int.tryParse(info.buildNumber) ?? 0;
      if (remoteCode <= installedCode) return null;

      return UpdateInfo(
        version: json['version'] as String? ?? '',
        versionCode: remoteCode,
        downloadUrl: json['download_url'] as String? ?? '',
        changelog: json['changelog'] as String?,
        sizeMb: (json['size_mb'] as num?)?.toDouble(),
      );
    } catch (_) {
      return null;
    }
  }

  static Future<String> downloadApk({
    required String downloadUrl,
    required String accessToken,
    required void Function(double) onProgress,
  }) async {
    final request = http.Request('GET', Uri.parse(downloadUrl));
    request.headers['Authorization'] = 'Bearer $accessToken';

    final client = http.Client();
    try {
      final streamed = await client.send(request);
      final total = streamed.contentLength ?? 0;
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/ims_update.apk');
      final sink = file.openWrite();
      int received = 0;
      await for (final chunk in streamed.stream) {
        sink.add(chunk);
        received += chunk.length;
        if (total > 0) onProgress(received / total);
      }
      await sink.close();
      return file.path;
    } finally {
      client.close();
    }
  }

  static Future<void> installApk(String filePath) async {
    await OpenFile.open(filePath, type: 'application/vnd.android.package-archive');
  }
}


// ── Update dialog ─────────────────────────────────────────────────────────────

Future<void> showUpdateDialog(
  BuildContext context,
  UpdateInfo info,
  String accessToken,
) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _UpdateDialog(info: info, accessToken: accessToken),
  );
}

enum _Phase { prompt, downloading, done, error }

class _UpdateDialog extends StatefulWidget {
  const _UpdateDialog({required this.info, required this.accessToken});
  final UpdateInfo info;
  final String accessToken;

  @override
  State<_UpdateDialog> createState() => _UpdateDialogState();
}

class _UpdateDialogState extends State<_UpdateDialog> {
  _Phase _phase = _Phase.prompt;
  double _progress = 0;
  String? _errorMessage;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _phase == _Phase.prompt || _phase == _Phase.error,
      child: AlertDialog(
        title: Text('Update available  v${widget.info.version}'),
        content: _buildContent(),
        actions: _buildActions(),
      ),
    );
  }

  Widget _buildContent() {
    switch (_phase) {
      case _Phase.prompt:
        final sizePart = widget.info.sizeMb != null
            ? '${widget.info.sizeMb!.toStringAsFixed(1)} MB'
            : '';
        final changelog = widget.info.changelog ?? '';
        final detail = [sizePart, changelog].where((s) => s.isNotEmpty).join(' · ');
        return Text(detail.isEmpty ? 'A new version is ready to install.' : detail,
            style: const TextStyle(fontSize: 13));
      case _Phase.downloading:
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            LinearProgressIndicator(value: _progress > 0 ? _progress : null),
            const SizedBox(height: 8),
            Text('${(_progress * 100).toStringAsFixed(0)}%  Downloading…'),
          ],
        );
      case _Phase.done:
        return const Text('Installing…');
      case _Phase.error:
        return Text(_errorMessage ?? 'Download failed. Please try again later.');
    }
  }

  List<Widget>? _buildActions() {
    switch (_phase) {
      case _Phase.prompt:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Later'),
          ),
          ElevatedButton(
            onPressed: _startDownload,
            child: const Text('Update Now'),
          ),
        ];
      case _Phase.downloading:
      case _Phase.done:
        return null;
      case _Phase.error:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Dismiss'),
          ),
        ];
    }
  }

  Future<void> _startDownload() async {
    setState(() => _phase = _Phase.downloading);
    try {
      final path = await UpdateService.downloadApk(
        downloadUrl: widget.info.downloadUrl,
        accessToken: widget.accessToken,
        onProgress: (p) {
          if (mounted) setState(() => _progress = p);
        },
      );
      if (!mounted) return;
      setState(() => _phase = _Phase.done);
      await UpdateService.installApk(path);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _phase = _Phase.error;
        _errorMessage = 'Download failed. Please try again later.';
      });
    }
  }
}
```

- [ ] **Step 6.4: Wire update check into `apps/admin_mobile/lib/main.dart`**

The admin mobile uses the **device token** (from enrollment) for the update check — not the operator login token. Add `_checkForUpdate` to `_StartupGateState` and call it from `_checkState()`.

Add the import at the top of `main.dart`:

```dart
import 'services/update_service.dart';
```

Modify `_checkState()` — add the update check call at the end, after `setState`:

```dart
  Future<void> _checkState() async {
    final enrolled = await SessionStore.isEnrolled();
    final baseUrl = await SessionStore.getBaseUrl();
    final session = await SessionStore.load();
    if (session != null) {
      unawaited(_currency.load(AdminApi(session.baseUrl, session.token)));
    }
    if (mounted) {
      setState(() {
        _enrolled = enrolled;
        _baseUrl = baseUrl;
        _session = session;
        _loading = false;
      });
    }
    // Fire update check after UI settles. Uses the device token (from enrollment),
    // not the operator login token, because /v1/apps/update-check requires device JWT.
    if (enrolled && baseUrl != null) {
      final deviceToken = await SessionStore.getDeviceToken();
      if (deviceToken != null) {
        unawaited(_checkForUpdate(baseUrl, deviceToken));
      }
    }
  }

  Future<void> _checkForUpdate(String baseUrl, String deviceToken) async {
    await Future<void>.delayed(const Duration(seconds: 2));
    final update = await UpdateService.checkForUpdate(
      baseUrl: baseUrl,
      accessToken: deviceToken,
      appName: 'admin_mobile',
    );
    if (update == null || !mounted) return;
    await showUpdateDialog(context, update, deviceToken);
  }
```

- [ ] **Step 6.5: Analyze the admin_mobile app**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze
```

Expected: `No issues found!`

- [ ] **Step 6.6: Commit**

```bash
git add apps/admin_mobile/pubspec.yaml apps/admin_mobile/pubspec.lock \
  apps/admin_mobile/android/app/src/main/AndroidManifest.xml \
  apps/admin_mobile/lib/services/update_service.dart \
  apps/admin_mobile/lib/main.dart
git commit -m "feat(admin-mobile): add OTA update check and in-app install dialog"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Platform manifest exposes `version_code` | Task 1 |
| `GET /v1/apps/update-check` (device JWT) | Task 3 |
| `GET /v1/apps/{app_name}/download` (device JWT, 302 redirect) | Task 3 |
| `GET /v1/admin/apps/downloads` (operator JWT, returns manifest + page URL) | Task 3 |
| `GET /v1/admin/apps/{app_name}/download` (operator JWT, 302 redirect) | Task 3 |
| `PLATFORM_DOWNLOAD_BASE_URL` config + docker-compose | Task 2 |
| Admin web nav item "Get Apps" | Task 4 |
| Admin web page: shareable link + QR code | Task 4 |
| Admin web page: app cards with version, size, changelog, download button | Task 4 |
| `qrcode` npm package | Task 4 |
| Cashier `package_info_plus` + `open_file` packages | Task 5 |
| Cashier `REQUEST_INSTALL_PACKAGES` permission | Task 5 |
| Cashier `UpdateService.checkForUpdate` | Task 5 |
| Cashier `UpdateService.downloadApk` (streaming + progress) | Task 5 |
| Cashier `UpdateService.installApk` | Task 5 |
| Cashier update dialog (prompt → downloading → done/error) | Task 5 |
| Cashier update check wired into `main.dart` (2s delay, unawaited) | Task 5 |
| Admin mobile — same OTA pattern using device token | Task 6 |
| Tests for all four API endpoints | Task 3 |

**No placeholders found.**

**Type consistency confirmed:** `UpdateInfo` defined in Task 5 Step 5.3, used in Step 5.5. `UpdateCheckOut`, `AppInfo`, `DownloadsOut` defined in Task 2 Step 2.2, used in Task 3 Step 3.1 tests and Step 3.3 implementation. `showUpdateDialog` defined in Task 5 Step 5.3, called in Step 5.5 and Task 6 Step 6.4.
