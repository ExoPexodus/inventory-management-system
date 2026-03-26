# Cashier app — Stitch reference (Tactile Archive)

Stitch project: **2327673696871788694**

Use these screens for side-by-side visual QA with the Flutter cashier (`apps/cashier`). Design tokens are centralized in [`apps/cashier/lib/cashier_tokens.dart`](../../../apps/cashier/lib/cashier_tokens.dart).

## Reference screen IDs

| Stitch screen        | Screen ID                               | Flutter implementation |
|----------------------|-----------------------------------------|-------------------------|
| Cashier Dashboard    | `8357c547a5b14f7396a045ad676d9cd2`      | `dashboard_screen.dart` |
| Inventory Lookup     | `80bfa6412b8b44c8b6a22b1c185915b6`      | `inventory_lookup_screen.dart` |
| Checkout Cart        | `ff1d3a1aea64418699fed7d28d20734e`      | `cart_screen.dart` |
| Transaction History  | `56e48fc2c0aa40ccac523183627ecd4e`      | `history_screen.dart` |

Shell / navigation: `cashier_shell.dart`.

## Downloading assets

Hosted screenshot/HTML URLs rotate; refresh them from Stitch (export or MCP `get_screen`) when you need pixel baselines.

A helper script stub lives at [`scripts/download_stitch_cashier_screens.py`](../../../scripts/download_stitch_cashier_screens.py). Populate `CASHIER_SCREENS` with current `screenshot_url` and `html_url` values from your Stitch export, then run:

```bash
python scripts/download_stitch_cashier_screens.py
```

Artifacts are written under `docs/design/stitch-cashier/screens/` with a `manifest.json`.

## Definition of done

- Primary phone viewport: layout hierarchy, spacing, radii, hero, cards/tiles, section headers, primary CTAs, empty states, and list density match the references within normal rendering differences (Flutter vs HTML).
- Bottom navigation matches Stitch tab prominence and label treatment.

See [`docs/client-architecture.md`](../../client-architecture.md) for current parity status.
