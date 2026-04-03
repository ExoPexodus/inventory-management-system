import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class SessionData {
  const SessionData({
    required this.baseUrl,
    required this.accessToken,
    required this.refreshToken,
    required this.tenantId,
    required this.shopIds,
    this.pendingEmployeeId,
    this.pendingEmployeeName,
    this.pendingEmployeeCredentialType,
    this.employeeId,
    this.employeeName,
    this.employeeEmail,
    this.employeePosition,
    this.employeeCredentialType,
  });

  final String baseUrl;
  final String accessToken;
  final String refreshToken;
  final String tenantId;
  final List<String> shopIds;
  final String? pendingEmployeeId;
  final String? pendingEmployeeName;
  final String? pendingEmployeeCredentialType;
  final String? employeeId;
  final String? employeeName;
  final String? employeeEmail;
  final String? employeePosition;
  final String? employeeCredentialType;

  String get defaultShopId => shopIds.isNotEmpty ? shopIds.first : '';
  bool get hasEmployeeSession => employeeId != null && employeeId!.isNotEmpty;
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
  static const _pendingEmployeeId = 'ims_pending_employee_id';
  static const _pendingEmployeeName = 'ims_pending_employee_name';
  static const _pendingEmployeeCredentialType = 'ims_pending_credential_type';
  static const _employeeId = 'ims_employee_id';
  static const _employeeName = 'ims_employee_name';
  static const _employeeEmail = 'ims_employee_email';
  static const _employeePosition = 'ims_employee_position';
  static const _employeeCredentialType = 'ims_employee_credential_type';

  static Future<void> save({
    required String baseUrl,
    required String accessToken,
    required String refreshToken,
    required String tenantId,
    required List<String> shopIds,
    String? pendingEmployeeId,
    String? pendingEmployeeName,
    String? pendingEmployeeCredentialType,
  }) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_baseUrl, baseUrl);
    await p.setString(_access, accessToken);
    await p.setString(_refresh, refreshToken);
    await p.setString(_tenant, tenantId);
    await p.setString(_shops, jsonEncode(shopIds));
    if (pendingEmployeeId == null || pendingEmployeeId.isEmpty) {
      await p.remove(_pendingEmployeeId);
    } else {
      await p.setString(_pendingEmployeeId, pendingEmployeeId);
    }
    if (pendingEmployeeName == null || pendingEmployeeName.isEmpty) {
      await p.remove(_pendingEmployeeName);
    } else {
      await p.setString(_pendingEmployeeName, pendingEmployeeName);
    }
    if (pendingEmployeeCredentialType == null || pendingEmployeeCredentialType.isEmpty) {
      await p.remove(_pendingEmployeeCredentialType);
    } else {
      await p.setString(_pendingEmployeeCredentialType, pendingEmployeeCredentialType);
    }
  }

  static Future<SessionData?> load() async {
    final p = await SharedPreferences.getInstance();
    final base = p.getString(_baseUrl);
    final access = p.getString(_access);
    final refresh = p.getString(_refresh);
    final tenant = p.getString(_tenant);
    final shopsRaw = p.getString(_shops);
    final pendingEmployeeId = p.getString(_pendingEmployeeId);
    final pendingEmployeeName = p.getString(_pendingEmployeeName);
    final pendingEmployeeCredentialType = p.getString(_pendingEmployeeCredentialType);
    final employeeId = p.getString(_employeeId);
    final employeeName = p.getString(_employeeName);
    final employeeEmail = p.getString(_employeeEmail);
    final employeePosition = p.getString(_employeePosition);
    final employeeCredentialType = p.getString(_employeeCredentialType);
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
      pendingEmployeeId: pendingEmployeeId,
      pendingEmployeeName: pendingEmployeeName,
      pendingEmployeeCredentialType: pendingEmployeeCredentialType,
      employeeId: employeeId,
      employeeName: employeeName,
      employeeEmail: employeeEmail,
      employeePosition: employeePosition,
      employeeCredentialType: employeeCredentialType,
    );
  }

  static Future<void> saveEmployeeSession({
    required String employeeId,
    required String name,
    required String email,
    required String position,
    required String credentialType,
  }) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_employeeId, employeeId);
    await p.setString(_employeeName, name);
    await p.setString(_employeeEmail, email);
    await p.setString(_employeePosition, position);
    await p.setString(_employeeCredentialType, credentialType);
    await p.remove(_pendingEmployeeId);
  }

  static Future<void> clearEmployeeSession() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_employeeId);
    await p.remove(_employeeName);
    await p.remove(_employeeEmail);
    await p.remove(_employeePosition);
    await p.remove(_employeeCredentialType);
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
    await p.remove(_pendingEmployeeId);
    await p.remove(_pendingEmployeeName);
    await p.remove(_pendingEmployeeCredentialType);
    await p.remove(_employeeId);
    await p.remove(_employeeName);
    await p.remove(_employeeEmail);
    await p.remove(_employeePosition);
    await p.remove(_employeeCredentialType);
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
