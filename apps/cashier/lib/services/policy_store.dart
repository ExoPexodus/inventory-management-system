import 'package:shared_preferences/shared_preferences.dart';

import '../config/cashier_timings.dart';

/// Tenant-level policy + currency configuration delivered via sync pull.
/// These settings persist across employee sign-outs so the cashier can keep
/// enforcing them while offline.
class PolicyStore {
  const PolicyStore._();

  static const _maxOfflineMinutes = 'ims_max_offline_minutes';
  static const _sessionTimeoutMinutes = 'ims_session_timeout_minutes';
  static const _currencyCode = 'ims_currency_code';
  static const _currencyExponent = 'ims_currency_exponent';
  static const _currencySymbolOverride = 'ims_currency_symbol_override';
  static const _shopTimezone = 'ims_shop_timezone';

  static Future<void> saveMaxOfflineMinutes(int minutes) async {
    final p = await SharedPreferences.getInstance();
    await p.setInt(_maxOfflineMinutes, minutes);
  }

  static Future<int> getMaxOfflineMinutes() async {
    final p = await SharedPreferences.getInstance();
    return p.getInt(_maxOfflineMinutes) ?? CashierTimings.defaultOfflineLimitMinutes;
  }

  static Future<void> saveSessionTimeoutMinutes(int minutes) async {
    final p = await SharedPreferences.getInstance();
    await p.setInt(_sessionTimeoutMinutes, minutes);
  }

  static Future<int> getSessionTimeoutMinutes() async {
    final p = await SharedPreferences.getInstance();
    return p.getInt(_sessionTimeoutMinutes) ?? CashierTimings.defaultSessionTimeoutMinutes;
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

  static Future<void> setShopTimezone(String tz) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_shopTimezone, tz);
  }

  static Future<String> getShopTimezone() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_shopTimezone) ?? 'UTC';
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_maxOfflineMinutes);
    await p.remove(_sessionTimeoutMinutes);
    await p.remove(_currencyCode);
    await p.remove(_currencyExponent);
    await p.remove(_currencySymbolOverride);
    await p.remove(_shopTimezone);
  }
}
