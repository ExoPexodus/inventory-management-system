import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.statusCode, this.body);

  final int statusCode;
  final String body;

  @override
  String toString() => 'ApiException($statusCode): $body';
}

class ProductRow {
  ProductRow({
    required this.id,
    required this.sku,
    required this.name,
    required this.unitPriceCents,
    required this.quantity,
    this.category,
    this.effectiveTaxRateBps = 0,
    this.taxExempt = false,
    this.productGroupId,
    this.groupTitle,
    this.variantLabel,
  });

  final String id;
  final String sku;
  final String name;
  final String? category;
  /// Basis points applicable at synced shop (0 when [taxExempt]).
  final int effectiveTaxRateBps;
  final bool taxExempt;
  final int unitPriceCents;
  final int quantity;
  final String? productGroupId;
  final String? groupTitle;
  final String? variantLabel;

  factory ProductRow.merged(Map<String, dynamic> product, int quantity) {
    return ProductRow(
      id: product['id'] as String,
      sku: product['sku'] as String,
      name: product['name'] as String,
      unitPriceCents: product['unit_price_cents'] as int,
      quantity: quantity,
      category: product['category'] as String?,
      effectiveTaxRateBps: (product['effective_tax_rate_bps'] as num?)?.toInt() ?? 0,
      taxExempt: product['tax_exempt'] as bool? ?? false,
      productGroupId: product['product_group_id'] as String?,
      groupTitle: product['group_title'] as String?,
      variantLabel: product['variant_label'] as String?,
    );
  }
}

class TransactionListPage {
  TransactionListPage({required this.items, this.nextCursor});

  final List<Map<String, dynamic>> items;
  final String? nextCursor;

  /// Accepts wrapped `{ items, next_cursor }` or a legacy JSON array.
  factory TransactionListPage.decode(Object? decoded) {
    if (decoded is List) {
      return TransactionListPage(
        items: decoded.cast<Map<String, dynamic>>(),
        nextCursor: null,
      );
    }
    final m = decoded as Map<String, dynamic>;
    return TransactionListPage(
      items: (m['items'] as List<dynamic>).cast<Map<String, dynamic>>(),
      nextCursor: m['next_cursor'] as String?,
    );
  }
}

class InventoryApi {
  InventoryApi(this.baseUrl);

  final String baseUrl;

  Uri _uri(String path, [Map<String, String>? query]) {
    final trimmed = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    final u = Uri.parse('$trimmed$path');
    if (query == null || query.isEmpty) return u;
    return u.replace(queryParameters: query);
  }

  Future<Map<String, dynamic>> enroll({
    required String enrollmentToken,
    required String deviceFingerprint,
    String platform = 'android',
  }) async {
    final r = await http.post(
      _uri('/v1/devices/enroll'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'enrollment_token': enrollmentToken,
        'device_fingerprint': deviceFingerprint,
        'platform': platform,
      }),
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> refresh({required String refreshToken}) async {
    final r = await http.post(
      _uri('/v1/devices/refresh'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'refresh_token': refreshToken}),
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> employeeLogin({
    required String accessToken,
    required String credential,
    String? employeeId,
    String? email,
  }) async {
    final payload = <String, dynamic>{'credential': credential};
    if (employeeId != null && employeeId.isNotEmpty) payload['employee_id'] = employeeId;
    if (email != null && email.isNotEmpty) payload['email'] = email;
    final r = await http.post(
      _uri('/v1/employees/login'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode(payload),
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> syncPull({
    required String accessToken,
    required String shopId,
    String? cursor,
  }) async {
    final q = <String, String>{'shop_id': shopId};
    if (cursor != null && cursor.isNotEmpty) q['cursor'] = cursor;
    final r = await http.get(
      _uri('/v1/sync/pull', q),
      headers: {'Authorization': 'Bearer $accessToken'},
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> syncPush({
    required String accessToken,
    required String deviceId,
    required String idempotencyKey,
    required List<Map<String, dynamic>> events,
    int? timeoutMs,
  }) async {
    final req = http.post(
      _uri('/v1/sync/push'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({
        'device_id': deviceId,
        'idempotency_key': idempotencyKey,
        'events': events,
      }),
    );
    final r = timeoutMs == null ? await req : await req.timeout(Duration(milliseconds: timeoutMs));
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<bool> ping({int timeoutMs = 2500}) async {
    try {
      final r = await http.get(_uri('/health')).timeout(Duration(milliseconds: timeoutMs));
      return r.statusCode >= 200 && r.statusCode < 300;
    } catch (_) {
      return false;
    }
  }

  /// Recent transactions for this device and shop (device bearer).
  Future<TransactionListPage> listTransactions({
    required String accessToken,
    required String shopId,
    int limit = 50,
    String? cursor,
    String? status,
    String? q,
  }) async {
    final query = <String, String>{
      'shop_id': shopId,
      'limit': '$limit',
    };
    if (cursor != null && cursor.isNotEmpty) query['cursor'] = cursor;
    if (status != null && status.isNotEmpty) query['status'] = status;
    if (q != null && q.isNotEmpty) query['q'] = q;
    final r = await http.get(
      _uri('/v1/transactions', query),
      headers: {'Authorization': 'Bearer $accessToken'},
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    final decoded = jsonDecode(r.body);
    return TransactionListPage.decode(decoded);
  }

  Future<Map<String, dynamic>> shiftSummary({
    required String accessToken,
    required String shopId,
    String? sinceIso,
  }) async {
    final query = <String, String>{'shop_id': shopId};
    if (sinceIso != null && sinceIso.isNotEmpty) query['since'] = sinceIso;
    final r = await http.get(
      _uri('/v1/transactions/shift-summary', query),
      headers: {'Authorization': 'Bearer $accessToken'},
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// Returns the active (open) shift for this device's shop, or null if none.
  Future<Map<String, dynamic>?> getActiveShift({required String accessToken}) async {
    final r = await http.get(
      _uri('/v1/shifts/active'),
      headers: {'Authorization': 'Bearer $accessToken'},
    );
    if (r.statusCode == 404) return null;
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// Opens a new shift. Throws ApiException(409) if one is already open.
  Future<Map<String, dynamic>> openShift({
    required String accessToken,
    String? notes,
  }) async {
    final r = await http.post(
      _uri('/v1/shifts'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({'notes': notes}),
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// Closes the given shift with the cashier's physical cash count.
  Future<Map<String, dynamic>> closeShift({
    required String accessToken,
    required String shiftId,
    required int reportedCashCents,
    String? notes,
  }) async {
    final r = await http.patch(
      _uri('/v1/shifts/$shiftId/close'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $accessToken',
      },
      body: jsonEncode({
        'reported_cash_cents': reportedCashCents,
        'notes': notes,
      }),
    );
    if (r.statusCode >= 400) throw ApiException(r.statusCode, r.body);
    return jsonDecode(r.body) as Map<String, dynamic>;
  }
}
