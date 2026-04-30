import 'package:timezone/timezone.dart' as tz;

/// Formats an ISO-8601 UTC instant for display in the given IANA [shopTimezone].
///
/// Falls back to device local time if [shopTimezone] is not found in the
/// bundled timezone database.
String formatShortLocalDateTime(String isoUtc, {String shopTimezone = 'UTC'}) {
  final utcDt = DateTime.tryParse(isoUtc);
  if (utcDt == null) return isoUtc;

  DateTime local;
  try {
    final location = tz.getLocation(shopTimezone);
    final tzDt = tz.TZDateTime.from(utcDt.toUtc(), location);
    local = tzDt;
  } catch (_) {
    local = utcDt.toLocal();
  }

  final h24 = local.hour;
  final h12 = h24 % 12 == 0 ? 12 : h24 % 12;
  final mm = local.minute.toString().padLeft(2, '0');
  final ap = h24 >= 12 ? 'PM' : 'AM';
  return '${local.month}/${local.day}/${local.year} $h12:$mm $ap';
}
