import 'package:shared_preferences/shared_preferences.dart';

import 'policy_store.dart';

/// Activity-scoped timestamps: last user interaction and last successful sync.
/// These drive the inactivity timeout and the offline-limit wall.
class ActivityStore {
  const ActivityStore._();

  static const _lastActivityAt = 'ims_last_activity_at';
  static const _lastSyncIso = 'ims_last_sync_iso';

  static Future<void> saveLastActivityNow() async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_lastActivityAt, DateTime.now().toUtc().toIso8601String());
  }

  static Future<String?> getLastActivityAt() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_lastActivityAt);
  }

  static Future<void> clearLastActivity() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_lastActivityAt);
  }

  static Future<void> setLastSyncNow() async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_lastSyncIso, DateTime.now().toUtc().toIso8601String());
  }

  static Future<String?> getLastSyncIso() async {
    final p = await SharedPreferences.getInstance();
    return p.getString(_lastSyncIso);
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_lastActivityAt);
    await p.remove(_lastSyncIso);
  }

  /// True iff [lastActivityAt] is older than the policy-configured inactivity
  /// timeout. Returns false when there is no recorded activity yet (e.g. the
  /// employee just signed in and hasn't interacted).
  static Future<bool> isEmployeeSessionTimedOut() async {
    final lastActivityIso = await getLastActivityAt();
    if (lastActivityIso == null) return false;
    final lastActivity = DateTime.tryParse(lastActivityIso);
    if (lastActivity == null) return false;
    final timeoutMinutes = await PolicyStore.getSessionTimeoutMinutes();
    final elapsed = DateTime.now().toUtc().difference(lastActivity.toUtc()).inMinutes;
    return elapsed >= timeoutMinutes;
  }
}
