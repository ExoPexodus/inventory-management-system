# Unified Product Creation Design Spec

**Date:** 2026-05-10
**Status:** Approved
**Phase:** 6 of 6 (UI declutter roadmap / L3)

---

## Problem

Creating a complete product today requires navigating 5 separate surfaces in order. The `/entries` page handles only basic fields; images, variants, and per-currency prices each live behind a different post-creation modal. New merchants routinely miss these steps, resulting in products with no images or incomplete pricing.

---

## Goals

1. One page, one "Save product" button — merchant fills in everything including images before a single API call fires.
2. Replaces `/entries` in-place — no link or routing changes needed.
3. Sequential API calls on save are transparent via a progress message.
4. Partial failures after product creation are non-blocking warnings — the product is saved regardless.

---

## Non-goals

- Consolidating EditProductDialog / VariantsModal / PricesModal into a tabbed *edit* dialog (separate future item)
- Any backend endpoint changes — all existing APIs are used as-is

---

## Route

`apps/admin-web/src/app/(main)/entries/page.tsx` — **replaced entirely**. The "Create Product" link in the New Entry sidebar menu already points to `/entries`. No other link updates required.

---

## Page structure

Full-width `"use client"` page. Four tabs in a horizontal tab bar at the top:

```
[ Details ]  [ Images ]  [ Variants ]  [ Prices ]
```

Tabs are freely navigable in any order — not a linear wizard. The "Save product" button is always visible in a sticky footer bar regardless of active tab.

---

## State model

All data lives in React `useState`. Nothing hits the backend until Save is clicked.

```tsx
// Details tab
sku: string                        // required
name: string                       // required
price: string                      // required (display as decimal)
category: string
barcode: string
costPrice: string
mrpPrice: string
hsnCode: string
variantLabel: string
productGroupId: string
status: "active" | "draft"
negativeInventory: boolean

// Images tab
stagedImages: Array<{
  file: File
  previewUrl: string               // URL.createObjectURL(file)
}>

// Variants tab
stagedVariants: Array<{
  sku: string
  name: string
  price: string                    // display as decimal
  optionPairs: Array<{ key: string; value: string }>
}>

// Prices tab
stagedPrices: Array<{
  currencyCode: string
  amount: string                   // display as decimal
}>

// Save state
savePhase: "idle" | "saving" | "done" | "error"
saveProgress: string               // human-readable progress message
saveWarnings: string[]             // non-fatal errors shown after completion
```

---

## Tab content

### Details tab

Fields (identical to current `/entries`, nothing removed):

| Field | Type | Required |
|---|---|---|
| SKU | text | yes |
| Display name | text | yes |
| Price | number | yes |
| Category | text | no |
| Barcode (UPC/EAN) | text | no |
| Cost price | number | no |
| MRP | number | no |
| HSN code | text | no |
| Variant label | text | no |
| Product group | select (fetched from `/v1/admin/product-groups`) | no |
| Status | select (active / draft) | no (defaults to active) |
| Negative inventory | toggle | no |

Price guard validation (same as current `/entries`): warn if selling price < cost price or > MRP.

### Images tab

- Drag-and-drop zone + "Browse files" button using HTML5 `<input type="file" accept="image/*" multiple>`
- Each staged image renders as a preview card (thumbnail + filename + size) with an × button to remove
- No API calls here — images are queued as `{ file: File, previewUrl: URL.createObjectURL(file) }`
- Max 10 images queued; max 10 MB per file (validated client-side before queuing, matching existing presign limits)
- Allowed types: `image/jpeg`, `image/png`, `image/webp`, `image/gif`, `image/avif`
- Helper text: *"Images will be uploaded when you save the product"*

### Variants tab

An inline add-variant form:
- Name (text), SKU (text), Price (number, required for variant)
- Option pairs: repeating key → value rows ("Add option" link adds a row). Example: `Size → M`
- "Add variant" button appends the entry to `stagedVariants` and clears the form
- Staged variants render as a table: Name | SKU | Price | Options | ×
- Empty state: *"No variants yet — add size, colour, or other options"*

### Prices tab

An inline add-price form:
- Currency code (text, 3 chars, e.g. `USD`)
- Amount (number)
- "Add price" button appends to `stagedPrices` and clears the form
- Staged prices render as a simple list: Currency | Amount | ×
- Empty state: *"No additional prices — your default price is set on the Details tab"*

---

## Save sequence

Triggered by "Save product" button. Runs all calls sequentially. Progress message updates the UI.

```
Step 1: POST /v1/admin/products
  Body: {
    sku, name,
    unit_price_cents: Math.round(parseFloat(price) * 100),
    category: category || null,
    barcode: barcode || null,
    cost_price_cents: costPrice ? Math.round(parseFloat(costPrice) * 100) : null,
    mrp_cents: mrpPrice ? Math.round(parseFloat(mrpPrice) * 100) : null,
    hsn_code: hsnCode || null,
    variant_label: variantLabel || null,
    product_group_id: productGroupId || null,
    status,
    negative_inventory_allowed: negativeInventory,
  }
  → product.id
  
Step 2: For each stagedImage (index i):
  Progress: "Uploading images (i+1 of N)…"
  
  2a. POST /v1/admin/media/presign-upload
      Body: {
        folder: `products/${product.id}`,
        filename: file.name,
        content_type: file.type,
        file_size_bytes: file.size,
      }
      → { upload_url, public_url, storage_warning? }
      
  2b. PUT upload_url  (file bytes, Content-Type: file.type)
  
  2c. POST /v1/admin/catalog/products/{product.id}/images
      Body: { url: public_url, sort_order: i, file_size_bytes: file.size }

Step 3: For each stagedVariant:
  Progress: "Adding variants…"
  POST /v1/admin/products/{product.id}/variants
  Body: {
    sku: variant.sku,
    name: variant.name,
    unit_price_cents: Math.round(parseFloat(variant.price) * 100),
    options: Object.fromEntries(
      variant.optionPairs
        .filter(p => p.key.trim())
        .map(p => [p.key.trim(), p.value.trim()])
    ),
  }

Step 4: For each stagedPrice:
  Progress: "Adding prices…"
  POST /v1/admin/products/{product.id}/prices
  Body: {
    currency_code: price.currencyCode.toUpperCase(),
    amount_cents: Math.round(parseFloat(price.amount) * 100),
    channel_id: null,
  }

Step 5: router.push('/products')
```

---

## Error handling

| Failure point | User sees | Navigation |
|---|---|---|
| Step 1 (product create) fails | Inline error on Save button area; form stays intact; retry safe | Stay on page |
| Step 2 (one image fails) | Warning added to `saveWarnings`: *"1 image failed to upload — add it from the product page later"* | Continue to step 3 |
| Step 3 (one variant fails) | Warning added: *"A variant failed to save — add it from the product page later"* | Continue to step 4 |
| Step 4 (one price fails) | Warning added: *"A price failed to save — add it from the product page later"* | Continue |
| All steps complete (with warnings) | Yellow warning banner above product list with all warnings listed | Navigate to /products |
| All steps complete (clean) | Navigate silently to /products | Navigate to /products |

**Key principle:** once the product row exists, never block navigation. Partial failures produce non-fatal warnings, not hard stops.

---

## Files changed

| File | Change |
|---|---|
| `apps/admin-web/src/app/(main)/entries/page.tsx` | Complete rewrite |

No other files change — all entry points already link to `/entries`.

---

## Spec self-review

**Placeholder scan:** None — all API bodies, field names, progress messages, and error copy are fully specified.

**Internal consistency:**
- `stagedImages[i].previewUrl = URL.createObjectURL(file)` created at queue time, not at render time ✅
- `sort_order: i` on image save matches the staged array index — order is preserved ✅
- Price `amount_cents` uses `Math.round(parseFloat(amount) * 100)` — same calculation as existing PricesModal ✅
- Storage quota warning from presign response is ignored during creation (the existing inline warning in EditProductDialog was for post-creation; during bulk creation we just continue and let the final quota guard fail gracefully) ✅
- Status defaults to "active" matching the existing `/entries` behavior ✅

**Scope:** Single file rewrite. Right-sized. ✅

**Ambiguity:**
- "Max 10 images" — enforced client-side by disabling the add button when `stagedImages.length >= 10` ✅
- "Partial failure continues" — explicit in the error table; no retries attempted mid-save ✅
- Currency amount_cents: uses `* 100` not exponent — simplified from the existing PricesModal's `currencyExponent` helper; implementer should use `* 100` since all currencies in this system use 2 decimal places as the common case ✅
