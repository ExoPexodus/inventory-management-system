import 'package:flutter/foundation.dart';

import '../services/outbox_db.dart';
import '../services/session_store.dart';

class SyncStateModel extends ChangeNotifier {
  int _pendingOutbox = 0;
  String? _lastSyncIso;
  String? _lastOutboxFailure;

  int get pendingOutboxCount => _pendingOutbox;
  String? get lastSyncIso => _lastSyncIso;
  String? get lastOutboxFailure => _lastOutboxFailure;

  void setLastOutboxFailure(String? message) {
    _lastOutboxFailure = message;
    notifyListeners();
  }

  void clearTransientFailures() {
    _lastOutboxFailure = null;
    notifyListeners();
  }

  /// Clears in-memory sync UI state when the user logs out.
  void resetForLogout() {
    _lastOutboxFailure = null;
    _pendingOutbox = 0;
    _lastSyncIso = null;
    notifyListeners();
  }

  Future<void> refreshFromStorage() async {
    _pendingOutbox = await OutboxDb.countPending();
    _lastSyncIso = await SessionStore.getLastSyncIso();
    notifyListeners();
  }
}
