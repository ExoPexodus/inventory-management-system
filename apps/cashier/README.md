# Cashier (Flutter)

**Application ID:** `com.inventory.platform.cashier` (Android/Wayland package from `flutter create --org com.inventory.platform`).

## SDK in this repo

Flutter stable is cloned at [`../../tools/flutter`](../../tools/flutter). Add it to your PATH, or rely on Cursor/VS Code [`dart.flutterSdkPath`](../../.vscode/settings.json).

PowerShell (current session):

```powershell
$env:PATH = "G:\work\inventory-management-system\tools\flutter\bin;$env:PATH"
flutter --version
```

## Commands

```bash
cd apps/cashier
flutter pub get
flutter analyze
flutter test
flutter run -d windows    # no Android SDK required
flutter run -d chrome
```

For **Android** builds / emulators, install [Android Studio](https://developer.android.com/studio) and accept SDK licenses: `flutter doctor --android-licenses`.

## Phase 1 product scope

- Onboarding (API base URL + enrollment token / QR).
- Catalog sync (`/v1/sync/pull`), **cart**, **checkout** via `/v1/sync/push` (`sale_completed`: **cash** anytime if stock allows; **card** blocked on device when there is no Wi‑Fi/mobile data).
- Transaction history and sync status (next).

## API contract

See [`../../packages/sync-protocol/openapi.yaml`](../../packages/sync-protocol/openapi.yaml).
