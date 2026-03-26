/// Normalizes decoded JSON [Map] (including [Map<dynamic, dynamic>]) for lookups.
Map<String, dynamic>? asJsonObject(dynamic value) {
  if (value == null) return null;
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((k, v) => MapEntry(k.toString(), v));
  }
  return null;
}
