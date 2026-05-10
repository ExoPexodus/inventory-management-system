# Item 2 — Advanced RBAC Implementation Spec

**Date:** 2026-05-11
**Effort:** Smaller than originally estimated — most of the work was already done.

## Current state (already shipped)
- `Role`, `Permission`, `RolePermission` tables ✓
- `admin_roles.py` router with full CRUD + permission validation + audit log + cache invalidation ✓
- System role protection (cannot delete `is_system=true`) ✓
- Role builder UI in `apps/admin-web/src/app/(main)/team/page.tsx` Roles tab with grouped checkbox UI, bulk category select, edit/create modal ✓
- 47 permissions seeded across 22 categories
- Permission descriptions present on most, NULL on 2 (`customers:read`, `customers:write`)

## What's actually missing (per locked decisions)

### 1. Role deletion → bulk-reassign flow (decision Q6: option B)
Currently `DELETE /v1/admin/roles/{id}` returns 409 with an assigned-user count. Need a way for the admin to RESOLVE that — bulk-pick fallback roles for each assigned user, then delete.

**New endpoint:** `POST /v1/admin/roles/{id}/reassign-and-delete`
```json
{
  "assignments": [
    { "user_id": "uuid", "new_role_id": "uuid" },
    ...
  ]
}
```
Validates every assigned user is covered. Atomic: reassigns all users then deletes the role.

Also: `GET /v1/admin/roles/{id}/assigned-users` — returns users currently holding this role, so the UI can render the picker.

### 2. Role clone (decision Q7: option A)
**New endpoint:** `POST /v1/admin/roles/{id}/clone` (no body) → creates a copy with name `{source_name}_copy` and display_name `Copy of {source_display_name}`, same permission set. Returns the new role.

UI: "Clone" button on each role row in the team Roles tab.

### 3. Permission descriptions backfill (decision Q9: option B)
Migration adds descriptions to the 2 NULL permissions:
- `customers:read` → "View customers and customer groups"
- `customers:write` → "Create, edit, and delete customers and customer groups"

No new field added — the existing `description` column is sufficient. The UI already renders it.

### 4. Permission grouping (decision Q8: option C)
Already auto-derived from `Permission.category` (set in seed migrations). Manual override = whatever the seed migration sets the category to. No code change needed; this is already option C in practice. Just verify the UI's `CATEGORY_ORDER` covers all 22 categories — currently it lists 17 plus an "Access" alias. Add the 5 missing: `billing`, `commerce`, `channels`, `customers`, `shipping`.

## UI work

### Team page Roles tab — `apps/admin-web/src/app/(main)/team/page.tsx`

**Clone button** on each role row. Confirm dialog → calls POST clone → refetches.

**Delete flow update:** instead of a single "Delete" that shows 409 error, when role has assigned users:
1. Initial click opens a "Reassign and delete" modal.
2. Modal lists each assigned user with a role-picker dropdown next to them (defaults to the next-most-similar role — let's say first system role that isn't the one being deleted).
3. "Set all to..." bulk dropdown at top: when picked, fills every user's picker.
4. "Reassign and delete" button → calls the new endpoint.

When the role has no users assigned, the existing flow (direct delete) still works.

**Category order** in the permission grid — add `billing`, `commerce`, `channels`, `customers`, `shipping` to `CATEGORY_ORDER` constant at line 809.

## Files

| File | Status |
|---|---|
| `services/api/alembic/versions/20260531000001_permission_descriptions.py` | NEW migration — backfill descriptions |
| `services/api/app/routers/admin_roles.py` | Add 3 endpoints: clone, assigned-users, reassign-and-delete |
| `apps/admin-web/src/app/(main)/team/page.tsx` | Add Clone button + Reassign-delete modal + category order update |

## Out of scope
- Page-mapping impact preview (deferred per Q9)
- Per-resource permissions ("can only manage Shop X")
- Permission codename refactor / consolidation
- Bulk role assignment for new users (one user at a time during invite)
