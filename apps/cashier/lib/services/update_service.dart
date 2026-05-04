import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:open_file/open_file.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';

class UpdateInfo {
  const UpdateInfo({
    required this.version,
    required this.versionCode,
    required this.downloadUrl,
    this.changelog,
    this.sizeMb,
  });

  final String version;
  final int versionCode;
  final String downloadUrl;
  final String? changelog;
  final double? sizeMb;
}

class UpdateService {
  UpdateService._();

  static final _plugin = FlutterLocalNotificationsPlugin();
  static const _kChannelId = 'ims_app_updates';
  static const _kNotifId = 1001;

  static String? _pendingApkPath;
  static int _lastNotifPercent = -1;
  static const _kInstallChannel = MethodChannel('ims/apk_install');

  // ── Initialization ───────────────────────────────────────────────────────

  static Future<void> initialize() async {
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    await _plugin.initialize(
      const InitializationSettings(android: androidSettings),
      onDidReceiveNotificationResponse: _onNotifTap,
    );
    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
  }

  static Future<void> _onNotifTap(NotificationResponse response) async {
    final path = _pendingApkPath;
    if (path != null) await installApk(path);
  }

  // ── Update detection ─────────────────────────────────────────────────────

  static Future<UpdateInfo?> checkForUpdate({
    required String baseUrl,
    required String accessToken,
    required String appName,
  }) async {
    try {
      final trimmedBase =
          baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
      final uri = Uri.parse('$trimmedBase/v1/apps/update-check')
          .replace(queryParameters: {'app_name': appName});
      final resp = await http
          .get(uri, headers: {'Authorization': 'Bearer $accessToken'})
          .timeout(const Duration(seconds: 10));

      if (resp.statusCode != 200) return null;
      final json = jsonDecode(resp.body) as Map<String, dynamic>;
      if (json['available'] != true) return null;

      final remoteCode = (json['version_code'] as num?)?.toInt();
      if (remoteCode == null) return null;

      final info = await PackageInfo.fromPlatform();
      final installedCode = int.tryParse(info.buildNumber) ?? 0;
      if (remoteCode <= installedCode) return null;

      return UpdateInfo(
        version: json['version'] as String? ?? '',
        versionCode: remoteCode,
        downloadUrl: json['download_url'] as String? ?? '',
        changelog: json['changelog'] as String?,
        sizeMb: (json['size_mb'] as num?)?.toDouble(),
      );
    } catch (_) {
      return null;
    }
  }

  // ── Background download ──────────────────────────────────────────────────

  static Future<void> startBackgroundDownload({
    required UpdateInfo info,
    required String accessToken,
    BuildContext? context,
  }) async {
    _lastNotifPercent = -1;
    _pendingApkPath = null;
    await _showProgress(0, 0.0, info.sizeMb, null);

    final startTime = DateTime.now();

    try {
      final path = await _downloadApk(
        downloadUrl: info.downloadUrl,
        accessToken: accessToken,
        onProgress: (fraction) async {
          final percent = (fraction * 100).toInt();
          if (percent - _lastNotifPercent < 3 && percent < 99) return;
          _lastNotifPercent = percent;

          double? bytesPerSec;
          final elapsed = DateTime.now().difference(startTime).inSeconds;
          if (elapsed > 0 && info.sizeMb != null) {
            bytesPerSec = (fraction * info.sizeMb! * 1024 * 1024) / elapsed;
          }
          await _showProgress(percent, fraction, info.sizeMb, bytesPerSec);
        },
      );

      _pendingApkPath = path;
      await _showComplete(info.version);

      if (context != null && context.mounted) {
        await _showInstallDialog(context, info.version, path);
      }
    } catch (_) {
      await _plugin.cancel(_kNotifId);
    }
  }

  // ── Notifications ────────────────────────────────────────────────────────

  static Future<void> _showProgress(
    int percent,
    double fraction,
    double? sizeMb,
    double? bytesPerSec,
  ) async {
    String body;
    if (sizeMb != null) {
      final downloaded = (fraction * sizeMb).toStringAsFixed(1);
      body = '$downloaded / ${sizeMb.toStringAsFixed(1)} MB';
    } else {
      body = '$percent%';
    }
    if (bytesPerSec != null && bytesPerSec > 0 && fraction < 0.99 && sizeMb != null) {
      final remainingSec = ((1 - fraction) * sizeMb * 1024 * 1024) / bytesPerSec;
      final etaStr = remainingSec < 60
          ? '${remainingSec.toInt()}s left'
          : '${(remainingSec / 60).toInt()}m ${(remainingSec % 60).toInt()}s left';
      body += ' · $etaStr';
    }

    await _plugin.show(
      _kNotifId,
      'Downloading update  $percent%',
      body,
      NotificationDetails(
        android: AndroidNotificationDetails(
          _kChannelId,
          'App Updates',
          channelDescription: 'App update download progress',
          importance: Importance.low,
          priority: Priority.low,
          showProgress: true,
          maxProgress: 100,
          progress: percent,
          ongoing: true,
          onlyAlertOnce: true,
          playSound: false,
          enableVibration: false,
        ),
      ),
    );
  }

  static Future<void> _showComplete(String version) async {
    await _plugin.show(
      _kNotifId,
      'Update v$version ready',
      'Tap to install',
      const NotificationDetails(
        android: AndroidNotificationDetails(
          _kChannelId,
          'App Updates',
          channelDescription: 'App update download progress',
          importance: Importance.high,
          priority: Priority.high,
          ongoing: false,
          playSound: true,
        ),
      ),
    );
  }

  // ── Install dialog ───────────────────────────────────────────────────────

  static Future<void> _showInstallDialog(
    BuildContext context,
    String version,
    String apkPath,
  ) async {
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('v$version ready to install'),
        content: const Text('The update has been downloaded. Install now?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Later'),
          ),
          ElevatedButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await installApk(apkPath);
            },
            child: const Text('Install Now'),
          ),
        ],
      ),
    );
  }

  // ── Download / Install ───────────────────────────────────────────────────

  static Future<String> _downloadApk({
    required String downloadUrl,
    required String accessToken,
    required void Function(double) onProgress,
  }) async {
    final request = http.Request('GET', Uri.parse(downloadUrl));
    request.headers['Authorization'] = 'Bearer $accessToken';

    final client = http.Client();
    try {
      final streamed = await client.send(request);
      final total = streamed.contentLength ?? 0;
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/ims_update.apk');
      final sink = file.openWrite();
      int received = 0;
      await for (final chunk in streamed.stream) {
        sink.add(chunk);
        received += chunk.length;
        if (total > 0) onProgress(received / total);
      }
      await sink.close();
      return file.path;
    } finally {
      client.close();
    }
  }

  static Future<bool> installApk(String filePath) async {
    try {
      final canInstall =
          await _kInstallChannel.invokeMethod<bool>('canInstallPackages') ?? true;
      if (!canInstall) {
        await _kInstallChannel.invokeMethod('openInstallSettings');
        await _showPermissionRequiredNotification();
        return false;
      }
      await _kInstallChannel.invokeMethod<void>('install', {'path': filePath});
      return true;
    } on MissingPluginException {
      // Channel unavailable — fall back to open_file.
    } catch (_) {
      // install method threw — fall back to open_file.
    }
    await OpenFile.open(filePath, type: 'application/vnd.android.package-archive');
    return true;
  }

  static Future<void> _showPermissionRequiredNotification() async {
    await _plugin.show(
      _kNotifId,
      'Permission required',
      'Enable "Install unknown apps" for this app in Settings, then tap here to install.',
      const NotificationDetails(
        android: AndroidNotificationDetails(
          _kChannelId,
          'App Updates',
          channelDescription: 'App update download progress',
          importance: Importance.high,
          priority: Priority.high,
          ongoing: false,
          playSound: true,
        ),
      ),
    );
  }
}
