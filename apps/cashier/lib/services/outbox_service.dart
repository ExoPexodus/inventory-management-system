import 'dart:convert';

import '../models/sync_state_model.dart';
import '../util/jwt_device_id.dart';
import '../util/json_map.dart';
import '../util/push_conflict_message.dart';
import 'authenticated_api.dart';
import 'inventory_api.dart';
import 'outbox_db.dart';

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

  /// Sends pending outbox events in order.
  /// Skips events that fail with transient errors (network/5xx), stops after
  /// 3 consecutive failures to avoid spinning. Auth is handled by [auth] —
  /// a single 401 that survives refresh terminates the flush.
  static Future<void> flush(AuthenticatedApi auth, SyncStateModel syncState) async {
    final pending = await OutboxDb.pendingOrdered();
    int consecutiveErrors = 0;

    for (final row in pending) {
      if (consecutiveErrors >= 3) break;

      final event = jsonDecode(row.eventJson) as Map<String, dynamic>;
      Map<String, dynamic> response;

      try {
        response = await auth.run((api, session) {
          final deviceId = deviceIdFromAccessToken(session.accessToken);
          if (deviceId == null) {
            throw StateError('no_device_id');
          }
          return api.syncPush(
            accessToken: session.accessToken,
            deviceId: deviceId,
            idempotencyKey: row.idempotencyKey,
            events: [event],
          );
        });
      } on ApiException catch (e) {
        if (e.statusCode == 401) {
          // Refresh token itself is dead — stop entirely.
          break;
        }
        if (e.statusCode >= 500) {
          consecutiveErrors++;
          syncState.setLastOutboxFailure('Server error (${e.statusCode}) — will retry');
          continue;
        }
        // 4xx (not 401) — permanent client error, drop the event.
        await OutboxDb.deleteById(row.id);
        syncState.setLastOutboxFailure('Event rejected (${e.statusCode}): ${e.body}');
        consecutiveErrors = 0;
        continue;
      } on StateError {
        // No session / no device_id — stop entirely.
        break;
      } catch (_) {
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
