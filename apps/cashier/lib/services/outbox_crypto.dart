import 'dart:convert';
import 'dart:math';

import 'package:encrypt/encrypt.dart' as enc;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _kSecureKey = 'ims_outbox_aes_key_b64';
const _encPrefix = 'E1:';

/// AES-CBC payload sealed with a key kept in platform secure storage (legacy plaintext rows still supported).
class OutboxCrypto {
  static const FlutterSecureStorage _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static Future<enc.Key> _loadKey() async {
    var b64 = await _storage.read(key: _kSecureKey);
    if (b64 == null || b64.length < 32) {
      final rnd = Random.secure();
      final bytes = List<int>.generate(32, (_) => rnd.nextInt(256));
      b64 = base64Encode(bytes);
      await _storage.write(key: _kSecureKey, value: b64);
    }
    return enc.Key.fromBase64(b64);
  }

  static Future<String> seal(String plaintext) async {
    final key = await _loadKey();
    final iv = enc.IV.fromLength(16);
    final encrypter = enc.Encrypter(enc.AES(key, mode: enc.AESMode.cbc));
    final out = encrypter.encrypt(plaintext, iv: iv);
    return '$_encPrefix${iv.base64}|${out.base64}';
  }

  static Future<String> open(String stored) async {
    if (!stored.startsWith(_encPrefix)) {
      return stored;
    }
    final rest = stored.substring(_encPrefix.length);
    final pipe = rest.indexOf('|');
    if (pipe < 0) return stored;
    final ivB64 = rest.substring(0, pipe);
    final cipherB64 = rest.substring(pipe + 1);
    final key = await _loadKey();
    final iv = enc.IV.fromBase64(ivB64);
    final encrypter = enc.Encrypter(enc.AES(key, mode: enc.AESMode.cbc));
    return encrypter.decrypt(enc.Encrypted.fromBase64(cipherB64), iv: iv);
  }

  /// Call on logout so the next user does not reuse the same AES key.
  static Future<void> wipeKeyForNextUser() async {
    await _storage.delete(key: _kSecureKey);
  }
}
