# Channel Setup Wizard Design Spec

**Date:** 2026-05-09
**Status:** Approved
**Phase:** 5 of 6 (UI declutter roadmap / L2)

---

## Problem

Setting up a working ecommerce channel today requires navigating 4–5 separate pages in the correct order: create an inventory pool, create the channel, configure a payment provider, optionally configure shipping and email. Non-technical merchants routinely fail at the inventory pool step — they don't know what it is or why it must come first. The "Set up a sales channel" checklist item on the dashboard has nowhere good to send people.

---

## Goals

1. A merchant can go from zero to a working ecommerce checkout in under 5 minutes without understanding inventory pools.
2. Shopify and WooCommerce merchants are recognised immediately and routed to the right place — no dead-end generic form.
3. Payment setup can be skipped and completed later without losing the rest of the work.
4. The wizard is the canonical entry point for channel creation across the app (dashboard checklist, New Entry menu, channels empty state).

---

## Non-goals

- Shopify / WooCommerce guided setup within this wizard (they redirect to the integrations page)
- Shipping carrier setup (post-wizard, optional)
- Email transactional setup (post-wizard, optional, also on setup checklist)
- Editing existing channels (existing channels page handles that)

---

## Entry points

| Surface | Old link | New link |
|---|---|---|
| Dashboard setup checklist | `/channels?new=1` | `/channels/setup` |
| New Entry menu ("Create Channel") | `/channels?new=1` | `/channels/setup` |
| Channels page empty state CTA | `?new=1` | `/channels/setup` |

---

## Page route

`apps/admin-web/src/app/(main)/channels/setup/page.tsx`

A `"use client"` page (wizard state must live client-side). Not accessible to tenants with `retail` business type — wrap with `<RequiresBusinessType types={["online","hybrid"]}>` from Phase 1.

---

## Flow

### Type-picker screen (before numbered steps)

Three large radio-card options shown on first render:

| Card | Icon | Description | Action |
|---|---|---|---|
| **Headless storefront** | `code` | Build a custom store using the IMS Storefront SDK or your own frontend | Enter wizard |
| **Shopify** | `shopping_bag` | Connect an existing Shopify store to sync inventory and orders | `router.push('/integrations')` |
| **WooCommerce** | `shopping_cart` | Connect an existing WooCommerce store | `router.push('/integrations')` |

### Step structure

Varies by business type. `business_type` is read from `useBusinessType()` (Phase 1 context, already on every page).

| Business type | Steps |
|---|---|
| `online` | Step 1: Channel details → Step 2: Payment |
| `hybrid` | Step 1: Pick shops → Step 2: Channel details → Step 3: Payment |

Step indicator bar at the top shows the steps for the current type with the active step highlighted. Previous steps are clickable (go back); future steps are not.

---

## Step content

### Step "Pick shops" (hybrid only)

- Fetch `GET /v1/admin/shops` on mount
- Render each shop as a checkable row (shop name)
- Default: all shops selected
- If no shops exist: show a callout *"You haven't added any shops yet."* with a link to `/shops/new`

The inventory pool name is auto-derived as `"{channelName} Pool"` and never shown to the user.

### Step "Channel details" (all)

Two fields:
- **Channel name** — text input, required, default value `"Online Store"`
- **Currency** — fetches `GET /v1/admin/tenant-settings/currency` on mount; shown as a read-only display (`{currency_code} — {currency_symbol}`); small helper link *"Wrong currency? Change in Settings →"* pointing to `/settings`

No channel type picker — wizard always creates `type: "headless"`.

### Step "Payment" (all)

Three radio cards at top:
- **Stripe**
- **Razorpay**
- **Skip for now**

**Stripe form fields:** `stripe_secret_key` (password input), `stripe_publishable_key`, `checkout_success_url` (placeholder: `https://yourstore.com/order/success`)

**Razorpay form fields:** `razorpay_key_id`, `razorpay_key_secret`, `checkout_success_url`

**Skip for now:** no form shown; small note: *"You can add a payment provider from the Channels page after setup."*

---

## API call sequence on "Complete"

Three sequential calls. Stop on first failure.

```
1. POST /v1/admin/inventory-pools
   Body: { name: "{channelName} Pool", shop_ids: [...selectedShopIds] }
   
   For online tenants: shop_ids = [virtual_shop.id]
   The virtual shop (kind == "virtual") is fetched from GET /v1/admin/shops
   and auto-selected — the shop picker step is skipped, but we still
   need the virtual shop's ID for the pool.

2. POST /v1/admin/channels
   Body: { type: "headless", name: channelName, inventory_pool_id: pool.id, currency_code }
   → returns channel.id

3. (if payment provider chosen — not "skip")
   POST /v1/admin/channels/{channel.id}/payment/setup-stripe
   Body: { stripe_secret_key, stripe_publishable_key, checkout_success_url }
   OR
   POST /v1/admin/channels/{channel.id}/payment/setup-razorpay
   Body: { razorpay_key_id, razorpay_key_secret, checkout_success_url }
```

---

## Error handling

| Failure point | Behaviour |
|---|---|
| Step 1 (pool creation) fails | Inline error on current step; retry button; no state lost |
| Step 2 (channel creation) fails | Inline error; retry |
| Step 3 (payment setup) fails | Channel already exists — show: *"Your channel was created, but payment setup failed. Configure it from the Channels page."* with a link to `/channels` |
| Network error at any point | Inline error with retry; no partial clean-up (idempotent pool/channel names make retry safe) |

---

## Completion

On full success: `router.push('/channels')` with a query param `?created={channel.id}` so the channels page can show a success banner for the new channel.

The channels page reads `searchParams.get('created')` and if present shows a dismissible green banner: *"Channel created successfully — your storefront is ready to connect."*

---

## Files

| File | Status | Change |
|---|---|---|
| `apps/admin-web/src/app/(main)/channels/setup/page.tsx` | NEW | Full wizard page |
| `apps/admin-web/src/components/dashboard/SetupChecklist.tsx` | MODIFY | `/channels?new=1` → `/channels/setup` for the `first_channel` item |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | MODIFY | New Entry "Create Channel" href: `/channels?new=1` → `/channels/setup` |
| `apps/admin-web/src/app/(main)/channels/page.tsx` | MODIFY | Empty state `actionHref`: `?new=1` → `/channels/setup`; read `?created=` param and show success banner |

---

## Spec self-review

**Placeholder scan:** None — all API shapes, field names, routes, and copy are fully specified.

**Internal consistency:**
- Online tenants skip the shop-picker step but still need the virtual shop ID for the pool → fetched from `GET /v1/admin/shops`, filtered by `kind == "virtual"` ✅
- `RequiresBusinessType types={["online","hybrid"]}` on the wizard page prevents retail tenants from accessing it ✅
- Payment step failure leaves a usable channel → user isn't stranded ✅
- `?created={channel.id}` convention is consistent with the `?new=1` convention already in the codebase ✅

**Scope:** Single new page + 3 small file edits. Right-sized for one plan. ✅

**Ambiguity:**
- "Virtual shop auto-selected for online" — explicit: fetch from `/v1/admin/shops`, filter `kind == "virtual"`, use that ID ✅
- Pool name derivation — explicit: `"{channelName} Pool"`, never shown to user ✅
- After failure of Step 3 — explicit: navigate to `/channels` with a specific error message ✅
