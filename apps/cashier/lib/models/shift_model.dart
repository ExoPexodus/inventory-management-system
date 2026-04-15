import 'package:flutter/foundation.dart';

/// Holds the currently open shift for this device's shop.
/// Updated by DashboardScreen on every data load; read by CartScreen to gate
/// checkout — a sale cannot be completed without an active shift.
class ShiftModel extends ChangeNotifier {
  Map<String, dynamic>? _activeShift;

  Map<String, dynamic>? get activeShift => _activeShift;
  bool get hasActiveShift => _activeShift != null;

  void update(Map<String, dynamic>? shift) {
    _activeShift = shift;
    notifyListeners();
  }

  void clear() {
    _activeShift = null;
    notifyListeners();
  }
}
