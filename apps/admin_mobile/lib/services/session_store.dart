import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/session.dart';

class SessionStore {
  static const _storage = FlutterSecureStorage();
  static const _keyToken = 'admin_token';
  static const _keyEmail = 'admin_email';
  static const _keyBaseUrl = 'admin_base_url';
  static const _keyRole = 'admin_role';
  static const _keyPermissions = 'admin_permissions';

  static Future<void> save(AdminSession session) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBaseUrl, session.baseUrl);
    if (session.role != null) {
      await prefs.setString(_keyRole, session.role!);
    } else {
      await prefs.remove(_keyRole);
    }
    await prefs.setString(_keyPermissions, jsonEncode(session.permissions));
    await _storage.write(key: _keyToken, value: session.token);
    await _storage.write(key: _keyEmail, value: session.email);
  }

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

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyBaseUrl);
    await prefs.remove(_keyRole);
    await prefs.remove(_keyPermissions);
    await _storage.delete(key: _keyToken);
    await _storage.delete(key: _keyEmail);
  }

  static Future<String?> getSavedBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyBaseUrl);
  }
}
