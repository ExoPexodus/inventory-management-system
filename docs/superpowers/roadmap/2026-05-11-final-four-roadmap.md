# Final Four — Autonomous Execution Roadmap

**Date:** 2026-05-11
**Mode:** Autonomous (continuous, push after each feature, no checkpoints)
**Execution order:** TO → RBAC → Tenant-gap-fixes → Platform plan UI → RMA

---

## Item 1 — Transfer Orders (4-6 days)

**Locked decisions:**
- **Approval logic:** new `transfers:approve` permission (B). Tenant setting `transfer_auto_approve_under_cents: int | null` — transfers whose line-total is below this threshold auto-approve; above need `transfers:approve` holder. UI shows whether a transfer is auto-approved or pending. (C+B combined)
- **Stock during `in_transit`:** soft-deduct via Reservation at source on approval; final movement on `completed`. Reservation visible in UI.
- **Receive flow:** destination shop confirms receipt with `quantity_received` per line (handles partial / damaged-in-transit).
- **Self-approval:** tenant setting `transfer_allow_self_approval: bool` (default `false`). When false, creator cannot approve their own transfer.
- **Cost-basis:** snapshot `unit_cost_at_transfer_cents` on `TransferOrderLine` at approval time (locks cost for accurate per-shop COGS).

## Item 2 — Advanced RBAC (5-7 days)

**Locked decisions:**
- **Role deletion with assigned users:** block deletion until admin reassigns. The reassignment screen lets the admin bulk-change multiple users to different target roles in one flow (not one-at-a-time).
- **Role cloning:** "Clone" button on every role, opens form pre-filled with source's permissions + name "Copy of X".
- **Permission grouping:** auto-derived from codename prefix (`inventory:read` → "Inventory") by default; manual override possible via a `group` field in the permission registry.
- **Impact preview:** v1 ships text-label only with a `description` field per permission ("Edit inventory and stock movements"). Page-mapping deferred.

## Item 3a — Tenant-Creation Gap Fixes (hotfix, ~½ day)

Shipped BEFORE the plan UI as a separate small PR. Three bugs:
1. `services/platform/app/services/tenant_provision.py` does not forward `storage_mode` or BYO bucket fields to IMS in the provision POST body.
2. No `TenantLicenseCache` row seeded at provision time (sync job catches up later, leaving a window).
3. Platform's `subscriptions` table has no row created for new tenants.

## Item 3b — Platform plan-feature UI (5-7 days)

**Locked decisions:**
- **Plan changes affecting existing tenants:** platform operator chooses per change — "Apply to existing tenants: yes/no" checkbox on plan save. Yes = next license sync pushes new values to all tenants on that plan; No = existing tenants stay on their snapshot.
- **Plan archive + delete:** archiving hides a plan from new-tenant assignment while existing tenants keep their plan. Deletion is allowed AFTER archiving, but blocked if any tenant is still on it.
- **`plans.py` migration:** drop the Python constants entirely once data lives in DB. DB is source of truth.
- **Bulk overrides:** v1 includes cohort filter + apply-to-all-matching UI ("Apply this override to all tenants where business_type = retail").

## Item 4 — RMA Flow (7-10 days)

**Locked decisions** (carried from REMAINING-WORK + this session):
- All 3 refund types (refund-only, return+refund, exchange) ✓
- Restock: merchant decides per approval; tenant default; clear no-restock path ✓
- Return shipping: configurable per request (Shiprocket return-AWB optional) ✓
- Unified POS + ecommerce inbox ✓
- Auto-refund on approval (Stripe/Razorpay reverse charge) ✓
- Structured reasons taxonomy + Other-with-text ✓
- Line-level granularity AND partial-quantity within a line (refund 2 of 5 of same SKU) ✓
- Configurable window (default 30 days from delivery) ✓
- Status flow `requested → approved/rejected → refunded → closed` ✓
- Email at every status change ✓
- Customer can cancel before approval ✓
- **Shipping cost on refund:** merchant decides per approval (toggle in the admin UI)
- **Tax on refund:** merchant adjusts manually (no auto-proportional tax refund)
- **POS refund UI:** cashier app gets in-store refund initiation; merchant can also process from admin-web. Per-tenant `rma_auto_approve_under_cents` setting auto-approves small refunds.
- **Customer-facing UI:** SDK methods + a reference page in the storefront demo app
- **Cash/offline payments:** cash sales CAN use RMA. Auto-refund step is a no-op; merchant manually marks "cash refund paid" to close.
- **Partial-quantity within a line:** allowed (return 2 of 5 same SKU).

---

## Per-feature workflow

1. Brief spec → commit
2. Dispatch implementation subagent (sonnet for backend+frontend; haiku where mechanical)
3. Verify: alembic upgrade head; backend tests; admin-web build (and platform-web/storefront-sdk where touched)
4. Commit + push
5. Update progress table below, move to next

## Stop conditions
- Genuine blocker (DB schema conflict, payment provider API change, etc.)
- Otherwise continuous

## Progress
| # | Feature | Status |
|---|---|---|
| 1 | Transfer Orders | _pending_ |
| 2 | Advanced RBAC | _pending_ |
| 3a | Tenant-creation gap fixes | _pending_ |
| 3b | Platform plan-feature UI | _pending_ |
| 4 | RMA Flow | _pending_ |
