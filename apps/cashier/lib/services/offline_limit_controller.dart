import 'dart:async';

import 'package:flutter/foundation.dart';

import '../config/cashier_timings.dart';
import 'debug_log.dart';
import 'session_store.dart';

/// Tracks whether the device has been offline longer than the policy allows.
///
/// On every check, if the elapsed time since [SessionStore.getLastSyncIso] has
/// crossed [SessionStore.getMaxOfflineMinutes], we first attempt a live sync
/// via the injected [probe]. The wall only goes up if that probe fails to
/// advance the last-sync timestamp.
class OfflineLimitController extends ChangeNotifier {
  OfflineLimitController({required this.probe});

  /// Live-sync attempt. Should pull from the server and (on success) update
  /// [SessionStore.setLastSyncNow]. Errors are caught here.
  final Future<void> Function() probe;

  bool _exceeded = false;
  bool _checking = false;
  Timer? _timer;

  bool get exceeded => _exceeded;

  void start() {
    _timer ??= Timer.periodic(CashierTimings.offlineCheckInterval, (_) => checkNow());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _timer = null;
    super.dispose();
  }

  Future<void> checkNow() async {
    if (_checking) return;
    _checking = true;
    try {
      final lastSyncIso = await SessionStore.getLastSyncIso();
      if (lastSyncIso == null || lastSyncIso.isEmpty) {
        DebugLog.log('OFFLINE', 'no lastSyncIso yet — skipping wall check');
        return;
      }
      final lastSync = DateTime.tryParse(lastSyncIso);
      if (lastSync == null) return;
      final maxMinutes = await SessionStore.getMaxOfflineMinutes();
      final elapsed = DateTime.now().difference(lastSync.toLocal()).inMinutes;
      DebugLog.log('OFFLINE', 'elapsed=${elapsed}m max=${maxMinutes}m');

      if (elapsed < maxMinutes) {
        _setExceeded(false);
        return;
      }

      DebugLog.log('OFFLINE', 'limit exceeded — attempting live sync before wall');
      try {
        await probe();
      } catch (_) {
        // Probe failure is expected when offline — fall through to wall check.
      }

      final freshIso = await SessionStore.getLastSyncIso();
      final freshSync = DateTime.tryParse(freshIso ?? '');
      final freshElapsed = freshSync == null
          ? maxMinutes
          : DateTime.now().difference(freshSync.toLocal()).inMinutes;
      final showWall = freshElapsed >= maxMinutes;
      DebugLog.log('OFFLINE', 'post-sync elapsed=${freshElapsed}m → wall=$showWall');
      _setExceeded(showWall);
    } finally {
      _checking = false;
    }
  }

  void _setExceeded(bool value) {
    if (_exceeded == value) return;
    _exceeded = value;
    notifyListeners();
  }
}
