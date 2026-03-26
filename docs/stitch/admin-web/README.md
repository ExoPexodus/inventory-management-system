# Stitch design references — Admin Web Console

Artifacts for the seven MVP screens are stored under this directory. They were fetched from Stitch project `2327673696871788694` (“Transaction History”) via the `user-stitch` MCP `get_screen` tool, then downloaded with `scripts/download_stitch_admin_screens.py`.

## Layout

| Route slug (app)   | Stitch screen id                         | Local folder            |
|-------------------|-------------------------------------------|-------------------------|
| `/overview`       | `c41290bb6b3c49daaf584818fbec282f`       | `executive-overview/`   |
| `/orders`         | `bd729c55e4944488bb465b9cc44e19ee`       | `order-audit-ledger/`   |
| `/suppliers`      | `46aa7e73c37a46998ef3899377ae7aaf`       | `supplier-hub/`         |
| `/analytics`      | `e0ae24d061944017a964a1a4fbc82817`       | `analytics-insights/`   |
| `/entries`        | `376fb70716e64c8c9de7af90b98df7cc`       | `new-entry-hub/`        |
| `/inventory`      | `f98f213ca4bf42ba888b56a17d6ea2cf`       | `inventory-ledger/`     |
| `/staff`          | `4a460c16c35841d59faef891a5a12127`       | `staff-permissions/`    |

Each folder contains:

- `screen.html` — exported HTML from Stitch (reference only; app is implemented in Next.js).
- `screenshot.webp` — design screenshot.

Machine-readable index: `manifest.json`.

## Refreshing assets

```bash
python scripts/download_stitch_admin_screens.py
```

(Reuses hard-coded download URLs from the last MCP fetch; if URLs expire, run `get_screen` again and update the script.)
