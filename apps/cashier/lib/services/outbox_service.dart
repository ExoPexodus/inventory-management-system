import 'dart:convert';

import '../models/sync_state_model.dart';
import '../util/jwt_device_id.dart';
import '../util/json_map.dart';
import '../util/push_conflict_message.dart';
import 'inventory_api.dart';
import 'outbox_db.dart';
import 'session_store.dart';

class OutboxService {
  static Future<void> enqueue({
    required String clientMutationId,
    required String idempotencyKey,
    required Map<String, dynamic> event,
  }) async {
    await OutboxDb.insert(
      clientMutationId: clientMutationId,
      idempotencyKey: idempotencyKey,
      eventJson: jsonEncode(event),
    );
  }

  static Future<SessionData?> _refreshSession(InventoryApi api, SessionData s) async {
    final body = await api.refresh(refreshToken: s.refreshToken);
    await SessionStore.save(
      baseUrl: s.baseUrl,
      accessToken: body['access_token'] as String,
      refreshToken: body['refresh_token'] as String,
      tenantId: body['tenant_id'] as String,
      shopIds: (body['shop_ids'] as List<dynamic>).map((x) => x.toString()).toList(),
    );
    return SessionStore.load();
  }

  /// Sends pending outbox events in order. Stops on auth/network/server errors.
  static Future<void> flush(InventoryApi api, SyncStateModel syncState) async {
    final pending = await OutboxDb.pendingOrdered();
    for (final row in pending) {
      var session = await SessionStore.load();
      if (session == null) break;

      var deviceId = deviceIdFromAccessToken(session.accessToken);
      if (deviceId == null) break;

      final event = jsonDecode(row.eventJson) as Map<String, dynamic>;
      Map<String, dynamic> response;

      try {
        response = await api.syncPush(
          accessToken: session.accessToken,
          deviceId: deviceId,
          idempotencyKey: row.idempotencyKey,
          events: [event],
        );
      } on ApiException catch (e) {
        if (e.statusCode == 401) {
          final next = await _refreshSession(api, session);
          if (next == null) break;
          session = next;
          deviceId = deviceIdFromAccessToken(session.accessToken);
          if (deviceId == null) break;
          try {
            response = await api.syncPush(
              accessToken: session.accessToken,
              deviceId: deviceId,
              idempotencyKey: row.idempotencyKey,
              events: [event],
            );
          } catch (_) {
            break;
          }
        } else {
          break;
        }
      } catch (_) {
        break;
      }

      final results = (response['results'] as List<dynamic>).cast<Map<String, dynamic>>();
      if (results.isEmpty) break;
      final status = results.first['status'] as String?;
      if (status == 'accepted' || status == 'duplicate') {
        await OutboxDb.deleteById(row.id);
      } else if (status == 'rejected') {
        final detail = results.first['detail'] as String?;
        final conflict = asJsonObject(results.first['conflict']);
        await OutboxDb.deleteById(row.id);
        syncState.setLastOutboxFailure(describePushConflict(conflict, detail));
      } else {
        break;
      }
    }
    await syncState.refreshFromStorage();
  }
}
