import 'package:flutter/foundation.dart';

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

  List<ProductRow> get products => List.unmodifiable(_products);
  String? get policyTier => _policyTier;
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
    required SyncStateModel sync,
    required CatalogModel catalog,
  }) async {
    final s = await SessionStore.load();
    _session = s;
    if (s == null) {
      _loading = false;
      notifyListeners();
      return;
    }
    sync.clearTransientFailures();
    _error = null;
    _loading = true;
    notifyListeners();

    try {
      final api = InventoryApi(s.baseUrl);
      Map<String, dynamic> data;
      try {
        data = await api.syncPull(
          accessToken: s.accessToken,
          shopId: s.defaultShopId,
        );
      } on ApiException catch (e) {
        if (e.statusCode == 401) {
          final body = await api.refresh(refreshToken: s.refreshToken);
          await SessionStore.save(
            baseUrl: s.baseUrl,
            accessToken: body['access_token'] as String,
            refreshToken: body['refresh_token'] as String,
            tenantId: body['tenant_id'] as String,
            shopIds: (body['shop_ids'] as List<dynamic>).map((x) => x.toString()).toList(),
          );
          _session = await SessionStore.load();
          final s2 = _session!;
          data = await api.syncPull(
            accessToken: s2.accessToken,
            shopId: s2.defaultShopId,
          );
        } else {
          rethrow;
        }
      }
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
      _products = rows;
      _policyTier = policy?['tier'] as String?;
      _currencyCode = (currency?['code'] as String?) ?? 'USD';
      _currencyExponent = (currency?['exponent'] as int?) ?? 2;
      _currencySymbolOverride = currency?['symbol_override'] as String?;
      _shopDefaultTaxRateBps = (data['shop_default_tax_rate_bps'] as num?)?.toInt() ?? 0;
      _loading = false;
      notifyListeners();

      await SessionStore.setLastSyncNow();
      await SessionStore.setCurrency(
        code: _currencyCode,
        exponent: _currencyExponent,
        symbolOverride: _currencySymbolOverride,
      );
      catalog.applyFromProducts(rows);
      await sync.refreshFromStorage();
      final active = await SessionStore.load();
      if (active != null) {
        await OutboxService.flush(InventoryApi(active.baseUrl), sync);
      }
    } catch (e) {
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
    notifyListeners();
  }
}
