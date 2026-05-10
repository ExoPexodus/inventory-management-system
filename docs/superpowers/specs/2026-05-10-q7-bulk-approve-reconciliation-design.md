# Q7 — Bulk Approve Reconciliations Design

**Date:** 2026-05-10
**Phase:** Audit Q7 (~1-2 days)

## Problem
Approving a batch of zero-variance reconciled shifts requires clicking "Approve" on each row. For a tenant with 5+ shops × 30 days, that's a lot of clicking.

## Solution
1. New backend endpoint `POST /v1/admin/reconciliation/bulk-approve` that accepts a list of shift IDs and approves all eligible ones in one transaction.
2. Frontend: row checkboxes + "Select all zero-variance" shortcut + "Approve N selected" button.

## Backend
**New endpoint:** `POST /v1/admin/reconciliation/bulk-approve`
**Body:** `{ shift_ids: UUID[] }`
**Response:** `{ approved: int, skipped: list[{ id: UUID, reason: str }] }`

Logic:
- Filter to shifts that are: `tenant_id == ctx.tenant_id`, `status == "closed"`, `discrepancy_cents == 0`
- For each eligible shift: set `reviewed_by_user_id = ctx.operator_id`, `reviewed_at = now`
- Write a single audit row (`action = "bulk_approve_reconciliation"`)
- Skip + report shifts that don't qualify (wrong tenant, not closed, has variance)

## Frontend
On the reconciliation page (`/reconciliation`):
- Add a checkbox column to the rows table (zero-variance rows only — variance rows show no checkbox since they need resolve, not approve)
- Add a sticky action bar at the top of the table showing "N selected · Approve" when any row is selected
- "Select all" button: selects all zero-variance unreviewed rows
- "Approve N selected" submits the bulk-approve POST, refreshes list, shows toast with count

## Files
| File | Change |
|---|---|
| `services/api/app/routers/admin_reconciliation.py` | Add bulk-approve endpoint |
| `apps/admin-web/src/app/(main)/reconciliation/page.tsx` | Row checkboxes + bulk action bar |

## Out of scope
Bulk resolve for variance rows — variance shifts need individual notes/justifications, can't be bulk-handled.
