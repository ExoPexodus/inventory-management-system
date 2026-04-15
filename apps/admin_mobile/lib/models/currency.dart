import 'package:flutter/foundation.dart';

import '../services/admin_api.dart';

/// Tenant currency configuration with formatting helpers.
///
/// Provided in the widget tree via ChangeNotifierProvider so all screens share
/// one instance. Call [load] once after login; defaults to USD until the
/// response arrives.
class CurrencyModel extends ChangeNotifier {
  String _code = 'USD';
  int _exponent = 2;
  String _symbol = r'$';

  String get code => _code;
  int get exponent => _exponent;
  String get symbol => _symbol;

  Future<void> load(AdminApi api) async {
    try {
      final data = await api.getCurrencySettings();
      final code = (data['currency_code'] as String? ?? 'USD').toUpperCase();
      final exponent = data['currency_exponent'] as int? ?? 2;
      final symbol = data['currency_symbol'] as String? ?? _symbolForCode(code);
      _code = code;
      _exponent = exponent;
      _symbol = symbol;
      notifyListeners();
    } catch (_) {
      // Keep defaults — non-fatal; formatting still works with USD.
    }
  }

  void reset() {
    _code = 'USD';
    _exponent = 2;
    _symbol = r'$';
    notifyListeners();
  }

  /// Formats [minorUnits] as a display string, e.g. "$12.34" for USD.
  String format(int minorUnits) {
    final sign = minorUnits < 0 ? '-' : '';
    final abs = minorUnits.abs();
    if (_exponent <= 0) return '$sign$_symbol$abs';
    final base = _pow10(_exponent);
    final whole = abs ~/ base;
    final frac = (abs % base).toString().padLeft(_exponent, '0');
    return '$sign$_symbol$whole.$frac';
  }

  /// Like [format] but abbreviates large amounts with K/M suffix.
  String formatAbbreviated(int minorUnits) {
    if (_exponent <= 0) return format(minorUnits);
    final major = minorUnits / _pow10(_exponent).toDouble();
    if (major >= 1000000) return '$_symbol${(major / 1000000).toStringAsFixed(1)}M';
    if (major >= 1000) return '$_symbol${(major / 1000).toStringAsFixed(1)}K';
    return format(minorUnits);
  }

  static int _pow10(int n) {
    var v = 1;
    for (var i = 0; i < n; i++) {
      v *= 10;
    }
    return v;
  }

  static String _symbolForCode(String code) {
    switch (code) {
      case 'USD':
        return r'$';
      case 'EUR':
        return '€';
      case 'GBP':
        return '£';
      case 'JPY':
        return '¥';
      default:
        return '$code ';
    }
  }
}
