# Admin Mobile App Overhaul — Design Spec

**Date:** 2026-05-04  
**Status:** Approved  
**Scope:** Navigation restructure, home screen fixes, Purchase Orders tab, analytics overhaul, staff simplification, stock alerts screen. Push notifications (FCM) explicitly deferred to a future session.

---

## Overview

The admin mobile app (`apps/admin_mobile/`) needs five areas of work:

1. **Navigation + home screen** — fix the broken revenue chart, remove the staff onboarding quick action, wire up stock alerts navigation, rename the Orders tab to Purchases.
2. **Purchase Orders tab** — replace the sales transactions view with a full PO lifecycle screen (list, create, edit, detail with status transitions).
3. **Analytics overhaul** — add payment methods, hourly heatmap, shop revenue, and revenue delta badge to match admin web coverage.
4. **Staff simplification** — remove "Re-enroll Device" and "Reset Credentials" from the action sheet; keep only Deactivate/Reactivate.
5. **Stock Alerts screen** — new read-only list screen navigated to from the home quick action and KPI card.

---

## Existing Infrastructure (no changes needed)

- **Backend PO router** — `services/api/app/routers/admin_orders.py` — full CRUD already exists: `GET/POST /v1/admin/purchase-orders`, `GET/PATCH/DELETE /v1/admin/purchase-orders/{id}`, `POST/PATCH/DELETE /v1/admin/purchase-orders/{id}/lines`.
- **Backend analytics** — `services/api/app/routers/admin_analytics.py` — `hourly-heatmap`, `payment-methods`, and `shop-revenue` endpoints already exist but are never called from mobile.
- **Stock alerts endpoint** — `GET /v1/notifications/stock-alerts?threshold=5` — returns per-(shop, product) alerts where `quantity <= threshold`. Already exists, never wired to a mobile screen.
- **Supplier data** — `GET /v1/admin/suppliers` — lives in `admin_web.py`, returns supplier list. Already accessible with operator JWT.
- **Revenue delta in summary** — `GET /v1/admin/analytics/summary` already returns `delta_pct` and `prev_gross_cents`; the mobile app fetches them but renders nothing.

---

## Section 1: Navigation & Home Screen

### Tab structure

| Tab | Current | New |
|-----|---------|-----|
| 1 | Home (no permission gate) | Home (unchanged) |
| 2 | Staff (`staff:read`) | Purchases (`procurement:read`) |
| 3 | Orders (`sales:read`) | Staff (`staff:read`) |
| 4 | Analytics (`analytics:read`) | Analytics (`analytics:read`) |

Tab order swaps Staff and the renamed Purchases tab. The icon for Purchases is `shopping_bag`.

### Home screen — data layer

Replace the two parallel loads `getAnalyticsSummary(days: 1)` + `getSalesSeries(days: 1, granularity: 'hour')` with:
- `getAnalyticsSummary(days: 7)` — gives rolling-7-day Revenue, Transactions, Stock Alerts, Pending POs, and delta
- `getSalesSeries(days: 7)` — gives 7 daily bars for the revenue chart (no granularity param — backend ignores it; remove from all callers)
- Keep `getEmployees()` for the Active Staff count

### Home screen — UI changes

**KPI cards (2×2 grid):**
- Revenue (7d) — formatted with tenant currency
- Transactions (7d) — from `transaction_count`
- Pending POs — from `pending_order_count`
- Stock Alerts — tappable, navigates to `StockAlertsScreen`

**Revenue Trend chart:** shows 7 daily bars from `getSalesSeries(days: 7)`. Empty state remains "No data" text (shown only when there are genuinely no transactions).

**Quick actions (2 tiles, down from 3):**
- "Purchase Orders" → navigates to Purchases tab
- "Inventory Alerts" → navigates to `StockAlertsScreen`
- **Remove:** "Onboard New Staff"

### Files changed

- `apps/admin_mobile/lib/screens/app_shell.dart` — tab order, tab labels, permission guards
- `apps/admin_mobile/lib/screens/home_screen.dart` — data load, KPI cards, quick actions

---

## Section 2: Purchase Orders Tab

### Screens

#### `purchase_orders_screen.dart` (list)

- Status filter chips: All / Draft / Ordered / Received / Cancelled
- Calls `GET /v1/admin/purchase-orders?status=&cursor=&limit=20`
- Each row: supplier name, date, status badge (colour-coded), line count ("3 items") — no total on list view since the list endpoint does not include nested lines; total is shown on the detail screen only
- Pull-to-refresh, cursor "Load more"
- FAB (floating action button) with `add` icon → navigates to `CreateEditPurchaseOrderScreen(po: null)`

#### `create_edit_purchase_order_screen.dart` (shared create + edit)

- App bar title: "New Purchase Order" when creating, "Edit Purchase Order" when editing
- **Supplier field** — dropdown populated from `GET /v1/admin/suppliers`; required
- **Expected delivery date** — date picker; optional
- **Notes** — multiline text field; optional
- **Line items** — dynamic list:
  - Each line: product search (debounced text field against product name/SKU), quantity (integer), unit cost (decimal, in tenant currency)
  - "Add item" button appends a blank line
  - Swipe-to-delete removes a line
- **Save button** — on create: `POST /v1/admin/purchase-orders` then `POST /v1/admin/purchase-orders/{id}/lines` for each line. On edit (draft only): `PATCH /v1/admin/purchase-orders/{id}` then add/delete lines as needed.
- Validation: at least one supplier selected, at least one line item with qty > 0.

#### `purchase_order_detail_screen.dart` (detail + status transitions)

- Header card: supplier name, PO creation date, expected delivery, notes
- Status badge (colour-coded): Draft=grey, Ordered=blue, Received=green, Cancelled=red
- Line items list: product name, SKU, qty ordered, unit cost, line total
- **Bottom action bar** — shown only for actionable statuses:
  - Draft: "Mark as Ordered" (primary) + "Cancel PO" (destructive, confirmation dialog)
  - Ordered: "Mark as Received" (primary) + "Cancel PO" (destructive, confirmation dialog)
  - Received / Cancelled: no action bar
- **Edit button** in app bar (pencil icon) — only shown for Draft status; opens `CreateEditPurchaseOrderScreen(po: existingPo)`
- All status transitions call `PATCH /v1/admin/purchase-orders/{id}` with `{"status": "ordered" | "received" | "cancelled"}`

### New models

```dart
// lib/models/purchase_order.dart
class PurchaseOrder {
  final String id;
  final String? supplierId;
  final String? supplierName;
  final String status; // draft | ordered | received | cancelled
  final String? notes;
  final String? expectedDeliveryDate;
  final List<PurchaseOrderLine> lines;
  final String createdAt;
}

class PurchaseOrderLine {
  final String id;
  final String? productId;
  final String? productName;
  final String? sku;
  final int quantityOrdered;
  final int quantityReceived;
  final int unitCostCents;
}

// lib/models/supplier.dart
class Supplier {
  final String id;
  final String name;
  final String? contactEmail;
  final String? contactPhone;
  final String status; // active | inactive
}
```

### New API methods on `AdminApi`

```dart
Future<List<Supplier>> getSuppliers()
Future<List<Map<String, dynamic>>> searchProducts(String q)  // GET /v1/admin/products?q= for the line-item picker
Future<Map<String, dynamic>> getPurchaseOrders({String? status, String? cursor, int limit = 20})
Future<Map<String, dynamic>> getPurchaseOrder(String id)     // returns full PO with lines
Future<Map<String, dynamic>> createPurchaseOrder({required String supplierId, String? notes, String? expectedDeliveryDate})
Future<Map<String, dynamic>> updatePurchaseOrder(String id, {String? status, String? notes, String? expectedDeliveryDate})
Future<void> addPOLine(String poId, {required String productId, required int quantity, required int unitCostCents})
Future<void> deletePOLine(String poId, String lineId)
```

### Files changed / created

- `apps/admin_mobile/lib/models/purchase_order.dart` — Create
- `apps/admin_mobile/lib/models/supplier.dart` — Create
- `apps/admin_mobile/lib/screens/purchase_orders_screen.dart` — Create
- `apps/admin_mobile/lib/screens/create_edit_purchase_order_screen.dart` — Create
- `apps/admin_mobile/lib/screens/purchase_order_detail_screen.dart` — Create
- `apps/admin_mobile/lib/services/admin_api.dart` — Add PO + supplier API methods
- `apps/admin_mobile/lib/screens/orders_screen.dart` — Delete (replaced entirely)
- `apps/admin_mobile/lib/screens/order_detail_screen.dart` — Delete (replaced entirely)
- `apps/admin_mobile/lib/models/transaction.dart` — Delete (no longer used)

---

## Section 3: Analytics Overhaul

All changes are in `apps/admin_mobile/lib/screens/analytics_screen.dart` and `admin_api.dart`, plus new widgets.

### Revenue delta badge

`AnalyticsSummary` already contains `delta_pct` (double) and `prev_gross_cents`. The Revenue KPI card gains a badge: `+X.X%` in green or `-X.X%` in red. Badge hidden when `delta_pct == 0` or null.

### Granularity param cleanup

Remove `granularity` from all `getSalesSeries` calls. The backend parameter does not exist; passing it is harmless but misleading. Both `home_screen.dart` and `analytics_screen.dart` currently pass it.

### New sections (appended below existing top products section)

**Payment methods** — calls `GET /v1/admin/analytics/payment-methods?days=`. Displayed as a simple list: icon per tender type (cash, card, other), tender label, formatted amount, transaction count, percentage. Updates with period selector.

**Hourly heatmap** — calls `GET /v1/admin/analytics/hourly-heatmap?days=`. Displayed as a horizontally scrollable row of 24 hour blocks (00–23). Each block is colour-coded by `avg_gross_cents` intensity (lightest = lowest, darkest = highest within the range for that period). Tapping a block shows a small tooltip: "X:00 · avg {amount} · {avg_tx_count} transactions". Section title: "Peak Hours". Updates with period selector.

**Shop revenue** — calls `GET /v1/admin/analytics/shop-revenue?days=`. Rendered only when `items.length > 1` (hidden for single-shop tenants). Simple list: shop name, revenue, percentage share, transaction count. Updates with period selector.

### New API methods

```dart
Future<List<Map<String, dynamic>>> getPaymentMethods(int days)
Future<Map<String, dynamic>> getHourlyHeatmap(int days)
Future<List<Map<String, dynamic>>> getShopRevenue(int days)
```

### New widget

`apps/admin_mobile/lib/widgets/hourly_heatmap_widget.dart` — stateless widget that takes a list of `{hour, avg_gross_cents}` and renders the scrollable heat blocks. Kept separate because the rendering logic is complex enough to warrant its own file.

### Files changed / created

- `apps/admin_mobile/lib/screens/analytics_screen.dart` — Add delta badge, new sections, remove granularity param
- `apps/admin_mobile/lib/services/admin_api.dart` — Add 3 new methods
- `apps/admin_mobile/lib/widgets/hourly_heatmap_widget.dart` — Create
- `apps/admin_mobile/lib/models/analytics.dart` — Extend with new response types if needed

---

## Section 4: Staff Simplification

Single change to `apps/admin_mobile/lib/screens/staff_screen.dart`:

Remove the "Re-enroll Device" list tile and its handler (`_reEnrollDevice`) from the action bottom sheet. Remove the "Reset Credentials" list tile and its handler. The bottom sheet retains only:
- "Deactivate" (when `employee.isActive == true`)
- "Reactivate" (when `employee.isActive == false`)

The `AdminApi.reEnroll` and `AdminApi.resetCredentials` methods can remain in `admin_api.dart` (removing unused methods is not required; it avoids breaking changes if the API client is ever reused).

---

## Section 5: Stock Alerts Screen

### `stock_alerts_screen.dart`

- Calls `GET /v1/notifications/stock-alerts?threshold=5` on load
- Pull-to-refresh
- List of products at or below reorder point, each row:
  - Product name + SKU (bold)
  - Shop name (subtitle, for multi-shop context)
  - Quantity indicator: current qty vs reorder point — e.g. "3 / min. 10"
  - Left border colour: **red** for `qty == 0`, **orange** for `qty > 0 && qty <= reorder_point`
- Empty state: checkmark icon + "All stock levels are healthy"
- No edit actions — read-only

### New model

```dart
// lib/models/stock_alert.dart
class StockAlert {
  final String productId;
  final String productName;
  final String sku;
  final String shopId;
  final String shopName;
  final int currentQty;
  final int reorderPoint;
}
```

### New API method

```dart
Future<List<StockAlert>> getStockAlerts({int threshold = 5})
```

### Files changed / created

- `apps/admin_mobile/lib/models/stock_alert.dart` — Create
- `apps/admin_mobile/lib/screens/stock_alerts_screen.dart` — Create
- `apps/admin_mobile/lib/services/admin_api.dart` — Add `getStockAlerts`

---

## Complete File Change List

| File | Action |
|------|--------|
| `apps/admin_mobile/lib/screens/app_shell.dart` | Modify — tab order, labels, permissions |
| `apps/admin_mobile/lib/screens/home_screen.dart` | Modify — data load, KPIs, quick actions |
| `apps/admin_mobile/lib/screens/staff_screen.dart` | Modify — remove 2 action sheet items |
| `apps/admin_mobile/lib/screens/analytics_screen.dart` | Modify — delta badge, 3 new sections, granularity cleanup |
| `apps/admin_mobile/lib/screens/orders_screen.dart` | Delete |
| `apps/admin_mobile/lib/screens/order_detail_screen.dart` | Delete |
| `apps/admin_mobile/lib/screens/purchase_orders_screen.dart` | Create |
| `apps/admin_mobile/lib/screens/create_edit_purchase_order_screen.dart` | Create |
| `apps/admin_mobile/lib/screens/purchase_order_detail_screen.dart` | Create |
| `apps/admin_mobile/lib/screens/stock_alerts_screen.dart` | Create |
| `apps/admin_mobile/lib/models/purchase_order.dart` | Create |
| `apps/admin_mobile/lib/models/supplier.dart` | Create |
| `apps/admin_mobile/lib/models/stock_alert.dart` | Create |
| `apps/admin_mobile/lib/models/transaction.dart` | Delete |
| `apps/admin_mobile/lib/widgets/hourly_heatmap_widget.dart` | Create |
| `apps/admin_mobile/lib/services/admin_api.dart` | Modify — add ~10 new methods |

---

## What Is Explicitly Out of Scope

- **Push notifications (FCM)** — deferred; requires Firebase project setup outside this codebase.
- **Stock adjustment from mobile** — the `POST /v1/admin/inventory/adjustments` endpoint exists but creating adjustments is not part of this spec.
- **Staff creation from mobile** — no "Add Employee" flow; management only.
- **PO line editing after creation** — draft lines can be deleted and re-added; inline editing of existing lines is not included (YAGNI).
