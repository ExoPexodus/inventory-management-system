# Remaining Work — Pick Up Later

**Last updated:** 2026-05-10
**Status:** 12 of 16 features from the autonomous roadmap shipped. The 4 below are deferred to future focused sessions.

This document is the **handoff brief** for resuming work. Each feature has its design decisions already locked from prior brainstorming — a fresh session can go straight to spec writing → implementation without re-litigating decisions.

---

## 1. Transfer Orders

**What:** Cross-shop inventory moves (e.g., move 10 units of SKU-X from Downtown shop to Mall shop) with an approval workflow.

**Locked design decisions:**
- **Approval workflow required** — manager must approve before stock moves
- Status flow: `draft → pending_approval → approved → in_transit → completed | rejected`

**Existing scaffolding:**
- DB models `TransferOrder` and `TransferOrderLine` already exist in `services/api/app/models/tables.py` (~line 600)
- Models are bare-bones — need to add `approved_by_user_id`, `approved_at`, `rejected_at`, `rejection_reason` columns
- No API endpoints exist
- No UI exists

**Effort estimate:** 4-6 days

**Greenfield work needed:**
1. DB migration — add approval columns + status enum constraints
2. API: `services/api/app/routers/admin_transfer_orders.py` (new) — CRUD + approve/reject + execute (creates StockMovement rows on completion)
3. UI: `apps/admin-web/src/app/(main)/transfer-orders/` (new) — list + create + detail with approve buttons
4. AppShell sidebar nav — add "Transfer Orders" item under Stock group, retail/hybrid only (online tenants don't have multiple shops)
5. RLS context for transfer orders (cross-shop, both shops must belong to the same tenant)

**Open design questions** (need brainstorm in future session):
- Required permission level for approval (`operations:write` vs new `transfers:approve`?)
- Should approval threshold be configurable per tenant? (e.g., transfers under $X auto-approve)
- What happens to source shop stock during `in_transit`? Soft-deduct + reservation? Or wait until `completed`?
- Receive flow: does the receiving shop confirm receipt and adjust `quantity_received`?

**Reference docs:** `docs/architecture.md` § stock movements

---

## 2. Advanced RBAC (Custom Roles via UI)

**What:** A role builder UI where merchants can create custom roles by ticking permission checkboxes (e.g., "Inventory Manager" role with `inventory:read`, `inventory:write`, `procurement:read` only).

**Locked design decisions:**
- **Custom roles via UI** — merchant decides which permissions per role (NOT predefined extra roles)
- Existing system roles (Owner, Admin, Cashier) are protected — can't be edited or deleted

**Existing scaffolding:**
- `Role` and `Permission` tables exist
- `RolePermission` join table exists
- The `provision_tenant` flow already creates an "Owner" role with all permissions
- Permission codenames are scattered across routers as `require_permission("foo:bar")` calls
- No central permission registry — they're string literals

**Effort estimate:** 5-7 days

**Work needed:**
1. **Permission registry** — collect every `require_permission(...)` string into a single `permissions.py` module that the API exposes via `GET /v1/admin/permissions`. Each permission gets a human-readable label and group ("Inventory > Read movements", "Channels > Configure payments")
2. **API**: `admin_roles.py` (probably exists; verify) — CRUD for roles, with system-role protection
3. **UI**: `apps/admin-web/src/app/(main)/team/roles/` (or under Settings) — list of roles, role-builder form with grouped checkboxes, permission preview
4. **Audit log** — every role change must write an audit row
5. **Existing user reassignment** — when a role is deleted, what happens to users assigned to it? Block deletion if any users hold it, or migrate them to a fallback role?

**Open design questions:**
- Should custom roles be cloneable from an existing role (templating)?
- "Permission impact preview" — when toggling a permission, show which pages/actions it controls (probably overkill for v1)
- Per-resource permissions (e.g., "this role can only manage Shop X")? — almost certainly out of scope

**Reference docs:** `services/api/app/auth/admin_deps.py` for the existing permission gate pattern

---

## 3. Platform-side Plan-Feature UI + Tenant-Creation Gap Fixes

**What:** A UI in `apps/platform-web` (the platform operator dashboard, separate from merchant admin) where platform operators can manage plans, feature limits, and per-tenant overrides without code changes. **Plus** fix the three tenant-creation gaps already documented.

**Locked design decisions:**
- **In scope** — confirmed important commercial feature
- Includes the 3 tenant-creation gap fixes (rolled into this work, not separate)

**Touches two codebases:**
- `services/platform/` (FastAPI) — separate platform service
- `apps/platform-web/` (Next.js) — separate platform admin UI

**Existing state:**
- Plans (`trial`, `starter`, `pro`) and feature limits live in **Python constants** at `services/api/app/billing/plans.py` and `features.py`
- `PlatformTenant` table on the platform side exists; tied to `Tenant` in IMS via shared UUID
- `TenantLicenseCache` syncs from platform → IMS via scheduled job
- `tenant_feature_overrides` table exists in IMS for per-tenant overrides

**The 3 tenant-creation gaps:**
1. **Storage mode never forwarded** — `services/platform/app/services/tenant_provision.py:35` doesn't include `storage_mode` or BYO bucket fields in the body it POSTs to IMS, even though the platform-web form collects them and the IMS endpoint accepts them
2. **No `TenantLicenseCache` seeded at provision time** — license sync is a separate scheduled job, leaving a window where new tenants have no license cache
3. **No initial subscription created on platform side** — platform's `subscriptions` table is independent of `tenants`; new tenants get a tenant row but no plan attached

**Effort estimate:** 5-7 days

**Work needed:**
1. **Plan management API** on the platform service — CRUD for plans, feature values per plan, add-on definitions
2. **Plan management UI** on platform-web — list + edit forms
3. **Override UI** — find a tenant, set custom limits per feature
4. **Tenant gap fixes** — patch `tenant_provision.py` to forward all storage fields, seed `TenantLicenseCache` at provision time, create a default subscription
5. **Migration** — move existing hardcoded `PLAN_FEATURES` data from `plans.py` into platform DB rows

**Open design questions:**
- Plan archiving vs deletion (archived plans can no longer be assigned to new tenants but existing ones keep their plan)
- Bulk override apply (e.g., "give all tenants in beta cohort +10 GB storage")
- Add-on stacking rules (can a tenant have multiple "Storage Boost" add-ons?)

**Reference docs:** `services/platform/`, `services/api/app/billing/`, the relevant memory file at `billing-service-architecture.md`

---

## 4. RMA Flow (Returns + Refunds + Exchanges)

**What:** A unified return-merchandise-authorisation system covering refund-only, return+refund, and exchange flows. Customer-initiated from storefront, merchant-validated, with optional return shipping and auto-refund execution.

**ALL design decisions locked** (from earlier brainstorm — see `docs/superpowers/roadmap/2026-05-10-autonomous-completion-roadmap.md`):

- **Refund types:** all three (refund-only, return+refund, exchange)
- **Inventory restock:** merchant decides per approval; tenant-level default setting; clear pathway when no restock
- **Return shipping:** configurable per request (Shiprocket return-AWB optional)
- **POS + Ecommerce coexistence:** unified RMA inbox wraps both flows
- **Refund execution:** auto-execute on approval (Stripe/Razorpay reverse charge automatically)
- **Reasons taxonomy:** structured (Damaged / Wrong item / Doesn't fit / Changed mind / Other-with-text)
- **Granularity:** line-level (refund individual items, not just whole orders)
- **Time window:** configurable per tenant, default 30 days from delivery
- **Statuses:** `requested → approved/rejected → refunded → closed` (with `received` sub-state for return+refund)
- **Customer notifications:** email at every status change
- **Customer can cancel:** yes, before approval

**Effort estimate:** 7-10 days (biggest remaining)

**Work needed:**
1. **DB schema** — new tables `refund_requests`, `refund_request_lines`, `refund_request_events` (audit trail)
2. **Migrations**
3. **Backend API**:
   - Customer-side (storefront): create request, view own requests, cancel
   - Admin-side: list/inbox, approve/reject (per-line + restock decisions), execute refund
   - Webhook trigger on approval — fire Stripe/Razorpay refund API
4. **Storefront SDK** — `requestRefund`, `cancelRefundRequest`, `listMyRefundRequests`
5. **Admin UI** — RMA inbox page (filters: status, channel, date), detail page with approve/reject controls
6. **Email templates** — request received, status update, refund completed
7. **Default settings** in tenant — `default_restock_on_refund: bool`, `refund_window_days: int`
8. **Shiprocket return-AWB integration** — call existing Shiprocket provider with reverse-shipment payload

**Why it's the biggest:** lots of cross-cutting concerns — payment integration, inventory mutation, email pipeline, customer-facing storefront flow, merchant approval UI, audit trail, status state machine. Each is small but they all have to work together correctly.

**Reference:** the locked design in the autonomous roadmap document is the most complete specification — start there, refine into a proper spec, then implementation plan.

---

## How to resume

When you come back, pick whichever feature interests you most. The natural starting point per feature:

```
1. Read this doc's section for the feature
2. Read its `Reference` material  
3. Run brainstorming skill to refine open questions → spec
4. writing-plans skill → plan
5. subagent-driven-development skill → implementation
```

Order suggestion (smallest to largest, low risk first):
1. **Transfer orders** (4-6 days) — most contained
2. **Advanced RBAC** (5-7 days) — touches many endpoints but each touch is simple
3. **Platform-side plan-feature UI** (5-7 days) — two codebases but well-defined scope
4. **RMA flow** (7-10 days) — save for last; biggest cross-cutting build

Or by business priority — if you're trying to demo to enterprise prospects, **RBAC** is the highest commercial-credibility win. If you're shipping to existing merchants, **RMA** is the highest customer-satisfaction win.

---

## Catalog scale & UX (added 2026-05-10 after Stickerize feasibility check)

Surfaced when assessing whether IMS handles the Stickerize sticker store (800+ products, 30+ tag categories, possible subcategories). The flat-tag pattern works today thanks to the server-side filtering shipped earlier in this session, but four gaps were identified.

### 5. Hierarchical Category table

**What:** A real `Category` table with `parent_id` self-reference plus a `product_categories` join table, so a product can belong to multiple categories AND categories can nest (`Anime → Shounen → Demon Slayer`).

**Today:** `Product.category` is a flat `String(128)` field; `Product.tags` is a flat JSONB list. Subcategories work only via convention (e.g. `cat:anime/shounen`).

**Why it matters:** Drill-down browse experiences (breadcrumbs, sub-category cards on a parent category page) need a real hierarchy. For Stickerize specifically: only matters if their nav has nested categories. If their navigation is flat, the existing tag system is fine indefinitely.

**Scope sketch:**
1. New `categories` table (id, tenant_id, parent_id, slug, name, sort_order)
2. Junction table `product_categories` (product_id, category_id)
3. Admin UI: tree-view for managing the hierarchy (drag-and-drop, optional)
4. Storefront API: extend `/v1/storefront/products` with `category_slug` param + new endpoint `/v1/storefront/categories` returning the tree
5. Migration helper: copy existing `Product.category` strings into the new table per tenant
6. Keep `tags` as-is — categories and tags are different concepts (browsing vs marketing labels)

**Effort:** 3-4 days

---

### 6. Admin product list pagination

**What:** Add `limit` / `offset` + server-side filtering to `GET /v1/admin/products`.

**Today:** Returns ALL products in one response (no pagination). At 800 products that's ~600 KB on every admin `/products` page load. Performance is OK but inefficient and won't scale past a few thousand products.

**Scope:**
1. Backend: extend `admin_list_products` with `limit` (default 50, max 200), `offset`, plus tag filter to mirror storefront
2. Frontend: add pagination controls to `/products`; convert client-side filter to URL params (`q` already does this from the polish week)
3. Add total-count header so the UI can show "1,234 products"

**Effort:** ½ day. This is a Q-tier fix.

---

### 7. Quantity-based & category-based discounts

**What:** Extend the discount engine so a discount can be conditional on:
- Quantity in cart (e.g. `min_quantity = 5` → "buy 5+ get 10% off")
- Category / tag membership (e.g. "20% off all stickers tagged 'clearance'")

**Today:** Discounts support per-order rules (min subtotal) but not quantity tiers or category scoping. Code-based + automatic + percentage / fixed / free-shipping all work.

**Scope sketch:**
1. New columns or related table for discount conditions
2. Update the discount evaluator to check conditions against cart contents
3. Admin UI: add condition fields to the discount form
4. Storefront: discount preview must show which line items qualified

**Effort:** 2-3 days

---

### 8. Full-text product search (later, when growing past a few thousand)

**What:** Replace the current `name ILIKE '%q%' OR sku ILIKE '%q%'` with PostgreSQL `tsvector` indexing for fuzzy / relevance-ranked search across name + description + tags.

**Today:** Basic LIKE works fine for 800 products. Will start showing latency at 10K+.

**Scope:** Add a `tsvector` GIN index on `Product`, populate it via trigger, modify search query to use `to_tsquery`. Admin search + storefront search both upgrade.

**Effort:** 1-2 days

**When:** Defer until a tenant actually has 5,000+ products. No need to build this now.

---

## Other items mentioned but not in this list

These were noted earlier in this session but are smaller / niche and don't need a dedicated session:

- Multi-carrier expansion (real Delhivery / DTDC / Bluedart integrations) — Shiprocket polish is shipped; new carriers are 1-2 days each whenever needed
- Storefront magic-link auth → SDK demo app updates — straightforward when a tenant needs it; not a feature
- Various UX-audit M3 / M4 follow-ups — primitives shipped; per-page adoption can happen incrementally as those pages are touched for other reasons
