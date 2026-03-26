import 'dart:convert';

/// Reads device UUID from access token payload (`sub`). Does not verify signature.
String? deviceIdFromAccessToken(String token) {
  try {
    final parts = token.split('.');
    if (parts.length != 3) return null;
    var payload = parts[1].replaceAll('-', '+').replaceAll('_', '/');
    switch (payload.length % 4) {
      case 2:
        payload += '==';
        break;
      case 3:
        payload += '=';
        break;
    }
    final jsonStr = utf8.decode(base64.decode(payload));
    final map = jsonDecode(jsonStr) as Map<String, dynamic>;
    return map['sub'] as String?;
  } catch (_) {
    return null;
  }
}
