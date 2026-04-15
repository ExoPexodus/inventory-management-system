import 'dart:async';

import '../config/cashier_timings.dart';
import 'session_store.dart';

/// Tracks the last user-interaction timestamp and fires [onTimeout] once the
/// configured employee-session window elapses.
///
/// Owns its own periodic timer so the shell does not have to drive it.
class InactivityController {
  InactivityController({required this.onTimeout});

  final Future<void> Function() onTimeout;

  DateTime _lastActivityAt = DateTime.now();
  Timer? _timer;
  bool _firing = false;

  void start() {
    _timer ??= Timer.periodic(CashierTimings.inactivityCheckInterval, (_) => checkNow());
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
  }

  /// Update the in-memory timestamp and persist it so a cold start picks up
  /// where the previous session left off.
  void recordActivity() {
    _lastActivityAt = DateTime.now();
    SessionStore.saveLastActivityNow();
  }

  /// Synchronous variant for cases that want to await the persistence.
  Future<void> recordActivityAndPersist() async {
    _lastActivityAt = DateTime.now();
    await SessionStore.saveLastActivityNow();
  }

  Future<void> checkNow() async {
    if (_firing) return;
    final timeoutMinutes = await SessionStore.getSessionTimeoutMinutes();
    final elapsed = DateTime.now().difference(_lastActivityAt).inMinutes;
    if (elapsed < timeoutMinutes) return;
    _firing = true;
    try {
      await SessionStore.clearEmployeeSession();
      await onTimeout();
    } finally {
      _firing = false;
    }
  }
}
