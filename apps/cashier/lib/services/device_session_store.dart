import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

class DeviceSession {
  const DeviceSession({
    required this.baseUrl,
    required this.accessToken,
    required this.refreshToken,
    required this.tenantId,
    required this.shopIds,
    this.pendingEmployeeId,
    this.pendingEmployeeName,
    this.pendingEmployeeCredentialType,
  });

  final String baseUrl;
  final String accessToken;
  final String refreshToken;
  final String tenantId;
  final List<String> shopIds;
  final String? pendingEmployeeId;
  final String? pendingEmployeeName;
  final String? pendingEmployeeCredentialType;
}

/// Device-scoped enrollment data: base URL, tokens, tenant/shop assignment,
/// and any "pending employee" receipt captured during enrollment but not yet
/// signed in.
///
/// Clearing this store forces the user back through device enrollment.
class DeviceSessionStore {
  const DeviceSessionStore._();

  static const _baseUrl = 'ims_base_url';
  static const _access = 'ims_access_token';
  static const _refresh = 'ims_refresh_token';
  static const _tenant = 'ims_tenant_id';
  static const _shops = 'ims_shop_ids_json';
  static const _pendingEmployeeId = 'ims_pending_employee_id';
  static const _pendingEmployeeName = 'ims_pending_employee_name';
  static const _pendingEmployeeCredentialType = 'ims_pending_credential_type';

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
    await _setOrRemove(p, _pendingEmployeeId, pendingEmployeeId);
    await _setOrRemove(p, _pendingEmployeeName, pendingEmployeeName);
    await _setOrRemove(p, _pendingEmployeeCredentialType, pendingEmployeeCredentialType);
  }

  static Future<DeviceSession?> load() async {
    final p = await SharedPreferences.getInstance();
    final base = p.getString(_baseUrl);
    final access = p.getString(_access);
    final refresh = p.getString(_refresh);
    final tenant = p.getString(_tenant);
    final shopsRaw = p.getString(_shops);
    if (base == null || access == null || refresh == null || tenant == null || shopsRaw == null) {
      return null;
    }
    final shopsList = (jsonDecode(shopsRaw) as List<dynamic>).cast<String>();
    return DeviceSession(
      baseUrl: base,
      accessToken: access,
      refreshToken: refresh,
      tenantId: tenant,
      shopIds: shopsList,
      pendingEmployeeId: p.getString(_pendingEmployeeId),
      pendingEmployeeName: p.getString(_pendingEmployeeName),
      pendingEmployeeCredentialType: p.getString(_pendingEmployeeCredentialType),
    );
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_baseUrl);
    await p.remove(_access);
    await p.remove(_refresh);
    await p.remove(_tenant);
    await p.remove(_shops);
    await p.remove(_pendingEmployeeId);
    await p.remove(_pendingEmployeeName);
    await p.remove(_pendingEmployeeCredentialType);
  }

  static Future<void> _setOrRemove(SharedPreferences p, String key, String? value) {
    if (value == null || value.isEmpty) return p.remove(key);
    return p.setString(key, value);
  }
}
