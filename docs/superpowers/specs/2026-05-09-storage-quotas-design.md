# Storage Quota System — Design Spec

**Date:** 2026-05-09
**Status:** Approved

---

## Problem

IMS hosts product images in a platform-managed Cloudflare R2 bucket. Every tenant
uploads into the same bucket under their own `{tenant_id}/` prefix. Without enforcement,
tenants on trial or starter plans can upload unlimited data, eroding the commercial value
of higher-tier plans and creating unbounded infrastructure costs.

---

## Goals

1. Enforce per-tenant storage quotas drawn from the existing billing/license system.
2. Warn merchants at 80% usage so they can act before hitting the limit.
3. Hard-block uploads at 100% with a clear, actionable error.
4. Keep tracking simple — no R2 event plumbing, no new external dependencies.
5. Correct tracking drift daily via a lightweight background reconciliation job.
6. Skip quotas entirely for BYO-bucket tenants (not our storage, not our problem).

---

## Non-goals

- Tracking BYO bucket usage.
- Charging for storage overages (handled by the platform billing service).
- Real-time byte-perfect accuracy (client-declared + daily reconciliation is sufficient).

---

## Where limits come from

`TenantLicenseCache.storage_limit_mb` already exists, is synced from the platform billing
service, and is updated automatically when a merchant upgrades their plan or purchases a
storage add-on. This is the single source of truth for the limit. No changes needed here.

Default values in the platform billing service:

| Plan | Storage limit |
|------|--------------|
| trial | 100 MB |
| starter | 1 GB |
| pro | 10 GB |

Merchants purchase additional storage via the existing add-on system — the platform service
increments `storage_limit_mb` automatically on purchase.

---

## Data model changes

### 1. `tenants.storage_bytes_used` (new column)

```sql
ALTER TABLE tenants ADD COLUMN storage_bytes_used BIGINT NOT NULL DEFAULT 0;
```

Running counter of bytes stored in the platform bucket. Updated atomically:

```sql
-- increment (on image save)
UPDATE tenants SET storage_bytes_used = storage_bytes_used + :delta WHERE id = :id;

-- decrement (on image delete)
UPDATE tenants SET storage_bytes_used = storage_bytes_used - :delta WHERE id = :id;
```

SQL expression updates (not ORM read-modify-write) are required to prevent race conditions
when multiple images are uploaded concurrently.

### 2. `product_images.file_size_bytes` (new column)

```sql
ALTER TABLE product_images ADD COLUMN file_size_bytes BIGINT NULL;
```

Stores the size of each image in bytes. Nullable — rows created before this feature was
added will have `NULL`. The delete handler skips decrement when `NULL`. The daily
reconciliation job corrects drift from any such rows.

---

## API changes

### `POST /v1/admin/media/presign-upload`

**Request body gains:**
```json
{ "folder": "...", "filename": "...", "content_type": "...", "file_size_bytes": 245760 }
```
`file_size_bytes` is required and must be a positive integer. The frontend reads this
from `File.size` before requesting the presign URL.

**Quota check (skipped entirely for BYO tenants):**

```
limit_bytes = cache.storage_limit_mb * 1_048_576
used_bytes  = tenant.storage_bytes_used

if used_bytes + file_size_bytes > limit_bytes:
    → HTTP 402  { detail, used_bytes, limit_bytes }

if (used_bytes + file_size_bytes) / limit_bytes >= 0.80:
    → HTTP 200 with storage_warning in response
else:
    → HTTP 200 normal
```

**Success response (unchanged fields omitted):**
```json
{
  "upload_url": "...",
  "public_url": "...",
  "key": "...",
  "expires_in": 900,
  "content_type": "...",
  "storage_warning": null
}
```

When at or above 80%:
```json
{
  "upload_url": "...",
  "storage_warning": {
    "used_pct": 84,
    "used_mb": 84,
    "limit_mb": 100
  }
}
```

**Error response (HTTP 402):**
```json
{
  "detail": "Storage limit reached. You have used 100 MB of your 100 MB limit.",
  "used_bytes": 104857600,
  "limit_bytes": 104857600
}
```

---

### `POST /v1/admin/catalog/products/{product_id}/images`

**Request body gains optional field:**
```json
{ "url": "...", "alt_text": null, "sort_order": 0, "file_size_bytes": 245760 }
```

When `file_size_bytes` is provided:
1. Stored on the `product_images` row.
2. `tenants.storage_bytes_used` is incremented atomically.

This is the moment the counter moves — not at presign time. Presign is just a gate;
save is the commit.

---

### `DELETE /v1/admin/catalog/products/{product_id}/images/{image_id}`

After deleting the row, if `image.file_size_bytes IS NOT NULL`:
```sql
UPDATE tenants SET storage_bytes_used = storage_bytes_used - :delta WHERE id = :id;
```
If `file_size_bytes` is NULL (pre-feature image), the counter is unchanged. The daily
reconciliation will correct the total.

---

### `GET /v1/admin/billing/usage`

`storage_used_mb` was hardcoded to `0`. Wire it to the real value:
```python
storage_used_mb = ceil(tenant.storage_bytes_used / 1_048_576)
```

---

## Background job: `reconcile_storage_usage`

**Purpose:** Correct any drift between `storage_bytes_used` and actual R2 contents.
Drift sources: pre-feature images with NULL sizes, interrupted uploads, direct R2 deletions.

**Interval:** Controlled by `STORAGE_RECONCILE_INTERVAL_HOURS` env var (default: `24`).
Add to `services/api/app/config.py`:
```python
storage_reconcile_interval_hours: int = 24
```

**Logic:**
```python
def reconcile_storage_usage() -> str:
    for tenant in db.query(Tenant).filter_by(storage_mode="platform"):
        actual_bytes = sum_r2_prefix(f"{tenant.id}/")   # ListObjectsV2 + sum Size
        db.execute(
            update(Tenant)
            .where(Tenant.id == tenant.id)
            .values(storage_bytes_used=actual_bytes)
        )
    db.commit()
```

- Only runs for `storage_mode = "platform"` tenants.
- Uses the existing platform R2 client (boto3 `list_objects_v2` with pagination).
- Never raises — logs warnings on per-tenant failure, continues to next tenant.
- Scheduled via rq-scheduler or a cron trigger using `settings.storage_reconcile_interval_hours`.

---

## Admin web changes

### 80% warning banner

Shown on the **billing page** and the **main overview/dashboard** when:
```
storage_used_mb / storage_limit_mb >= 0.80
```

Banner text:
> *"You've used {X} MB of your {Y} MB storage limit. [Upgrade plan →] to continue uploading images without interruption."*

Dismissible per session (localStorage key `storage_warning_dismissed`). Reappears on next
page load if still above 80%.

### Inline upload warning

After a successful upload, if the presign response included `storage_warning`, the image
upload UI shows a yellow inline note beneath the upload button:
> *"Storage {used_pct}% used ({used_mb} MB of {limit_mb} MB)."*

### Hard block UI

When presign returns HTTP 402:
> *"Storage limit reached ({limit_mb} MB). [Upgrade your plan →] to upload more images."*

The upload button is disabled until the merchant navigates away or their limit increases.

---

## Configuration

New environment variable:

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_RECONCILE_INTERVAL_HOURS` | `24` | How often the reconciliation job runs |

---

## Migration

Chain from `20260524000001`:

```
20260525000001_storage_quota_fields.py
  - ADD COLUMN tenants.storage_bytes_used BIGINT NOT NULL DEFAULT 0
  - ADD COLUMN product_images.file_size_bytes BIGINT NULL
```

Existing tenants start with `storage_bytes_used = 0`. The first reconciliation run
(within 24h) sets the correct value from R2. During this window, enforcement is lenient
(counter underestimates real usage) but that is acceptable for a soft migration.

---

## Security

- Quota check happens server-side — a client cannot bypass it by forging a presign request.
- `file_size_bytes` is client-provided but validated as a positive integer. The reconciliation
  job corrects any systematic abuse (e.g. always declaring 1 byte).
- BYO tenants are fully excluded from all quota logic.

---

## Out of scope

- Real-time R2 event notifications.
- Per-product or per-folder sub-quotas.
- Automatic plan upgrades or overage charges.
- Tracking for assets outside `product_images` (e.g. logos, banners) — can be added later
  by following the same increment/decrement pattern.
