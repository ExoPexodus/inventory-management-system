# App Distribution & OTA Update Design

**Date:** 2026-05-03  
**Status:** Approved  
**Scope:** Admin web "Get Apps" page + Flutter in-app OTA update for Cashier and Admin Mobile APKs

---

## Overview

Tenant admins need a way to distribute the Cashier POS and Admin Mobile APKs to their staff, and the Flutter apps need to detect and apply updates automatically at launch. The platform service already handles APK storage, manifests, and file serving. This feature connects that infrastructure to the admin web UI and the Flutter apps.

---

## Existing Infrastructure (no changes needed)

- **`services/platform/`** — `AppRelease` table stores uploaded APKs. Public endpoints:
  - `GET /downloads/{token}/manifest` — JSON manifest of latest active releases per app
  - `GET /downloads/{token}/{app_name}/latest` — streams the APK file
  - `GET /downloads/{token}` — rendered HTML download page
- **`apps/platform-web/`** — dev/operator portal for uploading APKs and toggling `is_active`
- **`services/api/app/models/tables.py`** — `Tenant` model has `download_token: Optional[str]`
- **`services/api/app/config.py`** — has `platform_base_url` (internal URL to platform service)

---

## Component 1: Tenant API — `app_updates` router

### New config field (`services/api/app/config.py`)

```python
platform_download_base_url: str = ""
# Public-facing URL of the platform service (for shareable download page links).
# Falls back to platform_base_url if empty.
```

Add `PLATFORM_DOWNLOAD_BASE_URL` to `docker-compose.yml` environment for the `api` service.

### New router (`services/api/app/routers/app_updates.py`)

Register in `services/api/app/main.py`.

#### `GET /v1/apps/update-check`

- **Auth:** Device JWT (`typ=device`)
- **Query param:** `app_name=cashier` or `app_name=admin_mobile`
- **Logic:**
  1. Load `Tenant` for `ctx.tenant_id`, read `download_token`
  2. If `download_token` is null → return `{"available": false}`
  3. Proxy `GET {platform_base_url}/downloads/{token}/manifest` (internal HTTP call)
  4. Find the entry matching `app_name`, return:

```json
{
  "app_name": "cashier",
  "version": "1.2.0",
  "version_code": 12,
  "changelog": "Bug fixes and performance improvements.",
  "size_mb": 45.3,
  "download_url": "{public_api_url}/v1/apps/cashier/download",
  "available": true
}
```

The `download_url` points back to the tenant API (not the platform service URL directly).

#### `GET /v1/apps/{app_name}/download`

- **Auth:** Device JWT
- **Logic:** 302 redirect to `{platform_base_url}/downloads/{token}/{app_name}/latest`
- The Flutter `http` package follows redirects automatically, so the app receives the APK stream.

#### `GET /v1/admin/apps/downloads`

- **Auth:** Operator JWT, `settings:read` permission
- **Logic:**
  1. Load tenant's `download_token`
  2. Proxy manifest from platform service
  3. Compute `download_page_url = {platform_download_base_url}/downloads/{token}`
  4. Return:

```json
{
  "download_page_url": "http://your-server:8002/downloads/{token}",
  "apps": [
    {
      "app_name": "cashier",
      "display_name": "Cashier POS",
      "description": "Offline-first point-of-sale app for your staff.",
      "version": "1.2.0",
      "version_code": 12,
      "changelog": "...",
      "size_mb": 45.3,
      "available": true,
      "admin_download_url": "/v1/admin/apps/cashier/download"
    },
    {
      "app_name": "admin_mobile",
      "display_name": "Admin Mobile",
      "description": "Mobile companion for store owners and managers.",
      "version": "1.0.5",
      "version_code": 5,
      "changelog": "...",
      "size_mb": 38.1,
      "available": true,
      "admin_download_url": "/v1/admin/apps/admin_mobile/download"
    }
  ]
}
```

#### `GET /v1/admin/apps/{app_name}/download`

- **Auth:** Operator JWT, `settings:read` permission
- **Logic:** 302 redirect to `{platform_base_url}/downloads/{token}/{app_name}/latest`
- Separate from the device-JWT download endpoint because the IMS proxy always forwards an operator JWT. The admin web's "Download APK" button uses this endpoint, not `/v1/apps/{app_name}/download`.

---

## Component 2: Admin Web — "Get Apps" page

### Nav item (`apps/admin-web/src/components/dashboard/AppShell.tsx`)

Add to the `NAV` array:
```ts
{ href: "/apps", label: "Get Apps", icon: "install_mobile", permission: "settings:read" }
```

### New page (`apps/admin-web/src/app/(main)/apps/page.tsx`)

Server component (consistent with `overview/page.tsx`). Calls `GET /v1/admin/apps/downloads` via `serverJsonGet`.

**Layout:**

**"Share with your team" card**
- Read-only input showing `download_page_url` with a "Copy link" button (client component island)
- QR code rendered client-side from that URL using the `qrcode` npm package (canvas → data URI, no external service)
- Instruction: "Share this link with your staff. Opening it on an Android device lets them download and install the apps."

**App cards (one per app)**
- App icon (Material Symbol: `point_of_sale` for cashier, `admin_panel_settings` for admin mobile)
- Display name + description
- Version badge (`v1.2.0`) and file size (`45.3 MB`)
- Changelog text (truncated to ~3 lines if long)
- "Download APK" button → `href="/api/ims/v1/admin/apps/{app_name}/download"` (goes through the existing IMS proxy with operator JWT, triggers browser download)
- "Not yet available" empty state if `available: false`

The `qrcode` package is added as a dependency to `apps/admin-web/package.json`.

---

## Component 3: Flutter OTA Update (Cashier + Admin Mobile)

Applies to both `apps/cashier/` and `apps/admin_mobile/`. Both apps follow the same pattern.

### New packages (`pubspec.yaml` in both apps)

```yaml
package_info_plus: ^8.0.0   # reads installed versionCode
open_file: ^3.5.0            # triggers Android APK install intent
```

Apply the existing `path_provider_android` version override from the cashier's `pubspec.yaml` to admin_mobile as well if it doesn't already have it.

### Android permission (`android/app/src/main/AndroidManifest.xml` in both apps)

```xml
<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES"/>
```

### New service (`lib/services/update_service.dart` in both apps)

**`UpdateInfo`** data class:
```dart
class UpdateInfo {
  final String version;
  final int versionCode;
  final String? changelog;
  final double? sizeMb;
  final String downloadUrl;
}
```

**`UpdateService`** static methods:

`checkForUpdate(String baseUrl, String accessToken, String appName) → Future<UpdateInfo?>`
- Calls `GET {baseUrl}/v1/apps/update-check?app_name={appName}` with `Authorization: Bearer {token}`
- Gets installed `versionCode` via `PackageInfo.fromPlatform().buildNumber` (parsed as int)
- Returns `UpdateInfo` if `response.version_code > installedVersionCode`, otherwise `null`
- Returns `null` on any network error (update check must never crash the app)

`downloadApk(String downloadUrl, String accessToken, void Function(double) onProgress) → Future<String>`
- Streams the APK from `downloadUrl` using the `http` package with a `StreamedResponse`
- Writes chunks to `${(await getTemporaryDirectory()).path}/ims_update.apk`
- Calls `onProgress(bytesReceived / totalBytes)` per chunk
- Returns the local file path on completion

`installApk(String filePath) → Future<void>`
- Calls `OpenFile.open(filePath, type: "application/vnd.android.package-archive")`

### Update check in `main.dart` (both apps)

In `_check()`, after a valid session is confirmed, fire an unawaited async task:

```dart
unawaited(_checkForUpdate(session));
```

`_checkForUpdate` runs after a 2-second delay (lets the main UI settle first), then checks for an update. If found, calls `showDialog` with the update dialog.

### Update dialog

A non-dismissible `AlertDialog` (barrier dismissible = false):

- **Before download:** Shows version, size, changelog. Two buttons: **"Later"** (dismisses) and **"Update Now"** (starts download).
- **During download:** Progress bar (0–1) with percentage label. No buttons — download cannot be cancelled once started.
- **On completion:** `installApk()` is called immediately, handing off to the Android system install dialog.
- **On error:** Shows error message with a "Dismiss" button. Never crashes the app.

The "Later" option is available before download starts so staff aren't forced to update mid-shift. Once they tap "Update Now", the download is committed.

---

## Data Flow Summary

```
Dev uploads APK → platform-web → POST /v1/platform/releases → AppRelease (is_active=true)

Flutter app launch:
  → GET {baseUrl}/v1/apps/update-check   (device JWT)
  → Tenant API proxies platform manifest
  → version_code compared against installed build number
  → if newer: show update dialog
  → "Update Now" → GET {baseUrl}/v1/apps/cashier/download (device JWT)
  → 302 → platform /downloads/{token}/cashier/latest → APK stream
  → saved to temp dir → OpenFile.open() → Android install dialog

Admin shares apps:
  → admin web /apps page → GET /v1/admin/apps/downloads (operator JWT)
  → Tenant API proxies platform manifest
  → shows download_page_url + QR code + app cards with version info
  → staff scan QR on Android → browser opens download page → downloads + installs APK
```

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `services/api/app/config.py` | Add `platform_download_base_url` field |
| `services/api/app/routers/app_updates.py` | Create (4 endpoints) |
| `services/api/app/main.py` | Register new router |
| `docker-compose.yml` | Add `PLATFORM_DOWNLOAD_BASE_URL` to `api` service env |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | Add "Get Apps" nav item |
| `apps/admin-web/src/app/(main)/apps/page.tsx` | Create (server component) |
| `apps/admin-web/package.json` | Add `qrcode` dependency |
| `apps/cashier/pubspec.yaml` | Add `package_info_plus`, `open_file` |
| `apps/cashier/android/app/src/main/AndroidManifest.xml` | Add install permission |
| `apps/cashier/lib/services/update_service.dart` | Create |
| `apps/cashier/lib/main.dart` | Wire update check into `_check()` |
| `apps/admin_mobile/pubspec.yaml` | Add `package_info_plus`, `open_file` |
| `apps/admin_mobile/android/app/src/main/AndroidManifest.xml` | Add install permission |
| `apps/admin_mobile/lib/services/update_service.dart` | Create |
| `apps/admin_mobile/lib/main.dart` | Wire update check into startup |
