# Admin Mobile App Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the admin mobile app: fix the sales-series parsing bug, replace the Orders tab with a full Purchase Orders tab, add analytics sections (payment methods, hourly heatmap, shop revenue), simplify staff actions, and add a Stock Alerts screen.

**Architecture:** All changes are within `apps/admin_mobile/`. New models go in `lib/models/`, new screens in `lib/screens/`, new widgets in `lib/widgets/`. `lib/services/admin_api.dart` gains ~12 new methods. No backend changes are required — all backend endpoints already exist.

**Tech Stack:** Flutter 3, Dart 3, `http` for API calls, `fl_chart` for bar charts, `provider` for state, `intl` for date formatting. Flutter SDK at `../../tools/flutter/bin/flutter` (run all Flutter commands from the app directory).

---

## File Map

| File | Action |
|------|--------|
| `lib/models/analytics.dart` | Modify — fix `SalesPoint.fromJson`, add `PaymentMethod`, `HeatmapBucket`, `ShopRevenue` |
| `lib/models/purchase_order.dart` | Create |
| `lib/models/supplier.dart` | Create |
| `lib/models/stock_alert.dart` | Create |
| `lib/models/transaction.dart` | Delete |
| `lib/services/admin_api.dart` | Modify — fix `getSalesSeries`, add ~12 new methods, remove `granularity` param |
| `lib/widgets/staff_card.dart` | Modify — remove Re-enroll and Reset Credentials from action sheet |
| `lib/widgets/hourly_heatmap_widget.dart` | Create |
| `lib/screens/staff_screen.dart` | Modify — remove callbacks + handlers for removed actions |
| `lib/screens/stock_alerts_screen.dart` | Create |
| `lib/screens/purchase_orders_screen.dart` | Create |
| `lib/screens/create_edit_purchase_order_screen.dart` | Create |
| `lib/screens/purchase_order_detail_screen.dart` | Create |
| `lib/screens/analytics_screen.dart` | Modify — 3 new sections, remove granularity param |
| `lib/screens/home_screen.dart` | Modify — days=7, new KPIs, new quick actions |
| `lib/screens/app_shell.dart` | Modify — tab restructure |
| `lib/screens/orders_screen.dart` | Delete |
| `lib/screens/order_detail_screen.dart` | Delete |
| `test/models_test.dart` | Create — unit tests for all fromJson methods |

---

## Task 1: Fix Sales Series Parsing Bug + Granularity Cleanup

The `getSalesSeries` method reads `data['items']` but the backend returns `data['points']`. Also, `SalesPoint.fromJson` reads `j['label']` but the backend returns `j['day']` (a date string like `"2026-05-04"`). Both bugs cause the revenue chart to show "No data" everywhere. The `granularity` query param is also silently ignored by the backend — remove it from all callers.

**Files:**
- Modify: `apps/admin_mobile/lib/models/analytics.dart`
- Modify: `apps/admin_mobile/lib/services/admin_api.dart`
- Create: `apps/admin_mobile/test/models_test.dart`

- [ ] **Step 1.1: Write the failing unit test**

Create `apps/admin_mobile/test/models_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:admin_mobile/models/analytics.dart';

void main() {
  group('SalesPoint.fromJson', () {
    test('parses day field and formats as abbreviated date label', () {
      final sp = SalesPoint.fromJson({
        'day': '2026-05-04',
        'gross_cents': 5930,
        'transaction_count': 4,
      });
      expect(sp.grossCents, 5930);
      expect(sp.transactionCount, 4);
      expect(sp.label, 'May 4');
    });

    test('returns empty label on missing day', () {
      final sp = SalesPoint.fromJson({'gross_cents': 0, 'transaction_count': 0});
      expect(sp.label, '');
    });
  });
}
```

- [ ] **Step 1.2: Run the test — confirm it fails**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter test test/models_test.dart --no-pub
```

Expected: test fails because `SalesPoint.fromJson` reads `j['label']` which is absent.

- [ ] **Step 1.3: Fix `SalesPoint.fromJson` in `lib/models/analytics.dart`**

Replace the existing `SalesPoint` class with:

```dart
class SalesPoint {
  const SalesPoint({
    required this.label,
    required this.grossCents,
    required this.transactionCount,
  });

  final String label;
  final int grossCents;
  final int transactionCount;

  static const _monthAbbr = [
    'Jan','Feb','Mar','Apr','May','Jun',
    'Jul','Aug','Sep','Oct','Nov','Dec',
  ];

  factory SalesPoint.fromJson(Map<String, dynamic> j) {
    final dayStr = j['day'] as String? ?? j['label'] as String? ?? '';
    String label = dayStr;
    if (dayStr.length >= 10) {
      try {
        final dt = DateTime.parse(dayStr);
        label = '${_monthAbbr[dt.month - 1]} ${dt.day}';
      } catch (_) {}
    }
    return SalesPoint(
      label: label,
      grossCents: j['gross_cents'] as int? ?? 0,
      transactionCount: j['transaction_count'] as int? ?? 0,
    );
  }
}
```

- [ ] **Step 1.4: Run the test — confirm it passes**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter test test/models_test.dart --no-pub
```

Expected: `All tests passed!`

- [ ] **Step 1.5: Fix `getSalesSeries` in `lib/services/admin_api.dart`**

Find the `getSalesSeries` method and replace it entirely:

```dart
Future<List<SalesPoint>> getSalesSeries({int days = 7}) async {
  final data = await _get('/v1/admin/analytics/sales-series', {'days': '$days'});
  final items = data['points'] as List<dynamic>? ?? [];
  return items.map((e) => SalesPoint.fromJson(e as Map<String, dynamic>)).toList();
}
```

- [ ] **Step 1.6: Remove granularity param from both callers and verify analyze**

In `lib/screens/home_screen.dart`, find the line calling `getSalesSeries` and remove the `granularity:` argument:
```dart
api.getSalesSeries(days: 1),
```

In `lib/screens/analytics_screen.dart`, same fix:
```dart
api.getSalesSeries(days: _days),
```

Then verify:
```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze
```

Expected: `No issues found!`

- [ ] **Step 1.7: Commit**

```bash
git add apps/admin_mobile/lib/models/analytics.dart \
        apps/admin_mobile/lib/services/admin_api.dart \
        apps/admin_mobile/test/models_test.dart \
        apps/admin_mobile/lib/screens/home_screen.dart \
        apps/admin_mobile/lib/screens/analytics_screen.dart
git commit -m "fix(admin-mobile): parse sales-series 'points'+'day' fields, remove granularity param"
```

---

## Task 2: New Data Models

Add models for Purchase Orders, Suppliers, Stock Alerts, and the three new analytics types. Add unit tests for every `fromJson`.

**Files:**
- Create: `apps/admin_mobile/lib/models/purchase_order.dart`
- Create: `apps/admin_mobile/lib/models/supplier.dart`
- Create: `apps/admin_mobile/lib/models/stock_alert.dart`
- Modify: `apps/admin_mobile/lib/models/analytics.dart` (append new classes)
- Modify: `apps/admin_mobile/test/models_test.dart` (append new tests)

- [ ] **Step 2.1: Create `lib/models/purchase_order.dart`**

```dart
class PurchaseOrderLine {
  const PurchaseOrderLine({
    required this.id,
    required this.productId,
    required this.productName,
    required this.productSku,
    required this.quantityOrdered,
    required this.quantityReceived,
    required this.unitCostCents,
  });

  final String id;
  final String productId;
  final String productName;
  final String productSku;
  final int quantityOrdered;
  final int quantityReceived;
  final int unitCostCents;

  int get lineTotalCents => quantityOrdered * unitCostCents;

  factory PurchaseOrderLine.fromJson(Map<String, dynamic> j) => PurchaseOrderLine(
        id: j['id'] as String,
        productId: j['product_id'] as String,
        productName: j['product_name'] as String? ?? '',
        productSku: j['product_sku'] as String? ?? '',
        quantityOrdered: j['quantity_ordered'] as int? ?? 0,
        quantityReceived: j['quantity_received'] as int? ?? 0,
        unitCostCents: j['unit_cost_cents'] as int? ?? 0,
      );
}

class PurchaseOrder {
  const PurchaseOrder({
    required this.id,
    required this.supplierId,
    required this.supplierName,
    required this.status,
    required this.createdAt,
    required this.lines,
    this.notes,
    this.expectedDeliveryDate,
  });

  final String id;
  final String supplierId;
  final String supplierName;
  final String status; // draft | ordered | received | cancelled
  final String createdAt;
  final List<PurchaseOrderLine> lines;
  final String? notes;
  final String? expectedDeliveryDate;

  int get totalCents => lines.fold(0, (sum, l) => sum + l.lineTotalCents);
  int get lineCount => lines.length;

  factory PurchaseOrder.fromJson(Map<String, dynamic> j) => PurchaseOrder(
        id: j['id'] as String,
        supplierId: j['supplier_id'] as String,
        supplierName: j['supplier_name'] as String? ?? '',
        status: j['status'] as String? ?? 'draft',
        createdAt: j['created_at'] as String? ?? '',
        notes: j['notes'] as String?,
        expectedDeliveryDate: j['expected_delivery_date'] as String?,
        lines: ((j['lines'] as List<dynamic>?) ?? [])
            .map((e) => PurchaseOrderLine.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
```

- [ ] **Step 2.2: Create `lib/models/supplier.dart`**

```dart
class Supplier {
  const Supplier({
    required this.id,
    required this.name,
    required this.status,
    this.contactEmail,
    this.contactPhone,
  });

  final String id;
  final String name;
  final String status; // active | inactive
  final String? contactEmail;
  final String? contactPhone;

  factory Supplier.fromJson(Map<String, dynamic> j) => Supplier(
        id: j['id'] as String,
        name: j['name'] as String? ?? '',
        status: j['status'] as String? ?? 'active',
        contactEmail: j['contact_email'] as String?,
        contactPhone: j['contact_phone'] as String?,
      );
}
```

- [ ] **Step 2.3: Create `lib/models/stock_alert.dart`**

```dart
class StockAlert {
  const StockAlert({
    required this.shopId,
    required this.shopName,
    required this.productId,
    required this.sku,
    required this.name,
    required this.quantity,
    required this.threshold,
  });

  final String shopId;
  final String shopName;
  final String productId;
  final String sku;
  final String name;
  final int quantity;
  final int threshold;

  bool get isOutOfStock => quantity == 0;

  factory StockAlert.fromJson(Map<String, dynamic> j) => StockAlert(
        shopId: j['shop_id'] as String? ?? '',
        shopName: j['shop_name'] as String? ?? '',
        productId: j['product_id'] as String? ?? '',
        sku: j['sku'] as String? ?? '',
        name: j['name'] as String? ?? '',
        quantity: j['quantity'] as int? ?? 0,
        threshold: j['threshold'] as int? ?? 5,
      );
}
```

- [ ] **Step 2.4: Append analytics extension models to `lib/models/analytics.dart`**

Add after the existing `TopProduct` class:

```dart
class PaymentMethod {
  const PaymentMethod({
    required this.tenderType,
    required this.grossCents,
    required this.transactionCount,
    required this.pct,
  });

  final String tenderType;
  final int grossCents;
  final int transactionCount;
  final double pct;

  factory PaymentMethod.fromJson(Map<String, dynamic> j) => PaymentMethod(
        tenderType: j['tender_type'] as String? ?? '',
        grossCents: j['gross_cents'] as int? ?? 0,
        transactionCount: j['transaction_count'] as int? ?? 0,
        pct: (j['pct'] as num?)?.toDouble() ?? 0.0,
      );
}

class HeatmapBucket {
  const HeatmapBucket({
    required this.hour,
    required this.avgGrossCents,
    required this.avgTxCount,
  });

  final int hour;
  final int avgGrossCents;
  final double avgTxCount;

  factory HeatmapBucket.fromJson(Map<String, dynamic> j) => HeatmapBucket(
        hour: j['hour'] as int? ?? 0,
        avgGrossCents: (j['avg_gross_cents'] as num?)?.toInt() ?? 0,
        avgTxCount: (j['avg_tx_count'] as num?)?.toDouble() ?? 0.0,
      );
}

class ShopRevenue {
  const ShopRevenue({
    required this.shopId,
    required this.shopName,
    required this.grossCents,
    required this.transactionCount,
    required this.pct,
  });

  final String shopId;
  final String shopName;
  final int grossCents;
  final int transactionCount;
  final double pct;

  factory ShopRevenue.fromJson(Map<String, dynamic> j) => ShopRevenue(
        shopId: j['shop_id'] as String? ?? '',
        shopName: j['shop_name'] as String? ?? '',
        grossCents: j['gross_cents'] as int? ?? 0,
        transactionCount: j['transaction_count'] as int? ?? 0,
        pct: (j['pct'] as num?)?.toDouble() ?? 0.0,
      );
}
```

- [ ] **Step 2.5: Append model tests to `test/models_test.dart`**

Add these imports at the top of the file (after existing imports):

```dart
import 'package:admin_mobile/models/purchase_order.dart';
import 'package:admin_mobile/models/stock_alert.dart';
import 'package:admin_mobile/models/analytics.dart';
```

Then append these groups inside `main()`:

```dart
  group('PurchaseOrder.fromJson', () {
    test('parses header and computes totalCents from lines', () {
      final po = PurchaseOrder.fromJson({
        'id': 'po-1', 'supplier_id': 'sup-1', 'supplier_name': 'Acme',
        'status': 'draft', 'created_at': '2026-05-04T10:00:00Z',
        'lines': [
          {
            'id': 'l-1', 'product_id': 'p-1', 'product_name': 'Widget',
            'product_sku': 'WGT', 'quantity_ordered': 3,
            'quantity_received': 0, 'unit_cost_cents': 500,
          },
        ],
      });
      expect(po.supplierName, 'Acme');
      expect(po.status, 'draft');
      expect(po.lineCount, 1);
      expect(po.totalCents, 1500);
    });

    test('handles empty lines gracefully', () {
      final po = PurchaseOrder.fromJson({
        'id': 'po-2', 'supplier_id': 'sup-1', 'supplier_name': 'X',
        'status': 'ordered', 'created_at': '2026-05-04T10:00:00Z',
      });
      expect(po.totalCents, 0);
      expect(po.lineCount, 0);
    });
  });

  group('StockAlert.fromJson', () {
    test('parses fields correctly', () {
      final alert = StockAlert.fromJson({
        'shop_id': 's1', 'shop_name': 'Main', 'product_id': 'p1',
        'sku': 'ABC', 'name': 'Chai', 'quantity': 0, 'threshold': 5,
      });
      expect(alert.name, 'Chai');
      expect(alert.quantity, 0);
      expect(alert.isOutOfStock, true);
    });

    test('isOutOfStock false when quantity > 0', () {
      final alert = StockAlert.fromJson({
        'shop_id': 's1', 'shop_name': 'Main', 'product_id': 'p1',
        'sku': 'ABC', 'name': 'Tea', 'quantity': 3, 'threshold': 5,
      });
      expect(alert.isOutOfStock, false);
    });
  });

  group('HeatmapBucket.fromJson', () {
    test('parses hour and avgGrossCents', () {
      final b = HeatmapBucket.fromJson({
        'hour': 14, 'avg_gross_cents': 2500, 'avg_tx_count': 3.5,
      });
      expect(b.hour, 14);
      expect(b.avgGrossCents, 2500);
      expect(b.avgTxCount, 3.5);
    });
  });
```

- [ ] **Step 2.6: Run all model tests**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter test test/models_test.dart --no-pub
```

Expected: all tests pass.

- [ ] **Step 2.7: Commit**

```bash
git add apps/admin_mobile/lib/models/ apps/admin_mobile/test/models_test.dart
git commit -m "feat(admin-mobile): add PurchaseOrder, Supplier, StockAlert models and analytics extensions"
```

---

## Task 3: AdminApi Extensions

Add all new API methods to `lib/services/admin_api.dart`. All methods follow the existing `_get` / `_getList` / `_post` / `_patch` / `_delete` helper pattern.

**Files:**
- Modify: `apps/admin_mobile/lib/services/admin_api.dart`

- [ ] **Step 3.1: Add imports at top of `admin_api.dart`**

Add after existing model imports:

```dart
import '../models/purchase_order.dart';
import '../models/stock_alert.dart';
import '../models/supplier.dart';
```

- [ ] **Step 3.2: Add stock alerts method**

Append after the `getTransactions` method:

```dart
  // ── Stock Alerts ─────────────────────────────────────────────────────

  Future<List<StockAlert>> getStockAlerts({int threshold = 5}) async {
    final list = await _getList(
      '/v1/notifications/stock-alerts',
      {'threshold': '$threshold'},
    );
    return list.map((e) => StockAlert.fromJson(e as Map<String, dynamic>)).toList();
  }
```

- [ ] **Step 3.3: Add supplier + product search methods**

```dart
  // ── Suppliers & Products ─────────────────────────────────────────────

  Future<List<Supplier>> getSuppliers() async {
    final list = await _getList('/v1/admin/suppliers');
    return list.map((e) => Supplier.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// Search products by name/SKU for the PO line-item picker.
  Future<List<Map<String, dynamic>>> searchProducts(String q) async {
    final list = await _getList('/v1/admin/products', {'q': q, 'limit': '20'});
    return list.map((e) => e as Map<String, dynamic>).toList();
  }
```

- [ ] **Step 3.4: Add purchase order methods**

```dart
  // ── Purchase Orders ──────────────────────────────────────────────────

  /// Returns {items: [...POOut], next_cursor: String?}
  Future<Map<String, dynamic>> getPurchaseOrders({
    String? status,
    String? cursor,
    int limit = 20,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (status != null && status != 'all') params['status'] = status;
    if (cursor != null) params['cursor'] = cursor;
    return _get('/v1/admin/purchase-orders', params);
  }

  Future<PurchaseOrder> getPurchaseOrder(String id) async {
    final data = await _get('/v1/admin/purchase-orders/$id');
    return PurchaseOrder.fromJson(data);
  }

  Future<PurchaseOrder> createPurchaseOrder({
    required String supplierId,
    String? notes,
    String? expectedDeliveryDate,
  }) async {
    final body = <String, dynamic>{'supplier_id': supplierId};
    if (notes != null && notes.isNotEmpty) body['notes'] = notes;
    if (expectedDeliveryDate != null) {
      body['expected_delivery_date'] = expectedDeliveryDate;
    }
    final data = await _post('/v1/admin/purchase-orders', body);
    return PurchaseOrder.fromJson(data);
  }

  Future<PurchaseOrder> updatePurchaseOrder(
    String id, {
    String? status,
    String? notes,
    String? expectedDeliveryDate,
  }) async {
    final body = <String, dynamic>{};
    if (status != null) body['status'] = status;
    if (notes != null) body['notes'] = notes;
    if (expectedDeliveryDate != null) {
      body['expected_delivery_date'] = expectedDeliveryDate;
    }
    final data = await _patch('/v1/admin/purchase-orders/$id', body);
    return PurchaseOrder.fromJson(data);
  }

  Future<void> addPOLine(
    String poId, {
    required String productId,
    required int quantity,
    required int unitCostCents,
  }) async {
    await _post('/v1/admin/purchase-orders/$poId/lines', {
      'product_id': productId,
      'quantity_ordered': quantity,
      'unit_cost_cents': unitCostCents,
    });
  }

  Future<void> deletePOLine(String poId, String lineId) =>
      _delete('/v1/admin/purchase-orders/$poId/lines/$lineId');
```

- [ ] **Step 3.5: Add analytics extension methods**

```dart
  // ── Analytics extensions ─────────────────────────────────────────────

  Future<List<PaymentMethod>> getPaymentMethods(int days) async {
    final data = await _get('/v1/admin/analytics/payment-methods', {'days': '$days'});
    final items = data['items'] as List<dynamic>? ?? [];
    return items.map((e) => PaymentMethod.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<HeatmapBucket>> getHourlyHeatmap(int days) async {
    final data = await _get('/v1/admin/analytics/hourly-heatmap', {'days': '$days'});
    final buckets = data['buckets'] as List<dynamic>? ?? [];
    return buckets.map((e) => HeatmapBucket.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<ShopRevenue>> getShopRevenue(int days) async {
    final data = await _get('/v1/admin/analytics/shop-revenue', {'days': '$days'});
    final items = data['items'] as List<dynamic>? ?? [];
    return items.map((e) => ShopRevenue.fromJson(e as Map<String, dynamic>)).toList();
  }
```

Add the missing imports for the new analytics types after `import '../models/analytics.dart';`:

```dart
import '../models/analytics.dart';
// PaymentMethod, HeatmapBucket, ShopRevenue are defined in analytics.dart — already imported.
```

- [ ] **Step 3.6: Verify analyze is clean**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze lib/services/admin_api.dart
```

Expected: `No issues found!`

- [ ] **Step 3.7: Commit**

```bash
git add apps/admin_mobile/lib/services/admin_api.dart
git commit -m "feat(admin-mobile): add PO, supplier, stock-alert, and analytics API methods"
```

---

## Task 4: Staff Simplification

Remove "Re-enroll Device" and "Reset Credentials" from the action sheet. The actions are rendered in `staff_card.dart` (the `_showActions` method) and the callbacks are declared on both `StaffCard` and `StaffScreen`.

**Files:**
- Modify: `apps/admin_mobile/lib/widgets/staff_card.dart`
- Modify: `apps/admin_mobile/lib/screens/staff_screen.dart`

- [ ] **Step 4.1: Update `StaffCard` widget signature in `lib/widgets/staff_card.dart`**

Replace the constructor and fields — remove `onReEnroll` and `onResetCredentials`:

```dart
class StaffCard extends StatelessWidget {
  const StaffCard({
    super.key,
    required this.employee,
    required this.onDeactivate,
    required this.onReactivate,
  });

  final Employee employee;
  final VoidCallback onDeactivate;
  final VoidCallback onReactivate;
```

- [ ] **Step 4.2: Remove the two action tiles from `_showActions` in `staff_card.dart`**

In the `_showActions` method, the `if (emp.isActive)` block currently shows three tiles: Re-enroll Device, Reset Credentials, Deactivate. Replace it with just Deactivate:

```dart
      if (emp.isActive) ...[
        _BottomSheetAction(
          icon: Icons.person_off_rounded,
          label: 'Deactivate',
          color: AdminColors.onErrorContainer,
          onTap: () { Navigator.pop(ctx); onDeactivate(); },
        ),
      ] else
        _BottomSheetAction(
          icon: Icons.person_rounded,
          label: 'Reactivate',
          color: const Color(0xFF1A6B3C),
          onTap: () { Navigator.pop(ctx); onReactivate(); },
        ),
```

- [ ] **Step 4.3: Remove unused methods and callbacks from `lib/screens/staff_screen.dart`**

Remove the `_reEnroll` method and the `_resetCredentials` method entirely from `_StaffScreenState`.

Update all `StaffCard(...)` calls — remove `onReEnroll:` and `onResetCredentials:` arguments:

```dart
StaffCard(
  employee: emp,
  onDeactivate: () => _deactivate(emp),
  onReactivate: () => _reactivate(emp),
),
```

Remove the `import 'package:qr_flutter/qr_flutter.dart';` line from `staff_screen.dart` since it was only used by `_reEnroll`.

- [ ] **Step 4.4: Verify analyze**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze lib/widgets/staff_card.dart lib/screens/staff_screen.dart
```

Expected: `No issues found!`

- [ ] **Step 4.5: Commit**

```bash
git add apps/admin_mobile/lib/widgets/staff_card.dart \
        apps/admin_mobile/lib/screens/staff_screen.dart
git commit -m "feat(admin-mobile): remove re-enroll and reset credentials from staff actions"
```

---

## Task 5: Stock Alerts Screen

New read-only screen showing products below their reorder threshold.

**Files:**
- Create: `apps/admin_mobile/lib/screens/stock_alerts_screen.dart`

- [ ] **Step 5.1: Create `lib/screens/stock_alerts_screen.dart`**

```dart
import 'package:flutter/material.dart';

import '../admin_tokens.dart';
import '../models/stock_alert.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/section_header.dart';
import 'app_shell.dart';

class StockAlertsScreen extends StatefulWidget {
  const StockAlertsScreen({super.key});

  @override
  State<StockAlertsScreen> createState() => _StockAlertsScreenState();
}

class _StockAlertsScreenState extends State<StockAlertsScreen> {
  bool _loading = true;
  String? _error;
  List<StockAlert> _alerts = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { Navigator.of(context).pop(); return; }
      final api = AdminApi(session.baseUrl, session.token);
      final alerts = await api.getStockAlerts();
      if (!mounted) return;
      setState(() { _alerts = alerts; _loading = false; });
    } on ApiException catch (e) {
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (_) {
      if (mounted) setState(() { _error = 'Connection error. Pull to refresh.'; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Stock Alerts')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.cloud_off_rounded, size: 48, color: AdminColors.onSurfaceVariant),
                        const SizedBox(height: 12),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh_rounded),
                          label: const Text('Retry'),
                        ),
                      ],
                    ),
                  )
                : _alerts.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.check_circle_outline_rounded,
                                size: 56, color: const Color(0xFF1A6B3C)),
                            const SizedBox(height: 12),
                            Text(
                              'All stock levels are healthy',
                              style: theme.textTheme.titleMedium?.copyWith(
                                color: AdminColors.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      )
                    : CustomScrollView(
                        slivers: [
                          SliverPadding(
                            padding: const EdgeInsets.fromLTRB(
                              AdminSpacing.gutter, AdminSpacing.lg,
                              AdminSpacing.gutter, 0,
                            ),
                            sliver: SliverToBoxAdapter(
                              child: SectionHeader(
                                label: '${_alerts.length} product${_alerts.length == 1 ? '' : 's'}',
                                title: 'Low Stock',
                              ),
                            ),
                          ),
                          SliverPadding(
                            padding: const EdgeInsets.fromLTRB(
                              AdminSpacing.gutter, AdminSpacing.md,
                              AdminSpacing.gutter, 80,
                            ),
                            sliver: SliverList.separated(
                              itemCount: _alerts.length,
                              separatorBuilder: (_, __) => const SizedBox(height: AdminSpacing.sm),
                              itemBuilder: (_, i) => _AlertTile(alert: _alerts[i]),
                            ),
                          ),
                        ],
                      ),
      ),
    );
  }
}

class _AlertTile extends StatelessWidget {
  const _AlertTile({required this.alert});
  final StockAlert alert;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isOut = alert.isOutOfStock;
    final borderColor = isOut ? AdminColors.error : const Color(0xFFE65100);
    final bgColor = isOut ? AdminColors.errorContainer : const Color(0xFFFFF3E0);
    final labelColor = isOut ? AdminColors.onErrorContainer : const Color(0xFFBF360C);

    return Container(
      decoration: BoxDecoration(
        color: AdminColors.card,
        borderRadius: BorderRadius.circular(AdminRadius.quickTile),
        border: Border(left: BorderSide(color: borderColor, width: 4)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AdminSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(alert.name, style: theme.textTheme.titleMedium),
                  Text(
                    '${alert.sku} · ${alert.shopName}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: AdminColors.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: bgColor,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                isOut ? 'Out of stock' : '${alert.quantity} / min. ${alert.threshold}',
                style: theme.textTheme.labelMedium?.copyWith(
                  color: labelColor,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 5.2: Verify analyze**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze lib/screens/stock_alerts_screen.dart
```

Expected: `No issues found!`

- [ ] **Step 5.3: Commit**

```bash
git add apps/admin_mobile/lib/screens/stock_alerts_screen.dart
git commit -m "feat(admin-mobile): add Stock Alerts screen"
```

---

## Task 6: Purchase Orders List Screen

**Files:**
- Create: `apps/admin_mobile/lib/screens/purchase_orders_screen.dart`

- [ ] **Step 6.1: Create `lib/screens/purchase_orders_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../admin_tokens.dart';
import '../models/purchase_order.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/section_header.dart';
import 'app_shell.dart';
import 'create_edit_purchase_order_screen.dart';
import 'purchase_order_detail_screen.dart';

const _statuses = ['All', 'Draft', 'Ordered', 'Received', 'Cancelled'];

Color _statusColor(String status) {
  switch (status) {
    case 'draft': return AdminColors.onSurfaceVariant;
    case 'ordered': return AdminColors.primary;
    case 'received': return const Color(0xFF1A6B3C);
    case 'cancelled': return AdminColors.onErrorContainer;
    default: return AdminColors.onSurfaceVariant;
  }
}

Color _statusBg(String status) {
  switch (status) {
    case 'draft': return AdminColors.surfaceContainerHigh;
    case 'ordered': return AdminColors.primaryContainer.withValues(alpha: 0.15);
    case 'received': return const Color(0xFFD6F0E3);
    case 'cancelled': return AdminColors.errorContainer;
    default: return AdminColors.surfaceContainerHigh;
  }
}

class PurchaseOrdersScreen extends StatefulWidget {
  const PurchaseOrdersScreen({super.key, required this.onLogout});
  final VoidCallback onLogout;

  @override
  State<PurchaseOrdersScreen> createState() => _PurchaseOrdersScreenState();
}

class _PurchaseOrdersScreenState extends State<PurchaseOrdersScreen> {
  bool _loading = true;
  String? _error;
  List<PurchaseOrder> _orders = [];
  String? _nextCursor;
  bool _loadingMore = false;
  String _filterStatus = 'All';
  AdminApi? _api;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; _nextCursor = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { widget.onLogout(); return; }
      _api = AdminApi(session.baseUrl, session.token);
      final data = await _api!.getPurchaseOrders(
        status: _filterStatus.toLowerCase() == 'all' ? null : _filterStatus.toLowerCase(),
      );
      if (!mounted) return;
      final items = (data['items'] as List<dynamic>? ?? [])
          .map((e) => PurchaseOrder.fromJson(e as Map<String, dynamic>))
          .toList();
      setState(() {
        _orders = items;
        _nextCursor = data['next_cursor'] as String?;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (e.statusCode == 401) { await SessionStore.clearLogin(); if (mounted) widget.onLogout(); return; }
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (_) {
      if (mounted) setState(() { _error = 'Connection error'; _loading = false; });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _nextCursor == null || _api == null) return;
    setState(() => _loadingMore = true);
    try {
      final data = await _api!.getPurchaseOrders(
        status: _filterStatus.toLowerCase() == 'all' ? null : _filterStatus.toLowerCase(),
        cursor: _nextCursor,
      );
      final items = (data['items'] as List<dynamic>? ?? [])
          .map((e) => PurchaseOrder.fromJson(e as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      setState(() {
        _orders.addAll(items);
        _nextCursor = data['next_cursor'] as String?;
        _loadingMore = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Purchases'),
        actions: [
          IconButton(
            onPressed: () => showLogoutDialog(context, widget.onLogout),
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Sign out',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          await Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const CreateEditPurchaseOrderScreen(),
          ));
          _load();
        },
        child: const Icon(Icons.add_rounded),
      ),
      body: Column(
        children: [
          // Status filter chips
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AdminSpacing.gutter, AdminSpacing.md, AdminSpacing.gutter, 0,
            ),
            child: SizedBox(
              height: 36,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: _statuses.map((s) {
                  final selected = _filterStatus == s;
                  return Padding(
                    padding: const EdgeInsets.only(right: AdminSpacing.xs),
                    child: FilterChip(
                      label: Text(s),
                      selected: selected,
                      onSelected: (_) {
                        setState(() => _filterStatus = s);
                        _load();
                      },
                      selectedColor: AdminColors.primary.withValues(alpha: 0.14),
                      labelStyle: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: selected ? AdminColors.primary : AdminColors.onSurfaceVariant,
                        fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
          const SizedBox(height: AdminSpacing.md),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.cloud_off_rounded, size: 48, color: AdminColors.onSurfaceVariant),
                            const SizedBox(height: 12),
                            Text(_error!, textAlign: TextAlign.center),
                            const SizedBox(height: 16),
                            FilledButton.icon(onPressed: _load,
                              icon: const Icon(Icons.refresh_rounded), label: const Text('Retry')),
                          ],
                        ),
                      )
                    : RefreshIndicator(
                        onRefresh: _load,
                        child: _orders.isEmpty
                            ? ListView(children: [
                                SizedBox(
                                  height: 300,
                                  child: Center(
                                    child: Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(Icons.shopping_bag_outlined, size: 48,
                                            color: AdminColors.onSurfaceVariant),
                                        const SizedBox(height: 12),
                                        Text('No purchase orders',
                                          style: Theme.of(context).textTheme.bodyMedium
                                              ?.copyWith(color: AdminColors.onSurfaceVariant)),
                                      ],
                                    ),
                                  ),
                                ),
                              ])
                            : ListView.separated(
                                padding: const EdgeInsets.fromLTRB(
                                  AdminSpacing.gutter, 0, AdminSpacing.gutter, 100,
                                ),
                                itemCount: _orders.length + (_nextCursor != null ? 1 : 0),
                                separatorBuilder: (_, __) => const SizedBox(height: AdminSpacing.sm),
                                itemBuilder: (_, i) {
                                  if (i == _orders.length) {
                                    if (!_loadingMore) {
                                      WidgetsBinding.instance.addPostFrameCallback((_) => _loadMore());
                                    }
                                    return const Padding(
                                      padding: EdgeInsets.all(16),
                                      child: Center(child: CircularProgressIndicator()),
                                    );
                                  }
                                  final po = _orders[i];
                                  return _POTile(
                                    po: po,
                                    onTap: () async {
                                      await Navigator.of(context).push(MaterialPageRoute(
                                        builder: (_) => PurchaseOrderDetailScreen(poId: po.id),
                                      ));
                                      _load();
                                    },
                                  );
                                },
                              ),
                      ),
          ),
        ],
      ),
    );
  }
}

class _POTile extends StatelessWidget {
  const _POTile({required this.po, required this.onTap});
  final PurchaseOrder po;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String dateLabel = '';
    try {
      final dt = DateTime.parse(po.createdAt).toLocal();
      dateLabel = DateFormat('MMM d, y').format(dt);
    } catch (_) {}

    return Material(
      color: AdminColors.card,
      borderRadius: BorderRadius.circular(AdminRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AdminSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(po.supplierName, style: theme.textTheme.titleMedium),
                    const SizedBox(height: 2),
                    Text(
                      '$dateLabel · ${po.lineCount} item${po.lineCount == 1 ? '' : 's'}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: AdminColors.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AdminSpacing.sm),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _statusBg(po.status),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  po.status[0].toUpperCase() + po.status.substring(1),
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: _statusColor(po.status),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: AdminSpacing.xs),
              const Icon(Icons.chevron_right_rounded, color: AdminColors.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 6.2: Verify analyze**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze lib/screens/purchase_orders_screen.dart
```

Expected: `No issues found!` (imports for `CreateEditPurchaseOrderScreen` and `PurchaseOrderDetailScreen` will resolve once those files are created in Tasks 7 and 8; if the analyzer complains about missing files, create stub files first and complete them in the next tasks.)

- [ ] **Step 6.3: Commit**

```bash
git add apps/admin_mobile/lib/screens/purchase_orders_screen.dart
git commit -m "feat(admin-mobile): add Purchase Orders list screen"
```

---

## Task 7: Purchase Orders — Create/Edit Screen

**Files:**
- Create: `apps/admin_mobile/lib/screens/create_edit_purchase_order_screen.dart`

- [ ] **Step 7.1: Create `lib/screens/create_edit_purchase_order_screen.dart`**

```dart
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../admin_tokens.dart';
import '../models/purchase_order.dart';
import '../models/supplier.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';

/// Pass [existingPo] to edit a draft PO; leave null to create a new one.
class CreateEditPurchaseOrderScreen extends StatefulWidget {
  const CreateEditPurchaseOrderScreen({super.key, this.existingPo});
  final PurchaseOrder? existingPo;

  @override
  State<CreateEditPurchaseOrderScreen> createState() =>
      _CreateEditPurchaseOrderScreenState();
}

class _LineItemState {
  String? productId;
  String? productName;
  String? productSku;
  final TextEditingController qtyCtrl;
  final TextEditingController costCtrl;

  _LineItemState({
    this.productId,
    this.productName,
    this.productSku,
    int quantity = 1,
    int unitCostCents = 0,
  })  : qtyCtrl = TextEditingController(text: quantity > 0 ? '$quantity' : ''),
        costCtrl = TextEditingController(
          text: unitCostCents > 0
              ? (unitCostCents / 100).toStringAsFixed(2)
              : '',
        );

  void dispose() {
    qtyCtrl.dispose();
    costCtrl.dispose();
  }

  int get qty => int.tryParse(qtyCtrl.text) ?? 0;
  int get costCents => ((double.tryParse(costCtrl.text) ?? 0.0) * 100).round();
  bool get isValid => productId != null && qty > 0;
}

class _CreateEditPurchaseOrderScreenState
    extends State<CreateEditPurchaseOrderScreen> {
  bool _loadingInit = true;
  bool _saving = false;
  String? _error;

  List<Supplier> _suppliers = [];
  Supplier? _selectedSupplier;
  final _notesCtrl = TextEditingController();
  DateTime? _deliveryDate;
  final List<_LineItemState> _lines = [];

  AdminApi? _api;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _notesCtrl.dispose();
    for (final l in _lines) l.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    final session = await SessionStore.load();
    if (session == null) { if (mounted) Navigator.of(context).pop(); return; }
    _api = AdminApi(session.baseUrl, session.token);
    try {
      final suppliers = await _api!.getSuppliers();
      if (!mounted) return;
      setState(() {
        _suppliers = suppliers.where((s) => s.status == 'active').toList();
      });

      final existing = widget.existingPo;
      if (existing != null) {
        _notesCtrl.text = existing.notes ?? '';
        if (existing.expectedDeliveryDate != null) {
          try { _deliveryDate = DateTime.parse(existing.expectedDeliveryDate!); } catch (_) {}
        }
        try {
          _selectedSupplier = _suppliers.firstWhere((s) => s.id == existing.supplierId);
        } catch (_) {}
        for (final line in existing.lines) {
          _lines.add(_LineItemState(
            productId: line.productId,
            productName: line.productName,
            productSku: line.productSku,
            quantity: line.quantityOrdered,
            unitCostCents: line.unitCostCents,
          ));
        }
      }

      if (_lines.isEmpty) _lines.add(_LineItemState());
      setState(() => _loadingInit = false);
    } catch (_) {
      if (mounted) setState(() { _error = 'Failed to load suppliers'; _loadingInit = false; });
    }
  }

  Future<void> _pickDeliveryDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _deliveryDate ?? DateTime.now().add(const Duration(days: 7)),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null && mounted) setState(() => _deliveryDate = picked);
  }

  Future<void> _pickProduct(int lineIndex) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => _ProductPickerDialog(api: _api!),
    );
    if (result == null || !mounted) return;
    setState(() {
      _lines[lineIndex].productId = result['id'] as String;
      _lines[lineIndex].productName = result['name'] as String? ?? '';
      _lines[lineIndex].productSku = result['sku'] as String? ?? '';
    });
  }

  bool get _canSave {
    if (_selectedSupplier == null) return false;
    return _lines.any((l) => l.isValid);
  }

  Future<void> _save() async {
    if (!_canSave || _api == null) return;
    setState(() { _saving = true; _error = null; });
    try {
      final deliveryIso = _deliveryDate?.toUtc().toIso8601String();
      final existing = widget.existingPo;

      if (existing == null) {
        // Create new PO
        final po = await _api!.createPurchaseOrder(
          supplierId: _selectedSupplier!.id,
          notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
          expectedDeliveryDate: deliveryIso,
        );
        // Add lines
        for (final line in _lines) {
          if (!line.isValid) continue;
          await _api!.addPOLine(po.id,
            productId: line.productId!,
            quantity: line.qty,
            unitCostCents: line.costCents,
          );
        }
      } else {
        // Update existing draft PO header
        await _api!.updatePurchaseOrder(existing.id,
          notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
          expectedDeliveryDate: deliveryIso,
        );
        // Delete old lines and re-add (simplest approach for draft editing)
        for (final oldLine in existing.lines) {
          await _api!.deletePOLine(existing.id, oldLine.id);
        }
        for (final line in _lines) {
          if (!line.isValid) continue;
          await _api!.addPOLine(existing.id,
            productId: line.productId!,
            quantity: line.qty,
            unitCostCents: line.costCents,
          );
        }
      }

      if (!mounted) return;
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      if (mounted) setState(() { _error = 'Failed to save (${e.statusCode})'; _saving = false; });
    } catch (_) {
      if (mounted) setState(() { _error = 'Connection error'; _saving = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isEdit = widget.existingPo != null;

    return Scaffold(
      appBar: AppBar(
        title: Text(isEdit ? 'Edit Purchase Order' : 'New Purchase Order'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.all(16),
              child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
            )
          else
            TextButton(
              onPressed: _canSave ? _save : null,
              child: const Text('Save'),
            ),
        ],
      ),
      body: _loadingInit
          ? const Center(child: CircularProgressIndicator())
          : _error != null && _suppliers.isEmpty
              ? Center(child: Text(_error!))
              : ListView(
                  padding: const EdgeInsets.all(AdminSpacing.gutter),
                  children: [
                    // Supplier dropdown
                    DropdownButtonFormField<Supplier>(
                      value: _selectedSupplier,
                      decoration: const InputDecoration(
                        labelText: 'Supplier *',
                        border: OutlineInputBorder(),
                      ),
                      items: _suppliers.map((s) => DropdownMenuItem(
                        value: s,
                        child: Text(s.name),
                      )).toList(),
                      onChanged: isEdit
                          ? null  // cannot change supplier on edit
                          : (s) => setState(() => _selectedSupplier = s),
                    ),
                    const SizedBox(height: AdminSpacing.md),

                    // Expected delivery date
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        _deliveryDate != null
                            ? 'Delivery: ${DateFormat('MMM d, y').format(_deliveryDate!)}'
                            : 'Expected delivery date (optional)',
                        style: theme.textTheme.bodyMedium,
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (_deliveryDate != null)
                            IconButton(
                              onPressed: () => setState(() => _deliveryDate = null),
                              icon: const Icon(Icons.close_rounded),
                              tooltip: 'Clear date',
                            ),
                          IconButton(
                            onPressed: _pickDeliveryDate,
                            icon: const Icon(Icons.calendar_today_outlined),
                            tooltip: 'Pick date',
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: AdminSpacing.md),

                    // Notes
                    TextField(
                      controller: _notesCtrl,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        labelText: 'Notes (optional)',
                        border: OutlineInputBorder(),
                        alignLabelWithHint: true,
                      ),
                    ),
                    const SizedBox(height: AdminSpacing.xl),

                    // Line items
                    Row(
                      children: [
                        Text('Line Items', style: theme.textTheme.titleMedium),
                        const Spacer(),
                        TextButton.icon(
                          onPressed: () => setState(() => _lines.add(_LineItemState())),
                          icon: const Icon(Icons.add_rounded, size: 18),
                          label: const Text('Add item'),
                        ),
                      ],
                    ),
                    const SizedBox(height: AdminSpacing.sm),

                    ..._lines.asMap().entries.map((entry) {
                      final i = entry.key;
                      final line = entry.value;
                      return Padding(
                        padding: const EdgeInsets.only(bottom: AdminSpacing.md),
                        child: Material(
                          color: AdminColors.surfaceContainerLow,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                          child: Padding(
                            padding: const EdgeInsets.all(AdminSpacing.md),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: GestureDetector(
                                        onTap: () => _pickProduct(i),
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 12, vertical: 14,
                                          ),
                                          decoration: BoxDecoration(
                                            border: Border.all(color: AdminColors.outlineVariant),
                                            borderRadius: BorderRadius.circular(8),
                                            color: AdminColors.card,
                                          ),
                                          child: Text(
                                            line.productName ?? 'Tap to select product',
                                            style: theme.textTheme.bodyMedium?.copyWith(
                                              color: line.productName != null
                                                  ? AdminColors.onSurface
                                                  : AdminColors.onSurfaceVariant,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ),
                                    if (_lines.length > 1) ...[
                                      const SizedBox(width: AdminSpacing.xs),
                                      IconButton(
                                        onPressed: () => setState(() { line.dispose(); _lines.removeAt(i); }),
                                        icon: const Icon(Icons.delete_outline_rounded),
                                        color: AdminColors.onSurfaceVariant,
                                        tooltip: 'Remove line',
                                      ),
                                    ],
                                  ],
                                ),
                                const SizedBox(height: AdminSpacing.sm),
                                Row(
                                  children: [
                                    Expanded(
                                      child: TextField(
                                        controller: line.qtyCtrl,
                                        keyboardType: TextInputType.number,
                                        decoration: const InputDecoration(
                                          labelText: 'Qty',
                                          border: OutlineInputBorder(),
                                        ),
                                        onChanged: (_) => setState(() {}),
                                      ),
                                    ),
                                    const SizedBox(width: AdminSpacing.sm),
                                    Expanded(
                                      flex: 2,
                                      child: TextField(
                                        controller: line.costCtrl,
                                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                        decoration: const InputDecoration(
                                          labelText: 'Unit cost',
                                          border: OutlineInputBorder(),
                                        ),
                                        onChanged: (_) => setState(() {}),
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    }),

                    if (_error != null) ...[
                      const SizedBox(height: AdminSpacing.md),
                      Text(_error!, style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.error)),
                    ],
                    const SizedBox(height: 80),
                  ],
                ),
    );
  }
}

class _ProductPickerDialog extends StatefulWidget {
  const _ProductPickerDialog({required this.api});
  final AdminApi api;

  @override
  State<_ProductPickerDialog> createState() => _ProductPickerDialogState();
}

class _ProductPickerDialogState extends State<_ProductPickerDialog> {
  final _ctrl = TextEditingController();
  List<Map<String, dynamic>> _results = [];
  bool _searching = false;
  Timer? _debounce;

  @override
  void dispose() {
    _ctrl.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  void _onChanged(String q) {
    _debounce?.cancel();
    if (q.length < 2) { setState(() => _results = []); return; }
    _debounce = Timer(const Duration(milliseconds: 350), () async {
      setState(() => _searching = true);
      try {
        final results = await widget.api.searchProducts(q);
        if (mounted) setState(() { _results = results; _searching = false; });
      } catch (_) {
        if (mounted) setState(() => _searching = false);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Select Product'),
      content: SizedBox(
        width: double.maxFinite,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _ctrl,
              autofocus: true,
              decoration: const InputDecoration(
                hintText: 'Search by name or SKU...',
                prefixIcon: Icon(Icons.search_rounded),
                border: OutlineInputBorder(),
              ),
              onChanged: _onChanged,
            ),
            const SizedBox(height: 8),
            if (_searching)
              const Padding(padding: EdgeInsets.all(16), child: CircularProgressIndicator())
            else if (_results.isEmpty && _ctrl.text.length >= 2)
              const Padding(padding: EdgeInsets.all(16), child: Text('No products found'))
            else
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: _results.length,
                  itemBuilder: (_, i) {
                    final p = _results[i];
                    return ListTile(
                      title: Text(p['name'] as String? ?? ''),
                      subtitle: Text(p['sku'] as String? ?? ''),
                      onTap: () => Navigator.of(context).pop(p),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
      ],
    );
  }
}
```

- [ ] **Step 7.2: Verify analyze**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze lib/screens/create_edit_purchase_order_screen.dart
```

Expected: `No issues found!`

- [ ] **Step 7.3: Commit**

```bash
git add apps/admin_mobile/lib/screens/create_edit_purchase_order_screen.dart
git commit -m "feat(admin-mobile): add Purchase Order create/edit screen"
```

---

## Task 8: Purchase Orders — Detail Screen

**Files:**
- Create: `apps/admin_mobile/lib/screens/purchase_order_detail_screen.dart`

- [ ] **Step 8.1: Create `lib/screens/purchase_order_detail_screen.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../admin_tokens.dart';
import '../models/currency.dart';
import '../models/purchase_order.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import 'create_edit_purchase_order_screen.dart';

class PurchaseOrderDetailScreen extends StatefulWidget {
  const PurchaseOrderDetailScreen({super.key, required this.poId});
  final String poId;

  @override
  State<PurchaseOrderDetailScreen> createState() => _PurchaseOrderDetailScreenState();
}

class _PurchaseOrderDetailScreenState extends State<PurchaseOrderDetailScreen> {
  bool _loading = true;
  bool _acting = false;
  String? _error;
  PurchaseOrder? _po;
  AdminApi? _api;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { Navigator.of(context).pop(); return; }
      _api = AdminApi(session.baseUrl, session.token);
      final po = await _api!.getPurchaseOrder(widget.poId);
      if (!mounted) return;
      setState(() { _po = po; _loading = false; });
    } on ApiException catch (e) {
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (_) {
      if (mounted) setState(() { _error = 'Connection error'; _loading = false; });
    }
  }

  Future<void> _transition(String newStatus) async {
    final confirmed = newStatus == 'cancelled'
        ? await showDialog<bool>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('Cancel purchase order'),
              content: const Text('This cannot be undone. Are you sure?'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('No')),
                FilledButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  style: FilledButton.styleFrom(backgroundColor: AdminColors.error),
                  child: const Text('Cancel PO'),
                ),
              ],
            ),
          )
        : true;
    if (confirmed != true || _api == null) return;
    setState(() => _acting = true);
    try {
      await _api!.updatePurchaseOrder(widget.poId, status: newStatus);
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _acting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed (${e.statusCode})')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final currency = context.watch<CurrencyModel>();
    final po = _po;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Purchase Order'),
        actions: [
          if (po?.status == 'draft')
            IconButton(
              onPressed: () async {
                await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => CreateEditPurchaseOrderScreen(existingPo: po),
                ));
                _load();
              },
              icon: const Icon(Icons.edit_outlined),
              tooltip: 'Edit',
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.cloud_off_rounded, size: 48, color: AdminColors.onSurfaceVariant),
                      const SizedBox(height: 12),
                      Text(_error!, textAlign: TextAlign.center),
                      const SizedBox(height: 16),
                      FilledButton.icon(onPressed: _load,
                        icon: const Icon(Icons.refresh_rounded), label: const Text('Retry')),
                    ],
                  ),
                )
              : po == null
                  ? const SizedBox.shrink()
                  : Column(
                      children: [
                        Expanded(
                          child: ListView(
                            padding: const EdgeInsets.all(AdminSpacing.gutter),
                            children: [
                              // Header card
                              Material(
                                color: AdminColors.card,
                                borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                                child: Padding(
                                  padding: const EdgeInsets.all(AdminSpacing.md),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(po.supplierName,
                                              style: theme.textTheme.titleLarge?.copyWith(
                                                fontWeight: FontWeight.bold,
                                              )),
                                          _StatusBadge(status: po.status),
                                        ],
                                      ),
                                      const SizedBox(height: AdminSpacing.sm),
                                      _InfoRow(
                                        label: 'Created',
                                        value: _fmtDate(po.createdAt),
                                      ),
                                      if (po.expectedDeliveryDate != null)
                                        _InfoRow(
                                          label: 'Expected delivery',
                                          value: _fmtDate(po.expectedDeliveryDate!),
                                        ),
                                      if (po.notes != null && po.notes!.isNotEmpty)
                                        _InfoRow(label: 'Notes', value: po.notes!),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(height: AdminSpacing.lg),

                              // Line items
                              Text('Line Items', style: theme.textTheme.titleMedium),
                              const SizedBox(height: AdminSpacing.sm),
                              Material(
                                color: AdminColors.card,
                                borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                                child: Column(
                                  children: [
                                    ...po.lines.asMap().entries.map((entry) {
                                      final i = entry.key;
                                      final line = entry.value;
                                      final isLast = i == po.lines.length - 1;
                                      return Column(
                                        children: [
                                          Padding(
                                            padding: const EdgeInsets.all(AdminSpacing.md),
                                            child: Row(
                                              children: [
                                                Expanded(
                                                  child: Column(
                                                    crossAxisAlignment: CrossAxisAlignment.start,
                                                    children: [
                                                      Text(line.productName,
                                                          style: theme.textTheme.titleMedium),
                                                      Text(
                                                        '${line.productSku} · ${line.quantityOrdered} × ${currency.format(line.unitCostCents)}',
                                                        style: theme.textTheme.bodySmall?.copyWith(
                                                          color: AdminColors.onSurfaceVariant,
                                                        ),
                                                      ),
                                                    ],
                                                  ),
                                                ),
                                                Text(
                                                  currency.format(line.lineTotalCents),
                                                  style: theme.textTheme.titleMedium?.copyWith(
                                                    fontWeight: FontWeight.bold,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                          if (!isLast)
                                            Divider(height: 1, indent: AdminSpacing.md,
                                              endIndent: AdminSpacing.md,
                                              color: AdminColors.outlineVariant.withValues(alpha: 0.4)),
                                        ],
                                      );
                                    }),
                                    // Total row
                                    Divider(height: 1,
                                      color: AdminColors.outlineVariant.withValues(alpha: 0.4)),
                                    Padding(
                                      padding: const EdgeInsets.all(AdminSpacing.md),
                                      child: Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text('Total',
                                              style: theme.textTheme.titleMedium?.copyWith(
                                                fontWeight: FontWeight.bold,
                                              )),
                                          Text(
                                            currency.format(po.totalCents),
                                            style: theme.textTheme.titleLarge?.copyWith(
                                              fontWeight: FontWeight.bold,
                                              color: AdminColors.primary,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 100),
                            ],
                          ),
                        ),

                        // Status action bar
                        if (po.status == 'draft' || po.status == 'ordered')
                          SafeArea(
                            child: Padding(
                              padding: const EdgeInsets.all(AdminSpacing.gutter),
                              child: _acting
                                  ? const Center(child: CircularProgressIndicator())
                                  : Row(
                                      children: [
                                        Expanded(
                                          child: OutlinedButton(
                                            onPressed: () => _transition('cancelled'),
                                            style: OutlinedButton.styleFrom(
                                              foregroundColor: AdminColors.error,
                                              side: BorderSide(color: AdminColors.error),
                                              minimumSize: const Size(0, 48),
                                            ),
                                            child: const Text('Cancel PO'),
                                          ),
                                        ),
                                        const SizedBox(width: AdminSpacing.md),
                                        Expanded(
                                          flex: 2,
                                          child: FilledButton(
                                            onPressed: () => _transition(
                                              po.status == 'draft' ? 'ordered' : 'received',
                                            ),
                                            style: FilledButton.styleFrom(
                                              minimumSize: const Size(0, 48),
                                            ),
                                            child: Text(
                                              po.status == 'draft'
                                                  ? 'Mark as Ordered'
                                                  : 'Mark as Received',
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                            ),
                          ),
                      ],
                    ),
    );
  }

  static String _fmtDate(String iso) {
    try { return DateFormat('MMM d, y').format(DateTime.parse(iso).toLocal()); }
    catch (_) { return iso; }
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final String status;

  Color get _fg {
    switch (status) {
      case 'ordered': return AdminColors.primary;
      case 'received': return const Color(0xFF1A6B3C);
      case 'cancelled': return AdminColors.onErrorContainer;
      default: return AdminColors.onSurfaceVariant;
    }
  }

  Color get _bg {
    switch (status) {
      case 'ordered': return AdminColors.primaryContainer.withValues(alpha: 0.15);
      case 'received': return const Color(0xFFD6F0E3);
      case 'cancelled': return AdminColors.errorContainer;
      default: return AdminColors.surfaceContainerHigh;
    }
  }

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
    decoration: BoxDecoration(color: _bg, borderRadius: BorderRadius.circular(20)),
    child: Text(
      status[0].toUpperCase() + status.substring(1),
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
        color: _fg, fontWeight: FontWeight.w700,
      ),
    ),
  );
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: AdminSpacing.xs),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 130,
          child: Text(label,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: AdminColors.onSurfaceVariant,
            )),
        ),
        Expanded(child: Text(value, style: Theme.of(context).textTheme.bodySmall)),
      ],
    ),
  );
}
```

- [ ] **Step 8.2: Verify analyze**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze lib/screens/purchase_order_detail_screen.dart
```

Expected: `No issues found!`

- [ ] **Step 8.3: Commit**

```bash
git add apps/admin_mobile/lib/screens/purchase_order_detail_screen.dart
git commit -m "feat(admin-mobile): add Purchase Order detail screen with status transitions"
```

---

## Task 9: Analytics Overhaul + Heatmap Widget

Add payment methods, hourly heatmap, and shop revenue sections to the analytics screen. Add the revenue delta badge (already wired — just needs the `trend` prop to not be hidden). Create the `HourlyHeatmapWidget`.

**Files:**
- Create: `apps/admin_mobile/lib/widgets/hourly_heatmap_widget.dart`
- Modify: `apps/admin_mobile/lib/screens/analytics_screen.dart`

- [ ] **Step 9.1: Create `lib/widgets/hourly_heatmap_widget.dart`**

```dart
import 'package:flutter/material.dart';

import '../admin_tokens.dart';
import '../models/analytics.dart';

class HourlyHeatmapWidget extends StatefulWidget {
  const HourlyHeatmapWidget({
    super.key,
    required this.buckets,
    required this.formatValue,
  });

  final List<HeatmapBucket> buckets;
  final String Function(int cents) formatValue;

  @override
  State<HourlyHeatmapWidget> createState() => _HourlyHeatmapWidgetState();
}

class _HourlyHeatmapWidgetState extends State<HourlyHeatmapWidget> {
  int? _selectedHour;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final buckets = widget.buckets;

    if (buckets.isEmpty) {
      return SizedBox(
        height: 60,
        child: Center(
          child: Text(
            'No data',
            style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant),
          ),
        ),
      );
    }

    final maxCents = buckets.map((b) => b.avgGrossCents).fold(0, (a, b) => a > b ? a : b);

    HeatmapBucket? selectedBucket;
    if (_selectedHour != null) {
      try {
        selectedBucket = buckets.firstWhere((b) => b.hour == _selectedHour);
      } catch (_) {}
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (selectedBucket != null)
          Padding(
            padding: const EdgeInsets.only(bottom: AdminSpacing.sm),
            child: Text(
              '${_selectedHour.toString().padLeft(2, '0')}:00 · avg ${widget.formatValue(selectedBucket.avgGrossCents)} · ${selectedBucket.avgTxCount.toStringAsFixed(1)} txns',
              style: theme.textTheme.bodySmall?.copyWith(
                color: AdminColors.primary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        SizedBox(
          height: 52,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: 24,
            separatorBuilder: (_, __) => const SizedBox(width: 3),
            itemBuilder: (context, hour) {
              HeatmapBucket? bucket;
              try { bucket = buckets.firstWhere((b) => b.hour == hour); } catch (_) {}
              final cents = bucket?.avgGrossCents ?? 0;
              final intensity = maxCents > 0 ? cents / maxCents : 0.0;
              final isSelected = _selectedHour == hour;
              final hasData = cents > 0;

              return GestureDetector(
                onTap: () => setState(
                  () => _selectedHour = isSelected ? null : hour,
                ),
                child: Container(
                  width: 26,
                  decoration: BoxDecoration(
                    color: hasData
                        ? AdminColors.primary.withValues(alpha: 0.10 + 0.75 * intensity)
                        : AdminColors.surfaceContainerHigh,
                    borderRadius: BorderRadius.circular(4),
                    border: isSelected
                        ? Border.all(color: AdminColors.primary, width: 2)
                        : null,
                  ),
                  child: Center(
                    child: Text(
                      '$hour',
                      style: TextStyle(
                        fontSize: 9,
                        fontWeight: FontWeight.w600,
                        color: intensity > 0.55
                            ? Colors.white
                            : AdminColors.onSurfaceVariant,
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Text(
            'Tap a block to see details · hours 00–23',
            style: theme.textTheme.labelSmall?.copyWith(
              color: AdminColors.onSurfaceVariant,
            ),
          ),
        ),
      ],
    );
  }
}
```

- [ ] **Step 9.2: Modify `lib/screens/analytics_screen.dart` — add state variables and load calls**

Add state variables after the existing `List<TopProduct> _topProducts = [];` line:

```dart
  List<PaymentMethod> _paymentMethods = [];
  List<HeatmapBucket> _heatmap = [];
  List<ShopRevenue> _shopRevenue = [];
```

Replace the `Future.wait` in `_load` with this expanded version:

```dart
      final results = await Future.wait([
        api.getAnalyticsSummary(days: _days),
        api.getSalesSeries(days: _days),
        api.getCategoryRevenue(days: _days),
        api.getTopProducts(days: _days, limit: 5),
        api.getPaymentMethods(_days),
        api.getHourlyHeatmap(_days),
        api.getShopRevenue(_days),
      ]);
      if (!mounted) return;
      setState(() {
        _summary = results[0] as AnalyticsSummary;
        _series = (results[1] as List).cast<SalesPoint>();
        _categories = (results[2] as List).cast<CategoryItem>();
        _topProducts = (results[3] as List).cast<TopProduct>();
        _paymentMethods = (results[4] as List).cast<PaymentMethod>();
        _heatmap = (results[5] as List).cast<HeatmapBucket>();
        _shopRevenue = (results[6] as List).cast<ShopRevenue>();
        _loading = false;
      });
```

- [ ] **Step 9.3: Add three new sections to `analytics_screen.dart` build method**

After the existing top products `SliverPadding` block (the one with `SliverToBoxAdapter` and "Best sellers"), add three new `SliverPadding` blocks. These go inside the `else ...[` spread, after the top products section. Find the closing `],` of the top products sliver and append:

```dart
              // Payment methods
              if (_paymentMethods.isNotEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(
                    AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, 0,
                  ),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SectionHeader(label: 'How customers pay', title: 'Payment Methods'),
                        const SizedBox(height: AdminSpacing.md),
                        Material(
                          color: AdminColors.card,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                          child: Column(
                            children: _paymentMethods.asMap().entries.map((entry) {
                              final i = entry.key;
                              final pm = entry.value;
                              final isLast = i == _paymentMethods.length - 1;
                              IconData icon;
                              switch (pm.tenderType.toLowerCase()) {
                                case 'cash': icon = Icons.money_rounded; break;
                                case 'card': icon = Icons.credit_card_rounded; break;
                                default: icon = Icons.payment_rounded;
                              }
                              return Column(
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: AdminSpacing.md, vertical: AdminSpacing.sm,
                                    ),
                                    child: Row(
                                      children: [
                                        Icon(icon, size: 20, color: AdminColors.primary),
                                        const SizedBox(width: AdminSpacing.sm),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                pm.tenderType[0].toUpperCase() + pm.tenderType.substring(1),
                                                style: theme.textTheme.titleMedium,
                                              ),
                                              Text(
                                                '${pm.transactionCount} transactions · ${pm.pct.toStringAsFixed(1)}%',
                                                style: theme.textTheme.bodySmall?.copyWith(
                                                  color: AdminColors.onSurfaceVariant,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        Text(
                                          currency.formatAbbreviated(pm.grossCents),
                                          style: theme.textTheme.titleMedium?.copyWith(
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  if (!isLast)
                                    Divider(height: 1, indent: AdminSpacing.md, endIndent: AdminSpacing.md,
                                      color: AdminColors.outlineVariant.withValues(alpha: 0.4)),
                                ],
                              );
                            }).toList(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

              // Hourly heatmap
              if (_heatmap.isNotEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(
                    AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, 0,
                  ),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SectionHeader(label: 'Busiest times', title: 'Peak Hours'),
                        const SizedBox(height: AdminSpacing.md),
                        Material(
                          color: AdminColors.card,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                          child: Padding(
                            padding: const EdgeInsets.all(AdminSpacing.md),
                            child: HourlyHeatmapWidget(
                              buckets: _heatmap,
                              formatValue: currency.formatAbbreviated,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

              // Shop revenue (multi-shop only)
              if (_shopRevenue.length > 1)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(
                    AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, AdminSpacing.xl,
                  ),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SectionHeader(label: 'By location', title: 'Shop Revenue'),
                        const SizedBox(height: AdminSpacing.md),
                        Material(
                          color: AdminColors.card,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                          child: Column(
                            children: _shopRevenue.asMap().entries.map((entry) {
                              final i = entry.key;
                              final shop = entry.value;
                              final isLast = i == _shopRevenue.length - 1;
                              return Column(
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: AdminSpacing.md, vertical: AdminSpacing.sm,
                                    ),
                                    child: Row(
                                      children: [
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(shop.shopName, style: theme.textTheme.titleMedium),
                                              Text(
                                                '${shop.transactionCount} transactions · ${shop.pct.toStringAsFixed(1)}%',
                                                style: theme.textTheme.bodySmall?.copyWith(
                                                  color: AdminColors.onSurfaceVariant,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        Text(
                                          currency.formatAbbreviated(shop.grossCents),
                                          style: theme.textTheme.titleMedium?.copyWith(
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  if (!isLast)
                                    Divider(height: 1, indent: AdminSpacing.md, endIndent: AdminSpacing.md,
                                      color: AdminColors.outlineVariant.withValues(alpha: 0.4)),
                                ],
                              );
                            }).toList(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
```

- [ ] **Step 9.4: Add missing imports to `analytics_screen.dart`**

Add at the top of the file, after existing imports:

```dart
import '../widgets/hourly_heatmap_widget.dart';
```

- [ ] **Step 9.5: Verify analyze**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze lib/screens/analytics_screen.dart lib/widgets/hourly_heatmap_widget.dart
```

Expected: `No issues found!`

- [ ] **Step 9.6: Commit**

```bash
git add apps/admin_mobile/lib/widgets/hourly_heatmap_widget.dart \
        apps/admin_mobile/lib/screens/analytics_screen.dart
git commit -m "feat(admin-mobile): add payment methods, peak hours, and shop revenue to analytics"
```

---

## Task 10: App Shell + Home Screen Overhaul

Wire up the new Purchases tab, fix the home screen KPIs and chart, update quick actions, and add stock alerts navigation.

**Files:**
- Modify: `apps/admin_mobile/lib/screens/app_shell.dart`
- Modify: `apps/admin_mobile/lib/screens/home_screen.dart`

- [ ] **Step 10.1: Rewrite `lib/screens/app_shell.dart`**

Replace the file contents entirely:

```dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../admin_tokens.dart';
import '../models/session.dart';
import '../services/session_store.dart';
import 'analytics_screen.dart';
import 'home_screen.dart';
import 'purchase_orders_screen.dart';
import 'staff_screen.dart';

class AppShellModel extends ChangeNotifier {
  int _index = 0;
  int get index => _index;

  void setIndex(int i) {
    if (_index == i) return;
    _index = i;
    notifyListeners();
  }
}

class _TabDef {
  const _TabDef({
    required this.label,
    required this.icon,
    required this.selectedIcon,
    required this.buildScreen,
    this.permission,
  });

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final Widget Function(VoidCallback onLogout) buildScreen;
  final String? permission;
}

final _allTabs = [
  _TabDef(
    label: 'Home',
    icon: Icons.home_outlined,
    selectedIcon: Icons.home_rounded,
    buildScreen: (onLogout) => HomeScreen(onNavigateToPurchases: () {}, onLogout: onLogout),
    permission: null,
  ),
  _TabDef(
    label: 'Purchases',
    icon: Icons.shopping_bag_outlined,
    selectedIcon: Icons.shopping_bag_rounded,
    buildScreen: (onLogout) => PurchaseOrdersScreen(onLogout: onLogout),
    permission: 'procurement:read',
  ),
  _TabDef(
    label: 'Staff',
    icon: Icons.people_outlined,
    selectedIcon: Icons.people_rounded,
    buildScreen: (onLogout) => StaffScreen(onLogout: onLogout),
    permission: 'staff:read',
  ),
  _TabDef(
    label: 'Analytics',
    icon: Icons.bar_chart_outlined,
    selectedIcon: Icons.bar_chart_rounded,
    buildScreen: (onLogout) => AnalyticsScreen(onLogout: onLogout),
    permission: 'analytics:read',
  ),
];

class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.session, required this.onLogout});

  final AdminSession session;
  final VoidCallback onLogout;

  Future<void> _logout(BuildContext context) async {
    await SessionStore.clearLogin();
    onLogout();
  }

  @override
  Widget build(BuildContext context) {
    final model = context.watch<AppShellModel>();

    final visibleTabs = _allTabs.where((tab) {
      if (tab.permission == null) return true;
      if (session.permissions.isEmpty) return true;
      return session.hasPermission(tab.permission!);
    }).toList();

    final safeIndex = model.index.clamp(0, visibleTabs.length - 1);

    void onLogoutCallback() => _logout(context);

    void navigateTo(String permission) {
      final idx = visibleTabs.indexWhere((t) => t.permission == permission);
      if (idx >= 0) context.read<AppShellModel>().setIndex(idx);
    }

    return Scaffold(
      body: IndexedStack(
        index: safeIndex,
        children: visibleTabs.map((tab) {
          if (tab.label == 'Home') {
            return HomeScreen(
              onNavigateToPurchases: () => navigateTo('procurement:read'),
              onLogout: onLogoutCallback,
            );
          }
          return tab.buildScreen(onLogoutCallback);
        }).toList(),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: safeIndex,
        onDestinationSelected: (i) => context.read<AppShellModel>().setIndex(i),
        destinations: visibleTabs
            .map((tab) => NavigationDestination(
                  icon: Icon(tab.icon),
                  selectedIcon: Icon(tab.selectedIcon),
                  label: tab.label,
                ))
            .toList(),
      ),
    );
  }
}

Future<void> showLogoutDialog(BuildContext context, VoidCallback onLogout) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Sign out'),
      content: const Text('Are you sure you want to sign out?'),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          style: FilledButton.styleFrom(
            backgroundColor: AdminColors.error,
            minimumSize: const Size(0, 44),
          ),
          child: const Text('Sign out'),
        ),
      ],
    ),
  );
  if (confirmed == true) onLogout();
}
```

- [ ] **Step 10.2: Rewrite the data-loading section of `lib/screens/home_screen.dart`**

Update the `HomeScreen` constructor to remove `onNavigateToStaff` and `onNavigateToOrders`, replacing them with `onNavigateToPurchases`:

```dart
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.onNavigateToPurchases,
    required this.onLogout,
  });

  final VoidCallback onNavigateToPurchases;
  final VoidCallback onLogout;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}
```

Update `_load` in `_HomeScreenState` — change `days: 1` to `days: 7` on both API calls and remove `getEmployees()` from the parallel load (Active Staff KPI is replaced by Pending POs):

```dart
  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { widget.onLogout(); return; }
      _email = session.email;
      final api = AdminApi(session.baseUrl, session.token);
      final results = await Future.wait([
        api.getAnalyticsSummary(days: 7),
        api.getSalesSeries(days: 7),
      ]);
      if (!mounted) return;
      setState(() {
        _summary = results[0] as AnalyticsSummary;
        _series = (results[1] as List).cast<SalesPoint>();
        _loading = false;
      });
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        await SessionStore.clearLogin();
        if (mounted) widget.onLogout();
        return;
      }
      if (mounted) setState(() { _error = 'Failed to load data (${e.statusCode})'; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = 'Connection error. Pull to refresh.'; _loading = false; });
    }
  }
```

Also remove the `_activeStaff` state variable and `getEmployees` import if present.

- [ ] **Step 10.3: Update the KPI grid and quick actions in `home_screen.dart`**

Replace the KPI grid children (the `children:` list inside `SliverGrid.count`):

```dart
                  children: [
                    AdminMetricCard(
                      title: 'Revenue (7d)',
                      value: summary != null ? currency.formatAbbreviated(summary.grossCents) : '--',
                      icon: Icons.attach_money_rounded,
                      trend: summary != null && summary.deltaPct != null
                          ? _formatDelta(summary.deltaPct)
                          : null,
                      trendPositive: summary != null && (summary.deltaPct ?? 0) >= 0,
                    ),
                    AdminMetricCard(
                      title: 'Transactions (7d)',
                      value: summary != null ? '${summary.transactionCount}' : '--',
                      icon: Icons.swap_horiz_rounded,
                    ),
                    AdminMetricCard(
                      title: 'Pending POs',
                      value: summary != null ? '${summary.pendingOrderCount}' : '--',
                      icon: Icons.shopping_bag_outlined,
                      onTap: widget.onNavigateToPurchases,
                    ),
                    AdminMetricCard(
                      title: 'Stock Alerts',
                      value: summary != null ? '${summary.stockAlertCount}' : '--',
                      icon: Icons.warning_amber_rounded,
                      trendPositive: summary != null && summary.stockAlertCount == 0,
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const StockAlertsScreen()),
                      ),
                    ),
                  ],
```

Replace the section header label for the chart (change `'Today'` to `'Last 7 days'`):

```dart
                      const SectionHeader(
                        label: 'Last 7 days',
                        title: 'Revenue Trend',
                      ),
```

Replace the quick actions section (2 tiles instead of 3):

```dart
                      _QuickActionTile(
                        icon: Icons.shopping_bag_outlined,
                        title: 'Purchase Orders',
                        subtitle: summary != null && summary.pendingOrderCount > 0
                            ? '${summary.pendingOrderCount} pending'
                            : 'View and manage orders',
                        onTap: widget.onNavigateToPurchases,
                      ),
                      const SizedBox(height: AdminSpacing.sm),
                      _QuickActionTile(
                        icon: Icons.warning_amber_rounded,
                        title: 'Inventory Alerts',
                        subtitle: summary != null
                            ? '${summary.stockAlertCount} product${summary.stockAlertCount == 1 ? '' : 's'} low on stock'
                            : 'Check stock levels',
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(builder: (_) => const StockAlertsScreen()),
                        ),
                      ),
```

Add the `StockAlertsScreen` import at the top of `home_screen.dart`:

```dart
import 'stock_alerts_screen.dart';
```

- [ ] **Step 10.4: Verify analyze — full app**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze
```

Expected: `No issues found!`

- [ ] **Step 10.5: Commit**

```bash
git add apps/admin_mobile/lib/screens/app_shell.dart \
        apps/admin_mobile/lib/screens/home_screen.dart
git commit -m "feat(admin-mobile): restructure tabs (Purchases replaces Orders), fix home screen KPIs and chart"
```

---

## Task 11: Delete Old Files + Final Verify + Build + Upload

Remove the now-unused orders and transaction files, do a final full analyze, build the APK, and upload it to the platform portal.

**Files:**
- Delete: `apps/admin_mobile/lib/screens/orders_screen.dart`
- Delete: `apps/admin_mobile/lib/screens/order_detail_screen.dart`
- Delete: `apps/admin_mobile/lib/models/transaction.dart`

- [ ] **Step 11.1: Delete old files**

```bash
git rm apps/admin_mobile/lib/screens/orders_screen.dart \
       apps/admin_mobile/lib/screens/order_detail_screen.dart \
       apps/admin_mobile/lib/models/transaction.dart
```

- [ ] **Step 11.2: Full analyze**

```bash
cd apps/admin_mobile
../../tools/flutter/bin/flutter analyze
```

Expected: `No issues found!` — if there are any remaining `orders_screen` or `transaction` imports in other files, remove them now.

- [ ] **Step 11.3: Commit deletion**

```bash
git commit -m "chore(admin-mobile): delete old Orders screens and Transaction model"
```

- [ ] **Step 11.4: Build the release APK**

```bash
cd apps/admin_mobile
ANDROID_HOME=/home/devadmin/tools/android-sdk \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Xmx4g" \
../../tools/flutter/bin/flutter build apk --release 2>&1
```

Expected: `✓ Built build/app/outputs/flutter-apk/app-release.apk`

- [ ] **Step 11.5: Bump version in `pubspec.yaml`**

Change `version: 1.1.0+2` to `version: 1.2.0+3` (this new overhaul release gets version_code 3, so existing 1.1.0 devices detect an update):

```yaml
version: 1.2.0+3
```

Re-run the build after bumping:

```bash
ANDROID_HOME=/home/devadmin/tools/android-sdk \
GRADLE_OPTS="-Dorg.gradle.daemon=false -Xmx4g" \
../../tools/flutter/bin/flutter build apk --release 2>&1
```

- [ ] **Step 11.6: Upload to platform portal**

```bash
TOKEN=$(curl -s -X POST http://localhost:8002/v1/platform/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@platform.ims","password":"admin"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://localhost:8002/v1/platform/releases \
  -H "Authorization: Bearer $TOKEN" \
  -F "app_name=admin_mobile" \
  -F "version=1.2.0" \
  -F "version_code=3" \
  -F "changelog=Major overhaul: Purchase Orders tab, analytics heatmap/payment methods/shop revenue, stock alerts screen, home screen fixes." \
  -F "file=@apps/admin_mobile/build/app/outputs/flutter-apk/app-release.apk" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('uploaded:', d.get('version'), '| active:', d.get('is_active'))"
```

Expected: `uploaded: 1.2.0 | active: True`

- [ ] **Step 11.7: Commit version bump and push**

```bash
git add apps/admin_mobile/pubspec.yaml apps/admin_mobile/pubspec.lock
git commit -m "chore(admin-mobile): bump version to 1.2.0+3 for overhaul release"
git push origin main
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Fix revenue trend "No data" bug | Task 1 (sales-series points/day fix) + Task 10 (days=7) |
| Remove "Onboard New Staff" quick action | Task 10 |
| "View All Orders" → "Purchase Orders" quick action | Task 10 |
| "Inventory Alerts" → navigate to StockAlertsScreen | Task 10 |
| Stock Alerts KPI card tappable | Task 10 |
| Staff: remove Re-enroll Device + Reset Credentials | Task 4 |
| Stock Alerts screen (read-only, severity colours) | Task 5 |
| PO list screen with status filter + FAB | Task 6 |
| PO create screen (supplier, date, notes, dynamic lines, product picker) | Task 7 |
| PO edit screen (pre-populated for draft) | Task 7 |
| PO detail screen with status transitions + edit button | Task 8 |
| Analytics: revenue delta badge | Already wired in existing code — Task 9 step adds 3 new sections only |
| Analytics: payment methods section | Task 9 |
| Analytics: hourly heatmap section + widget | Task 9 |
| Analytics: shop revenue section (multi-shop only) | Task 9 |
| Purchases tab (procurement:read) replacing Orders tab (sales:read) | Task 10 (shell restructure) |
| Delete old orders screens + transaction model | Task 11 |
| Build + upload 1.2.0+3 | Task 11 |

All spec requirements covered. No placeholders. Type names consistent throughout (e.g. `PurchaseOrder`, `StockAlert`, `HeatmapBucket` used identically in model definitions and screen usages).

