import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class SessionData {
  const SessionData({
    required this.baseUrl,
    required this.accessToken,
    required this.refreshToken,
    required this.tenantId,
    required this.shopIds,
  });

  final String baseUrl;
  final String accessToken;
  final String refreshToken;
  final String tenantId;
  final List<String> shopIds;

  String get defaultShopId => shopIds.isNotEmpty ? shopIds.first : '';
}

class SessionStore {
  static const _baseUrl = 'ims_base_url';
  static const _access = 'ims_access_token';
  static const _refresh = 'ims_refresh_token';
  static const _tenant = 'ims_tenant_id';
  static const _shops = 'ims_shop_ids_json';
  static const _lastSyncIso = 'ims_last_sync_iso';
  static const _currencyCode = 'ims_currency_code';
  static const _currencyExponent = 'ims_currency_exponent';
  static const _currencySymbolOverride = 'ims_currency_symbol_override';

  static Future<void> save({
    required String baseUrl,
    required String accessToken,
    required String refreshToken,
    required String tenantId,
    required List<String> shopIds,
  }) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_baseUrl, baseUrl);
    await p.setString(_access, accessToken);
    await p.setString(_refresh, refreshToken);
    await p.setString(_tenant, tenantId);
    await p.setString(_shops, jsonEncode(shopIds));
  }

  static Future<SessionData?> load() async {
    final p = await SharedPreferences.getInstance();
    final base = p.getString(_baseUrl);
    final access = p.getString(_access);
    final refresh = p.getString(_refresh);
    final tenant = p.getString(_tenant);
    final shopsRaw = p.getString(_shops);
    if (base == null ||
        access == null ||
        refresh == null ||
        tenant == null ||
        shopsRaw == null) {
      return null;
    }
    final shopsList = (jsonDecode(shopsRaw) as List<dynamic>).cast<String>();
    return SessionData(
      baseUrl: base,
      accessToken: access,
      refreshToken: refresh,
      tenantId: tenant,
      shopIds: shopsList,
    );
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_baseUrl);
    await p.remove(_access);
    await p.remove(_refresh);
    await p.remove(_tenant);
    await p.remove(_shops);
    await p.remove(_lastSyncIso);
    await p.remove(_currencyCode);
    await p.remove(_currencyExponent);
    await p.remove(_currencySymbolOverride);
  }

  static Future<void> setLastSyncNow() async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_lastSyncIso, DateTime.now().toUtc().toIso8601String());
  }

  static Future<String?> getLastSyncIso() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_lastSyncIso);
  }

  static Future<void> setCurrency({
    required String code,
    required int exponent,
    String? symbolOverride,
  }) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_currencyCode, code.toUpperCase());
    await p.setInt(_currencyExponent, exponent);
    if (symbolOverride == null || symbolOverride.isEmpty) {
      await p.remove(_currencySymbolOverride);
    } else {
      await p.setString(_currencySymbolOverride, symbolOverride);
    }
  }

  static Future<String> getCurrencyCode() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_currencyCode) ?? 'USD';
  }

  static Future<int> getCurrencyExponent() async {
    final p = await SharedPreferences.getInstance();
    return p.getInt(_currencyExponent) ?? 2;
  }

  static Future<String?> getCurrencySymbolOverride() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_currencySymbolOverride);
  }
}
