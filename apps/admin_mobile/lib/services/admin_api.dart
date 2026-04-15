import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/analytics.dart';
import '../models/employee.dart';
// import '../models/transaction.dart';

class ApiException implements Exception {
  const ApiException(this.statusCode, this.body);
  final int statusCode;
  final String body;

  @override
  String toString() => 'ApiException($statusCode): $body';
}

class AdminApi {
  const AdminApi(this.baseUrl, this.token);

  final String baseUrl;
  final String token;

  Map<String, String> get _headers => {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      };

  Uri _uri(String path, [Map<String, String>? params]) {
    final base = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    final uri = Uri.parse('$base$path');
    return params != null ? uri.replace(queryParameters: params) : uri;
  }

  Future<Map<String, dynamic>> _get(String path, [Map<String, String>? params]) async {
    final res = await http.get(_uri(path, params), headers: _headers);
    if (res.statusCode == 401) throw const ApiException(401, 'unauthorized');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> _getList(String path, [Map<String, String>? params]) async {
    final res = await http.get(_uri(path, params), headers: _headers);
    if (res.statusCode == 401) throw const ApiException(401, 'unauthorized');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body) as List<dynamic>;
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final res = await http.post(_uri(path), headers: _headers, body: jsonEncode(body));
    if (res.statusCode == 401) throw const ApiException(401, 'unauthorized');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _patch(String path, Map<String, dynamic> body) async {
    final res = await http.patch(_uri(path), headers: _headers, body: jsonEncode(body));
    if (res.statusCode == 401) throw const ApiException(401, 'unauthorized');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<void> _delete(String path) async {
    final res = await http.delete(_uri(path), headers: _headers);
    if (res.statusCode == 401) throw const ApiException(401, 'unauthorized');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
  }

  // ── Auth ─────────────────────────────────────────────────────────────

  static Future<Map<String, dynamic>> login({
    required String baseUrl,
    required String email,
    required String password,
  }) async {
    final base = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    final res = await http.post(
      Uri.parse('$base/v1/admin/auth/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  static Future<Map<String, dynamic>> enroll({
    required String baseUrl,
    required String enrollmentToken,
    required String deviceFingerprint,
    required String platform,
  }) async {
    final base = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    final res = await http.post(
      Uri.parse('$base/v1/devices/enroll'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'enrollment_token': enrollmentToken,
        'device_fingerprint': deviceFingerprint,
        'platform': platform,
      }),
    );
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<bool> ping() async {
    try {
      final res = await http.get(_uri('/v1/health')).timeout(const Duration(seconds: 3));
      return res.statusCode < 500;
    } catch (_) {
      return false;
    }
  }

  // ── Currency ─────────────────────────────────────────────────────────

  /// Returns currency settings for the tenant: code, symbol, exponent.
  Future<Map<String, dynamic>> getCurrencySettings() =>
      _get('/v1/admin/tenant-settings/currency');

  // ── Analytics ────────────────────────────────────────────────────────

  Future<AnalyticsSummary> getAnalyticsSummary({int days = 7}) async {
    final data = await _get('/v1/admin/analytics/summary', {'days': '$days'});
    return AnalyticsSummary.fromJson(data);
  }

  Future<List<SalesPoint>> getSalesSeries({int days = 7, String granularity = 'day'}) async {
    final data = await _get('/v1/admin/analytics/sales-series', {
      'days': '$days',
      'granularity': granularity,
    });
    final items = data['items'] as List<dynamic>? ?? [];
    return items.map((e) => SalesPoint.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<CategoryItem>> getCategoryRevenue({int days = 7}) async {
    final data = await _get('/v1/admin/analytics/category-revenue', {'days': '$days'});
    final items = data['items'] as List<dynamic>? ?? [];
    return items.map((e) => CategoryItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<TopProduct>> getTopProducts({int days = 7, int limit = 5}) async {
    final data = await _get('/v1/admin/analytics/top-products', {
      'days': '$days',
      'limit': '$limit',
    });
    final items = data['items'] as List<dynamic>? ?? [];
    return items.map((e) => TopProduct.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ── Employees ────────────────────────────────────────────────────────

  Future<List<Employee>> getEmployees({bool includeInactive = false}) async {
    final list = await _getList('/v1/admin/employees', {
      if (includeInactive) 'include_inactive': 'true',
    });
    return list.map((e) => Employee.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Employee> createEmployee({
    required String name,
    required String email,
    required String position,
    required String credentialType,
  }) async {
    final data = await _post('/v1/admin/employees', {
      'name': name,
      'email': email,
      'position': position,
      'credential_type': credentialType,
    });
    return Employee.fromJson(data);
  }

  Future<void> deactivateEmployee(String id) => _delete('/v1/admin/employees/$id');

  Future<Employee> reactivateEmployee(String id) async {
    final data = await _patch('/v1/admin/employees/$id/reactivate', {});
    return Employee.fromJson(data);
  }

  Future<Map<String, dynamic>> reEnrollEmployee(String id) =>
      _post('/v1/admin/employees/$id/re-enroll', {});

  Future<void> resetEmployeeCredentials(String id) =>
      _post('/v1/admin/employees/$id/reset-credentials', {});

  // ── Transactions ─────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getTransactions({
    String? q,
    String? status,
    String? cursor,
    int limit = 30,
  }) async {
    final params = <String, String>{'limit': '$limit'};
    if (q != null && q.isNotEmpty) params['q'] = q;
    if (status != null) params['status'] = status;
    if (cursor != null) params['cursor'] = cursor;
    return await _get('/v1/admin/transactions', params);
  }
}
