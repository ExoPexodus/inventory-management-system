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

  /// Sends pending outbox events in order.
  /// Skips events that fail with transient errors (network/5xx), stops after
  /// 3 consecutive failures to avoid spinning. Auth failures (401) attempt a
  /// single token refresh before giving up.
  static Future<void> flush(InventoryApi api, SyncStateModel syncState) async {
    final pending = await OutboxDb.pendingOrdered();
    int consecutiveErrors = 0;

    for (final row in pending) {
      if (consecutiveErrors >= 3) break;

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
          // Try refreshing the device token once.
          SessionData? next;
          try {
            next = await _refreshSession(api, session);
          } catch (_) {
            // Refresh failed — device session is dead, stop entirely.
            break;
          }
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
            consecutiveErrors++;
            continue;
          }
        } else if (e.statusCode >= 500) {
          // Server error — transient, skip this event and try the next.
          consecutiveErrors++;
          syncState.setLastOutboxFailure('Server error (${e.statusCode}) — will retry');
          continue;
        } else {
          // 4xx (not 401) — permanent client error, drop the event.
          await OutboxDb.deleteById(row.id);
          syncState.setLastOutboxFailure('Event rejected (${e.statusCode}): ${e.body}');
          consecutiveErrors = 0;
          continue;
        }
      } catch (_) {
        // Network timeout or other transient error — skip this event, try next.
        consecutiveErrors++;
        syncState.setLastOutboxFailure('Network error — will retry when online');
        continue;
      }

      consecutiveErrors = 0;
      final results = (response['results'] as List<dynamic>).cast<Map<String, dynamic>>();
      if (results.isEmpty) {
        consecutiveErrors++;
        continue;
      }
      final eventStatus = results.first['status'] as String?;
      if (eventStatus == 'accepted' || eventStatus == 'duplicate') {
        await OutboxDb.deleteById(row.id);
      } else if (eventStatus == 'rejected') {
        final detail = results.first['detail'] as String?;
        final conflict = asJsonObject(results.first['conflict']);
        await OutboxDb.deleteById(row.id);
        syncState.setLastOutboxFailure(describePushConflict(conflict, detail));
      } else {
        consecutiveErrors++;
      }
    }
    await syncState.refreshFromStorage();
  }
}
