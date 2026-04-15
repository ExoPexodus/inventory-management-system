import 'package:flutter/foundation.dart';

import '../config/cashier_timings.dart';
import '../services/authenticated_api.dart';
import '../services/debug_log.dart';
import '../services/inventory_api.dart';
import '../services/outbox_service.dart';
import '../services/session_store.dart';
import 'catalog_model.dart';
import 'sync_state_model.dart';

/// Server-backed product list + policy + display currency from sync pull.
class InventoryFeedModel extends ChangeNotifier {
  List<ProductRow> _products = [];
  String? _policyTier;
  String _currencyCode = 'USD';
  int _currencyExponent = 2;
  String? _currencySymbolOverride;
  int _shopDefaultTaxRateBps = 0;
  bool _loading = true;
  String? _error;
  SessionData? _session;
  bool _employeeDeactivated = false;

  List<ProductRow> get products => List.unmodifiable(_products);
  String? get policyTier => _policyTier;
  bool get employeeDeactivated => _employeeDeactivated;
  String get currencyCode => _currencyCode;
  int get currencyExponent => _currencyExponent;
  String? get currencySymbolOverride => _currencySymbolOverride;
  int get shopDefaultTaxRateBps => _shopDefaultTaxRateBps;
  bool get loading => _loading;
  String? get error => _error;
  SessionData? get session => _session;

  /// Load session from storage only (no network).
  Future<void> hydrateSession() async {
    _session = await SessionStore.load();
    notifyListeners();
  }

  /// Full sync pull; updates [CatalogModel] and storage; flushes outbox.
  Future<void> refresh({
    required AuthenticatedApi auth,
    required SyncStateModel sync,
    required CatalogModel catalog,
  }) async {
    final s = await SessionStore.load();
    _session = s;
    if (s == null) {
      DebugLog.log('SYNC', 'refresh aborted: no session');
      _loading = false;
      notifyListeners();
      return;
    }
    sync.clearTransientFailures();
    _error = null;
    _loading = true;
    notifyListeners();

    DebugLog.log('SYNC', 'pull start base=${s.baseUrl} shop=${s.defaultShopId}');
    try {
      final data = await auth.run((api, session) => api.syncPull(
            accessToken: session.accessToken,
            shopId: session.defaultShopId,
          ));
      DebugLog.log('SYNC', 'pull ok');
      // Keep _session in sync in case auth.run refreshed tokens mid-call.
      _session = await SessionStore.load();
      final products = (data['products'] as List<dynamic>).cast<Map<String, dynamic>>();
      final snaps = (data['stock_snapshots'] as List<dynamic>).cast<Map<String, dynamic>>();
      final qtyByProduct = <String, int>{};
      for (final sn in snaps) {
        qtyByProduct[sn['product_id'] as String] = sn['quantity'] as int;
      }
      final rows = <ProductRow>[];
      for (final p in products) {
        final id = p['id'] as String;
        rows.add(ProductRow.merged(p, qtyByProduct[id] ?? 0));
      }
      final policy = data['policy'] as Map<String, dynamic>?;
      final currency = data['currency'] as Map<String, dynamic>?;
      final employeeActive = data['employee_active'] as bool?;
      _products = rows;
      _policyTier = policy?['tier'] as String?;
      _currencyCode = (currency?['code'] as String?) ?? 'USD';
      _currencyExponent = (currency?['exponent'] as int?) ?? 2;
      _currencySymbolOverride = currency?['symbol_override'] as String?;
      _shopDefaultTaxRateBps = (data['shop_default_tax_rate_bps'] as num?)?.toInt() ?? 0;
      // employeeActive == false means the linked employee was deactivated in admin.
      _employeeDeactivated = employeeActive == false;
      _loading = false;
      notifyListeners();

      await SessionStore.setLastSyncNow();
      // Persist policy limits so the app can enforce them after a cold start.
      final maxOffline = (policy?['max_offline_minutes'] as num?)?.toInt() ??
          CashierTimings.defaultOfflineLimitMinutes;
      final sessionTimeout = (policy?['employee_session_timeout_minutes'] as num?)?.toInt() ??
          CashierTimings.defaultSessionTimeoutMinutes;
      await SessionStore.saveMaxOfflineMinutes(maxOffline);
      await SessionStore.saveSessionTimeoutMinutes(sessionTimeout);
      await SessionStore.setCurrency(
        code: _currencyCode,
        exponent: _currencyExponent,
        symbolOverride: _currencySymbolOverride,
      );
      catalog.applyFromProducts(rows);
      await sync.refreshFromStorage();
      await OutboxService.flush(auth, sync);
    } catch (e, st) {
      DebugLog.log('SYNC', 'refresh error: $e');
      debugPrint('$st');
      _error = e.toString();
      _loading = false;
      notifyListeners();
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  void resetForLogout() {
    _products = [];
    _policyTier = null;
    _currencyCode = 'USD';
    _currencyExponent = 2;
    _currencySymbolOverride = null;
    _shopDefaultTaxRateBps = 0;
    _loading = false;
    _error = null;
    _session = null;
    _employeeDeactivated = false;
    notifyListeners();
  }
}
