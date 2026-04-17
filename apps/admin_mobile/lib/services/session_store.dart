import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/session.dart';

class SessionStore {
  static const _storage = FlutterSecureStorage();

  // Enrollment keys (persist across login/logout)
  static const _keyBaseUrl = 'admin_base_url';
  static const _keyDeviceToken = 'admin_device_token';
  static const _keyRefreshToken = 'admin_refresh_token';
  static const _keyTenantId = 'admin_tenant_id';
  static const _keyEnrolled = 'admin_enrolled';

  // Login keys (cleared on logout, kept on app restart)
  static const _keyToken = 'admin_token';
  static const _keyEmail = 'admin_email';
  static const _keyRole = 'admin_role';
  static const _keyPermissions = 'admin_permissions';

  // Local PIN state (mirrors server — server holds the real hash)
  static const _keyPinEnabled = 'admin_pin_enabled';
  // Last-known email (persists across logout so PIN login can still display it).
  static const _keyLastEmail = 'admin_last_email';

  // ── Enrollment ──────────────────────────────────────────────────────

  /// Check if the device has been enrolled via QR code.
  static Future<bool> isEnrolled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_keyEnrolled) ?? false;
  }

  /// Save enrollment data from device enroll API response.
  static Future<void> saveEnrollment({
    required String baseUrl,
    required String deviceToken,
    required String refreshToken,
    required String tenantId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBaseUrl, baseUrl);
    await prefs.setString(_keyTenantId, tenantId);
    await prefs.setBool(_keyEnrolled, true);
    await _storage.write(key: _keyDeviceToken, value: deviceToken);
    await _storage.write(key: _keyRefreshToken, value: refreshToken);
  }

  /// Get the enrolled base URL.
  static Future<String?> getBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyBaseUrl);
  }

  /// Get the device access token (used to authenticate PIN login calls).
  static Future<String?> getDeviceToken() async {
    return _storage.read(key: _keyDeviceToken);
  }

  /// Clear enrollment — full device reset.
  static Future<void> clearEnrollment() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyBaseUrl);
    await prefs.remove(_keyTenantId);
    await prefs.remove(_keyEnrolled);
    await prefs.remove(_keyPinEnabled);
    await prefs.remove(_keyLastEmail);
    await _storage.delete(key: _keyDeviceToken);
    await _storage.delete(key: _keyRefreshToken);
    // Also clear login state
    await clearLogin();
  }

  // ── Operator login ──────────────────────────────────────────────────

  /// Save operator login session.
  static Future<void> save(AdminSession session) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBaseUrl, session.baseUrl);
    if (session.role != null) {
      await prefs.setString(_keyRole, session.role!);
    } else {
      await prefs.remove(_keyRole);
    }
    await prefs.setString(_keyPermissions, jsonEncode(session.permissions));
    if (session.email.isNotEmpty) {
      await prefs.setString(_keyLastEmail, session.email);
    }
    await _storage.write(key: _keyToken, value: session.token);
    await _storage.write(key: _keyEmail, value: session.email);
  }

  /// Returns the last email used to sign in on this device (for PIN login display).
  static Future<String?> getLastEmail() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyLastEmail);
  }

  /// Load operator session (returns null if not logged in).
  static Future<AdminSession?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final baseUrl = prefs.getString(_keyBaseUrl);
    if (baseUrl == null) return null;
    final token = await _storage.read(key: _keyToken);
    final email = await _storage.read(key: _keyEmail);
    if (token == null || token.isEmpty) return null;
    final role = prefs.getString(_keyRole);
    final permissionsRaw = prefs.getString(_keyPermissions);
    List<String> permissions = [];
    if (permissionsRaw != null) {
      try {
        permissions = List<String>.from(jsonDecode(permissionsRaw) as List);
      } catch (_) {}
    }
    return AdminSession(
      token: token,
      email: email ?? '',
      baseUrl: baseUrl,
      role: role,
      permissions: permissions,
    );
  }

  /// Clear login state only (keeps enrollment).
  static Future<void> clearLogin() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyRole);
    await prefs.remove(_keyPermissions);
    await _storage.delete(key: _keyToken);
    await _storage.delete(key: _keyEmail);
  }

  /// Legacy compat — alias for getBaseUrl.
  static Future<String?> getSavedBaseUrl() => getBaseUrl();

  // ── PIN quick-unlock ────────────────────────────────────────────────

  /// Whether the user has opted into PIN quick-unlock on this device.
  static Future<bool> isPinEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_keyPinEnabled) ?? false;
  }

  /// Mark PIN quick-unlock as enabled on this device (call after /set-pin succeeds).
  static Future<void> setPinEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    if (enabled) {
      await prefs.setBool(_keyPinEnabled, true);
    } else {
      await prefs.remove(_keyPinEnabled);
    }
  }
}
