import 'dart:async';

import 'inventory_api.dart';
import 'session_store.dart';

/// Wraps `InventoryApi` calls with transparent 401 → refresh → retry.
///
/// Must be a single shared instance across the app: without that, concurrent
/// 401s would each perform their own refresh, causing the server to rotate
/// the device refresh token multiple times and permanently invalidate
/// whichever client lost the race.
class AuthenticatedApi {
  AuthenticatedApi();

  Completer<SessionData?>? _inflightRefresh;

  /// Runs [call] with the current session. On 401, performs (or joins) a
  /// single in-flight refresh, reloads the session, and retries [call] once.
  ///
  /// Throws:
  ///   * `ApiException` if [call] fails with a non-401 error
  ///   * `ApiException(401)` from `/refresh` if the refresh token itself is
  ///     rejected — caller should route user to re-enrollment
  ///   * `StateError` if the session is missing
  Future<T> run<T>(Future<T> Function(InventoryApi api, SessionData s) call) async {
    var session = await SessionStore.load();
    if (session == null) {
      throw StateError('No session available');
    }
    var api = InventoryApi(session.baseUrl);
    try {
      return await call(api, session);
    } on ApiException catch (e) {
      if (e.statusCode != 401) rethrow;
      final refreshed = await _refreshOnce(session);
      if (refreshed == null) rethrow;
      session = refreshed;
      api = InventoryApi(session.baseUrl);
      return await call(api, session);
    }
  }

  /// Joins the in-flight refresh if one exists, otherwise starts one.
  Future<SessionData?> _refreshOnce(SessionData stale) async {
    final existing = _inflightRefresh;
    if (existing != null) return existing.future;

    final completer = Completer<SessionData?>();
    _inflightRefresh = completer;
    try {
      final api = InventoryApi(stale.baseUrl);
      final body = await api.refresh(refreshToken: stale.refreshToken);
      await SessionStore.save(
        baseUrl: stale.baseUrl,
        accessToken: body['access_token'] as String,
        refreshToken: body['refresh_token'] as String,
        tenantId: body['tenant_id'] as String,
        shopIds: (body['shop_ids'] as List<dynamic>).map((x) => x.toString()).toList(),
      );
      final next = await SessionStore.load();
      completer.complete(next);
      return next;
    } catch (e, st) {
      completer.completeError(e, st);
      rethrow;
    } finally {
      _inflightRefresh = null;
    }
  }
}
