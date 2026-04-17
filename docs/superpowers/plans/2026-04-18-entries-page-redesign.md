# Entries Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the New Entry Hub into a single-scroll product form, move shop creation out via a dropdown, and fix the currency label.

**Architecture:** Two isolated changes — (1) convert the "New Entry" sidebar button into a dropdown menu in `AppShell.tsx`, and (2) rewrite `entries/page.tsx` to collapse three tabs into a single-scroll form with a Summary card replacing the Logistics tab.

**Tech Stack:** Next.js 15, React, TypeScript, Tailwind CSS

---

## Task 1: Convert "New Entry" sidebar button to dropdown in AppShell

**Files:**
- Modify: `apps/admin-web/src/components/dashboard/AppShell.tsx:145-152`

The current `<Link>` at line 146 navigates directly to `/entries`. Replace it with a button that toggles a positioned dropdown containing "Create Product" and "Create Shop" links.

`useRef` and `useState` are already imported at line 4.

- [ ] **Step 1: Add dropdown state and click-outside ref**

Find the `AppShell` component function definition. Inside it, alongside the existing state declarations, add:

```tsx
const [entryMenuOpen, setEntryMenuOpen] = useState(false);
const entryMenuRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  function handleOutside(e: MouseEvent) {
    if (entryMenuRef.current && !entryMenuRef.current.contains(e.target as Node)) {
      setEntryMenuOpen(false);
    }
  }
  document.addEventListener("mousedown", handleOutside);
  return () => document.removeEventListener("mousedown", handleOutside);
}, []);
```

Note: `useEffect` is already imported at line 4.

- [ ] **Step 2: Replace the Link with the dropdown**

Replace this block (lines 145–152):

```tsx
<div className="shrink-0 space-y-3 px-3 pb-4 pt-2">
  <Link
    href={`${tenantPrefix}/entries`}
    className="ink-gradient flex w-full items-center justify-center gap-2 rounded-lg py-3 text-[13px] font-bold text-on-primary shadow-md transition-all hover:opacity-90 active:scale-[0.98]"
  >
    <span className="material-symbols-outlined text-lg leading-none" aria-hidden="true">add_circle</span>
    New Entry
  </Link>
```

With:

```tsx
<div className="shrink-0 space-y-3 px-3 pb-4 pt-2">
  <div ref={entryMenuRef} className="relative">
    <button
      type="button"
      onClick={() => setEntryMenuOpen((o) => !o)}
      className="ink-gradient flex w-full items-center justify-center gap-2 rounded-lg py-3 text-[13px] font-bold text-on-primary shadow-md transition-all hover:opacity-90 active:scale-[0.98]"
    >
      <span className="material-symbols-outlined text-lg leading-none" aria-hidden="true">add_circle</span>
      New Entry
    </button>
    {entryMenuOpen && (
      <div className="absolute bottom-full left-0 right-0 mb-1 overflow-hidden rounded-lg border border-outline-variant/10 bg-surface-container-lowest shadow-lg">
        <Link
          href={`${tenantPrefix}/entries`}
          onClick={() => setEntryMenuOpen(false)}
          className="flex items-center gap-2 px-4 py-3 text-[13px] font-medium text-on-surface hover:bg-surface-container"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">inventory_2</span>
          Create Product
        </Link>
        <Link
          href={`${tenantPrefix}/shops`}
          onClick={() => setEntryMenuOpen(false)}
          className="flex items-center gap-2 border-t border-outline-variant/10 px-4 py-3 text-[13px] font-medium text-on-surface hover:bg-surface-container"
        >
          <span className="material-symbols-outlined text-[18px]" aria-hidden="true">store</span>
          Create Shop
        </Link>
      </div>
    )}
  </div>
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd apps/admin-web && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors related to AppShell.

- [ ] **Step 4: Commit**

```bash
git add apps/admin-web/src/components/dashboard/AppShell.tsx
git commit -m "feat: convert New Entry button to dropdown with product/shop options"
```

---

## Task 2: Rewrite entries/page.tsx as single-scroll form

**Files:**
- Modify: `apps/admin-web/src/app/(main)/entries/page.tsx`

Remove the three-tab layout, the Create Shop form, and the standalone Create Product footer. Replace with a single `<form>` containing three card sections (Product Details, Product Image, Variants) plus a Commit button. Add a Summary card below the Live Preview in the right panel.

- [ ] **Step 1: Replace the entire file contents**

Overwrite `apps/admin-web/src/app/(main)/entries/page.tsx` with:

```tsx
"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  Badge,
  Breadcrumbs,
  DropZone,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type ProductGroup = { id: string; title: string };

export default function EntriesPage() {
  const currency = useCurrency();
  const [sku, setSku] = useState("");
  const [pname, setPname] = useState("");
  const [price, setPrice] = useState("");
  const [category, setCategory] = useState("");
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [productGroupId, setProductGroupId] = useState("");
  const [variantLabel, setVariantLabel] = useState("");
  const [newGroupTitle, setNewGroupTitle] = useState("");
  const [assetHint, setAssetHint] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/product-groups");
      if (r.ok) setProductGroups((await r.json()) as ProductGroup[]);
    })();
  }, []);

  const selectedGroupTitle = productGroups.find((g) => g.id === productGroupId)?.title ?? null;
  const previewPriceCents = Math.round(parseFloat(price) * 100);
  const priceOk = !Number.isNaN(previewPriceCents);

  async function createGroup() {
    setMsg(null);
    const title = newGroupTitle.trim();
    if (!title) {
      setMsg("Group title required");
      return;
    }
    const r = await fetch("/api/ims/v1/admin/product-groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (r.ok) {
      setNewGroupTitle("");
      const g = (await r.json()) as ProductGroup;
      setProductGroups((prev) => [...prev, g].sort((a, b) => a.title.localeCompare(b.title)));
      setProductGroupId(g.id);
      setMsg("Group created");
    } else {
      setMsg(`Group failed (${r.status})`);
    }
  }

  async function addProduct(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    const unit = Math.round(parseFloat(price) * 100);
    if (Number.isNaN(unit)) {
      setMsg("Invalid price");
      return;
    }
    const body: Record<string, unknown> = {
      sku,
      name: pname,
      unit_price_cents: unit,
      category: category || null,
    };
    if (productGroupId) body.product_group_id = productGroupId;
    const vl = variantLabel.trim();
    if (vl) body.variant_label = vl;

    const r = await fetch("/api/ims/v1/admin/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setMsg(r.ok ? "Product created" : `Product failed (${r.status})`);
    if (r.ok) {
      setSku("");
      setPname("");
      setVariantLabel("");
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: "Catalog", href: "/products" },
          { label: "New entry hub" },
        ]}
      />
      <PageHeader
        kicker="New entry hub"
        title="Create Product"
        subtitle="Fill in the details below — see a live preview on the right."
      />

      <div className="grid grid-cols-12 gap-6">
        <form onSubmit={addProduct} className="col-span-12 space-y-6 lg:col-span-7">
          {msg ? (
            <Badge tone={msg.includes("failed") ? "danger" : "good"}>{msg}</Badge>
          ) : null}

          {/* Product Details */}
          <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Product details</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-medium text-on-surface">
                SKU
                <TextInput required className="mt-1 font-mono" value={sku} onChange={(e) => setSku(e.target.value)} />
              </label>
              <label className="block text-sm font-medium text-on-surface">
                Category
                <TextInput className="mt-1" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Beverages" />
              </label>
            </div>
            <label className="block text-sm font-medium text-on-surface">
              Display name
              <TextInput required className="mt-1" value={pname} onChange={(e) => setPname(e.target.value)} />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Price ({currency.code})
              <TextInput required className="mt-1 tabular-nums" value={price} onChange={(e) => setPrice(e.target.value)} />
            </label>
          </div>

          {/* Product Image */}
          <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Product image</p>
            <DropZone
              onChange={(e) => {
                const f = e.target.files?.[0];
                setAssetHint(f ? `Queued: ${f.name}` : null);
              }}
            />
            {assetHint ? <p className="text-xs text-on-surface-variant">{assetHint}</p> : null}
          </div>

          {/* Variants */}
          <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Variants{" "}
              <span className="text-[10px] font-normal normal-case tracking-normal text-on-surface-variant/60">
                optional
              </span>
            </p>
            <SelectInput
              value={productGroupId}
              onChange={setProductGroupId}
              placeholder="None"
              options={[
                { value: "", label: "None" },
                ...productGroups.map((g) => ({ value: g.id, label: g.title })),
              ]}
            />
            <label className="block text-sm font-medium text-on-surface">
              Variant label
              <TextInput
                className="mt-1"
                placeholder="e.g. 12oz · cold"
                value={variantLabel}
                onChange={(e) => setVariantLabel(e.target.value)}
              />
            </label>
            <div className="flex flex-wrap gap-2 border-t border-outline-variant/10 pt-4">
              <TextInput
                className="min-w-[12rem] flex-1"
                placeholder="New group title"
                value={newGroupTitle}
                onChange={(e) => setNewGroupTitle(e.target.value)}
              />
              <SecondaryButton type="button" onClick={() => void createGroup()}>
                Save group
              </SecondaryButton>
            </div>
          </div>

          <PrimaryButton type="submit">Commit product</PrimaryButton>
        </form>

        {/* Right panel */}
        <div className="col-span-12 lg:col-span-5">
          <div className="sticky top-6 space-y-4">
            {/* Live Preview */}
            <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
              <div className="ink-gradient px-6 py-4">
                <p className="text-xs font-bold uppercase tracking-widest text-on-primary/90">Live preview</p>
                <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{pname || "Product name"}</p>
              </div>
              <div className="space-y-3 p-6">
                <p className="font-headline text-3xl font-extrabold text-primary">
                  {priceOk ? formatMoney(previewPriceCents, currency) : "—"}
                </p>
                <div className="flex flex-wrap gap-2 text-sm">
                  <Badge tone="default">SKU {sku || "—"}</Badge>
                  <Badge tone="good">{category || "Category"}</Badge>
                  {variantLabel ? <Badge tone="warn">{variantLabel}</Badge> : null}
                </div>
                <p className="text-xs text-on-surface-variant">
                  Tenant scope is derived from your signed-in organization.
                </p>
              </div>
            </div>

            {/* Summary */}
            <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
              <p className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Summary</p>
              <ul className="space-y-2 text-sm">
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">SKU</span>
                  <span className="font-mono font-semibold">{sku || "—"}</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">Category</span>
                  <span className={category ? "" : "italic text-on-surface-variant/60"}>
                    {category || "Uncategorized"}
                  </span>
                </li>
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">Variant</span>
                  <span className={variantLabel ? "" : "italic text-on-surface-variant/60"}>
                    {variantLabel || "Standard"}
                  </span>
                </li>
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">Group</span>
                  <span className={selectedGroupTitle ? "" : "italic text-on-surface-variant/60"}>
                    {selectedGroupTitle ?? "Ungrouped"}
                  </span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd apps/admin-web && npm run build 2>&1 | tail -20
```

Expected: no TypeScript errors. If there are type errors, the most likely cause is the `SelectInput` component's `placeholder` prop — check its definition at `apps/admin-web/src/components/ui/SelectInput.tsx` and remove the prop if it doesn't exist there.

- [ ] **Step 3: Start dev server and verify visually**

```bash
cd apps/admin-web && npm run dev
```

Open `http://localhost:3000/showcase-demo/entries` and verify:
1. No tabs visible — single scrollable form
2. Three card sections visible: "PRODUCT DETAILS", "PRODUCT IMAGE", "VARIANTS"
3. Price label reads "Price (INR)" (or whichever currency the tenant uses) — not "Price (USD)"
4. Right panel shows both "LIVE PREVIEW" and "SUMMARY" cards stacked
5. Typing in SKU/category/variant fields updates the Summary card live
6. Typing a price updates the Live Preview price with the correct currency symbol
7. No "Create shop" form visible anywhere on this page

- [ ] **Step 4: Verify the dropdown in the sidebar**

While dev server is running:
1. Click "New Entry" in the left sidebar
2. A dropdown appears above the button with "Create Product" and "Create Shop" items
3. Click "Create Product" → navigates to `/entries`
4. Click "New Entry" again → dropdown opens
5. Click "Create Shop" → navigates to `/shops`
6. Click "New Entry" → dropdown opens → click anywhere outside → dropdown closes

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/app/(main)/entries/page.tsx
git commit -m "feat: redesign entries page — single-scroll form, summary panel, currency label"
```
