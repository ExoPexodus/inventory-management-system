import 'package:flutter/foundation.dart';

/// Tiny in-memory ring buffer for runtime diagnostics. The offline-limit wall
/// renders the last N lines so a tester can screenshot them without adb.
class DebugLog {
  static final List<String> _lines = <String>[];
  static const int _max = 60;

  static void log(String tag, String msg) {
    final ts = DateTime.now().toIso8601String().substring(11, 23);
    final line = '[$ts] $tag  $msg';
    _lines.add(line);
    if (_lines.length > _max) _lines.removeAt(0);
    debugPrint(line);
  }

  static List<String> tail([int n = 20]) {
    final start = _lines.length - n;
    return _lines.sublist(start < 0 ? 0 : start);
  }
}
