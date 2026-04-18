# Create Shop Feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/shops` listing page and `/shops/new` creation form, wired to existing backend endpoints, accessible via the "New Entry" dropdown in the AppShell sidebar.

**Architecture:** Two new Next.js client-component pages under `app/(main)/shops/`. The AppShell "Create Shop" entry is converted from a disabled div to a Link pointing to `/shops/new`. Both pages use direct `fetch()` calls matching existing patterns in the codebase (entries page, inventory page).

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS, existing UI primitives (`Badge`, `Panel`, `PageHeader`, `PrimaryButton`, `SecondaryButton`, `TextInput`) from `@/components/ui/primitives`.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `apps/admin-web/src/components/dashboard/AppShell.tsx` | Convert disabled "Create Shop" div to active Link |
| Create | `apps/admin-web/src/app/(main)/shops/page.tsx` | Shop listing page |
| Create | `apps/admin-web/src/app/(main)/shops/new/page.tsx` | Shop creation form |

---

## Task 1: Enable "Create Shop" in AppShell Dropdown

**Files:**
- Modify: `apps/admin-web/src/components/dashboard/AppShell.tsx` (lines ~180–186)

The "Create Product" entry (line ~173) is a `<Link>` using `${tenantPrefix}/entries`. The "Create Shop" entry is a disabled `<div>`. Replace it with a `<Link>` following the exact same pattern.

- [ ] **Step 1: Open AppShell.tsx and locate the disabled Create Shop block**

Read `apps/admin-web/src/components/dashboard/AppShell.tsx`. Find the block that looks like:

```tsx
<div className="flex items-center justify-between border-t border-outline-variant/10 px-4 py-3 text-[13px] text-on-surface/40 cursor-not-allowed select-none">
  <div className="flex items-center gap-2">
    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">store</span>
    Create Shop
  </div>
  <span className="text-[10px] font-medium tracking-wide">Soon</span>
</div>
```

- [ ] **Step 2: Replace the disabled div with an active Link**

Replace the entire block above with:

```tsx
<Link
  href={`${tenantPrefix}/shops/new`}
  onClick={() => setEntryMenuOpen(false)}
  className="flex items-center gap-2 border-t border-outline-variant/10 px-4 py-3 text-[13px] font-medium text-on-surface hover:bg-surface-container"
>
  <span className="material-symbols-outlined text-[18px]" aria-hidden="true">store</span>
  Create Shop
</Link>
```

- [ ] **Step 3: Commit**

```bash
git add apps/admin-web/src/components/dashboard/AppShell.tsx
git commit -m "feat: enable Create Shop link in New Entry dropdown"
```

---

## Task 2: Create `/shops/new` — Shop Creation Page

**Files:**
- Create: `apps/admin-web/src/app/(main)/shops/new/page.tsx`

This page renders a single-field form (name), POSTs to `/api/ims/v1/admin/shops`, shows a badge message on error, and redirects to `/shops` on success.

- [ ] **Step 1: Create the directory and file**

Create `apps/admin-web/src/app/(main)/shops/new/page.tsx` with this content:

```tsx
"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, PageHeader, Panel, PrimaryButton, SecondaryButton, TextInput } from "@/components/ui/primitives";

export default function NewShopPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSaving(true);
    try {
      const r = await fetch("/api/ims/v1/admin/shops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (r.ok) {
        router.push("../shops");
        return;
      }
      if (r.status === 409) {
        setMsg("A shop with this name already exists.");
      } else {
        setMsg(`Failed to create shop (${r.status})`);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-6 px-4 py-8">
      <PageHeader title="Create Shop" />

      <Panel>
        <form onSubmit={handleSubmit} className="space-y-5 p-6">
          {msg ? <Badge tone="danger">{msg}</Badge> : null}

          <div>
            <label className="mb-1.5 block text-sm font-medium text-on-surface">
              Shop name
            </label>
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Main Street Branch"
              required
              maxLength={255}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create Shop"}
            </PrimaryButton>
            <SecondaryButton type="button" onClick={() => router.push("../shops")}>
              Cancel
            </SecondaryButton>
          </div>
        </form>
      </Panel>
    </div>
  );
}
```

- [ ] **Step 2: Start the dev server and verify the page renders**

```bash
cd apps/admin-web && npm run dev
```

Open `http://localhost:3000/shops/new` (or the port shown). Expected: form renders with a "Shop name" input and "Create Shop" / "Cancel" buttons.

- [ ] **Step 3: Verify form submission**

Fill in a shop name and submit. Expected:
- On success: redirected to `/shops` (which doesn't exist yet — a 404 is fine at this stage)
- On duplicate name: badge error "A shop with this name already exists."
- On empty name: browser native validation blocks submission (required attribute)

- [ ] **Step 4: Commit**

```bash
git add apps/admin-web/src/app/"(main)"/shops/new/page.tsx
git commit -m "feat: add /shops/new creation page"
```

---

## Task 3: Create `/shops` — Shop Listing Page

**Files:**
- Create: `apps/admin-web/src/app/(main)/shops/page.tsx`

This page fetches all shops and renders them in a table. Includes an empty state and a "New Shop" button.

- [ ] **Step 1: Create `apps/admin-web/src/app/(main)/shops/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ErrorState, PageHeader, Panel, PrimaryButton } from "@/components/ui/primitives";

type Shop = {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
};

export default function ShopsPage() {
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/shops");
        if (r.ok) {
          setShops((await r.json()) as Shop[]);
        } else {
          setErr(`Failed to load shops (${r.status})`);
        }
      } catch {
        setErr("Network error loading shops.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="flex items-center justify-between">
        <PageHeader title="Shops" />
        <Link href="shops/new">
          <PrimaryButton>New Shop</PrimaryButton>
        </Link>
      </div>

      <Panel>
        {loading ? (
          <div className="px-6 py-8 text-center text-sm text-on-surface-variant">Loading shops…</div>
        ) : err ? (
          <div className="px-6 py-4">
            <ErrorState detail={err} />
          </div>
        ) : shops.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm text-on-surface-variant">No shops yet.</p>
            <p className="mt-1 text-sm text-on-surface-variant">
              <Link href="shops/new" className="text-primary underline">
                Create your first shop
              </Link>
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-outline-variant/20">
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-on-surface-variant">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wide text-on-surface-variant">Created</th>
              </tr>
            </thead>
            <tbody>
              {shops.map((shop) => (
                <tr key={shop.id} className="border-b border-outline-variant/10 last:border-0">
                  <td className="px-6 py-4 font-medium text-on-surface">{shop.name}</td>
                  <td className="px-6 py-4 text-on-surface-variant">
                    {new Date(shop.created_at).toLocaleDateString(undefined, {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
```

- [ ] **Step 2: Verify the listing page**

With dev server running, open `http://localhost:3000/shops`. Expected:
- Shows existing shops in a table with Name and Created columns
- Empty state renders if no shops exist
- "New Shop" button links to `/shops/new`

- [ ] **Step 3: Verify the full creation flow**

1. Click "New Entry" in sidebar → "Create Shop" → lands on `/shops/new`
2. Enter a name → submit → redirects to `/shops`
3. New shop appears in the table

- [ ] **Step 4: Verify error case**

Submit the same shop name again. Expected: badge error "A shop with this name already exists."

- [ ] **Step 5: Commit**

```bash
git add apps/admin-web/src/app/"(main)"/shops/page.tsx
git commit -m "feat: add /shops listing page"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|---|---|
| "Create Shop" in dropdown → `/shops/new` | Task 1 |
| Remove "Soon" badge and disabled styling | Task 1 |
| `/shops/new` — name-only form | Task 2 |
| Error: name already taken (409) | Task 2 |
| On success: redirect to `/shops` | Task 2 |
| Cancel → `/shops` | Task 2 |
| `/shops` listing with Name + Created columns | Task 3 |
| "New Shop" button → `/shops/new` | Task 3 |
| Empty state | Task 3 |
| No edit/delete | (intentionally omitted) |
| No sidebar nav entry | (AppShell unchanged for nav) |
