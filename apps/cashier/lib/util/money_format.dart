/// Returns the display symbol for the given currency code, respecting any
/// tenant-configured override. Suitable for use as an input field prefix.
String currencySymbol(String code, {String? symbolOverride}) {
  if (symbolOverride != null && symbolOverride.isNotEmpty) return symbolOverride;
  return _symbolForCode(code);
}

/// Converts a major-unit decimal amount (e.g. 47.50) to integer minor units
/// (e.g. 4750 for exponent=2, 47 for exponent=0).
int majorToMinorUnits(double major, int exponent) {
  if (exponent <= 0) return major.round();
  return (major * _pow10(exponent)).round();
}

String _symbolForCode(String code) {
  switch (code.toUpperCase()) {
    case 'USD':
      return r'$';
    case 'EUR':
      return 'EUR ';
    case 'GBP':
      return 'GBP ';
    case 'JPY':
      return 'JPY ';
    default:
      return '${code.toUpperCase()} ';
  }
}

String formatMinorUnits(
  int amountMinor, {
  required String code,
  required int exponent,
  String? symbolOverride,
}) {
  final useExp = exponent < 0 ? 0 : exponent;
  final sign = amountMinor < 0 ? '-' : '';
  final absValue = amountMinor.abs();
  final base = useExp == 0 ? 1 : _pow10(useExp);
  final whole = absValue ~/ base;
  final frac = absValue % base;
  final fracStr = useExp == 0 ? '' : '.${frac.toString().padLeft(useExp, '0')}';
  final symbol = (symbolOverride != null && symbolOverride.isNotEmpty)
      ? symbolOverride
      : _symbolForCode(code);
  return '$sign$symbol$whole$fracStr';
}

int _pow10(int n) {
  var v = 1;
  for (var i = 0; i < n; i++) {
    v *= 10;
  }
  return v;
}

