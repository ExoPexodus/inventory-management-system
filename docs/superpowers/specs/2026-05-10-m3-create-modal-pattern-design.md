# M3 — Create UI Pattern Standardisation Design

**Date:** 2026-05-10
**Phase:** Audit M3 (~½ day, scoped down from 3-4 day full sweep)

## Problem
Create flows across list pages use inconsistent patterns: modals (Customers, Team), inline-toggled forms (Suppliers, Discounts, Tax, Channels, Purchase Orders), full pages (Entries, Shops/new — both since converted). The lack of a shared component means each page reimplements wrappers, error handling, and `?new=1` plumbing.

## Solution
Build one reusable `<CreateModal>` primitive that wraps the common shell (overlay, header, error display, footer with cancel + submit buttons). Convert ONE exemplar page (Suppliers — chosen for moderate complexity and current inline-toggle pattern). Document the primitive so future create flows adopt it without further coordination.

## Component shape
```tsx
<CreateModal
  open={showCreate}
  onClose={() => setShowCreate(false)}
  title="New supplier"
  description="Add a new vendor."
  submitLabel="Create supplier"
  onSubmit={handleCreate}
  saving={saving}
  error={err}
>
  {/* Form fields go here as children */}
</CreateModal>
```

The component handles:
- Fixed-position overlay + click-outside-to-close
- Header with title + optional description
- Body with the children
- Footer with Cancel + submit button (button label, saving state, disabled-while-saving)
- Inline error display
- Form `<form onSubmit={onSubmit}>` wrapping the body so submit-on-enter works

## Files
| File | Status |
|---|---|
| `apps/admin-web/src/components/ui/CreateModal.tsx` | NEW — primitive |
| `apps/admin-web/src/app/(main)/suppliers/page.tsx` | Convert from inline-form to CreateModal (exemplar) |

## Out of scope (future follow-up)
Converting discounts, tax, channels, purchase-orders to the new pattern. The primitive will exist; teams can adopt it incrementally.
