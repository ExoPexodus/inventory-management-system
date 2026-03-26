/// Formats an ISO-8601 instant for compact local display (no extra package).
String formatShortLocalDateTime(String isoUtc) {
  final dt = DateTime.tryParse(isoUtc);
  if (dt == null) return isoUtc;
  final l = dt.toLocal();
  final h24 = l.hour;
  final h12 = h24 % 12 == 0 ? 12 : h24 % 12;
  final mm = l.minute.toString().padLeft(2, '0');
  final ap = h24 >= 12 ? 'PM' : 'AM';
  return '${l.month}/${l.day}/${l.year} $h12:$mm $ap';
}
