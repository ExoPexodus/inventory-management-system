# Admin mobile (Flutter)

**Application ID:** `com.inventory.platform.admin.admin_mobile` — separate listing from cashier.

## SDK

Use the repo-local Flutter clone: [`../../tools/flutter`](../../tools/flutter) (see root README and [`.vscode/settings.json`](../../.vscode/settings.json)).

## Commands

```bash
cd apps/admin_mobile
flutter pub get
flutter analyze
flutter test
flutter run -d windows
```

Install **Android Studio** + SDK for device/emulator APK workflows (`flutter doctor`).

## Roadmap

Tenant summary, shops, sales, stock alerts, devices, approvals — aligned with platform API.

Contract: [`../../packages/sync-protocol/openapi.yaml`](../../packages/sync-protocol/openapi.yaml).
