import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
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

  static Future<UpdateInfo?> checkForUpdate({
    required String baseUrl,
    required String accessToken,
    required String appName,
    bool useAdminEndpoint = false,
  }) async {
    try {
      final trimmedBase =
          baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
      final path = useAdminEndpoint ? '/v1/admin/apps/update-check' : '/v1/apps/update-check';
      final uri = Uri.parse('$trimmedBase$path')
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

  static Future<String> downloadApk({
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

  static Future<void> installApk(String filePath) async {
    await OpenFile.open(filePath, type: 'application/vnd.android.package-archive');
  }
}


// ── Update dialog ─────────────────────────────────────────────────────────────

Future<void> showUpdateDialog(
  BuildContext context,
  UpdateInfo info,
  String accessToken,
) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _UpdateDialog(info: info, accessToken: accessToken),
  );
}

enum _Phase { prompt, downloading, done, error }

class _UpdateDialog extends StatefulWidget {
  const _UpdateDialog({required this.info, required this.accessToken});
  final UpdateInfo info;
  final String accessToken;

  @override
  State<_UpdateDialog> createState() => _UpdateDialogState();
}

class _UpdateDialogState extends State<_UpdateDialog> {
  _Phase _phase = _Phase.prompt;
  double _progress = 0;
  String? _errorMessage;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _phase == _Phase.prompt || _phase == _Phase.error,
      child: AlertDialog(
        title: Text('Update available  v${widget.info.version}'),
        content: _buildContent(),
        actions: _buildActions(),
      ),
    );
  }

  Widget _buildContent() {
    switch (_phase) {
      case _Phase.prompt:
        final sizePart = widget.info.sizeMb != null
            ? '${widget.info.sizeMb!.toStringAsFixed(1)} MB'
            : '';
        final changelog = widget.info.changelog ?? '';
        final detail = [sizePart, changelog].where((s) => s.isNotEmpty).join(' · ');
        return Text(
          detail.isEmpty ? 'A new version is ready to install.' : detail,
          style: const TextStyle(fontSize: 13),
        );
      case _Phase.downloading:
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            LinearProgressIndicator(value: _progress > 0 ? _progress : null),
            const SizedBox(height: 8),
            Text('${(_progress * 100).toStringAsFixed(0)}%  Downloading…'),
          ],
        );
      case _Phase.done:
        return const Text('Installing…');
      case _Phase.error:
        return Text(_errorMessage ?? 'Download failed. Please try again later.');
    }
  }

  List<Widget>? _buildActions() {
    switch (_phase) {
      case _Phase.prompt:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Later'),
          ),
          ElevatedButton(
            onPressed: _startDownload,
            child: const Text('Update Now'),
          ),
        ];
      case _Phase.downloading:
      case _Phase.done:
        return null;
      case _Phase.error:
        return [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Dismiss'),
          ),
        ];
    }
  }

  Future<void> _startDownload() async {
    setState(() => _phase = _Phase.downloading);
    try {
      final path = await UpdateService.downloadApk(
        downloadUrl: widget.info.downloadUrl,
        accessToken: widget.accessToken,
        onProgress: (p) {
          if (mounted) setState(() => _progress = p);
        },
      );
      if (!mounted) return;
      setState(() => _phase = _Phase.done);
      await UpdateService.installApk(path);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _phase = _Phase.error;
        _errorMessage = 'Download failed. Please try again later.';
      });
    }
  }
}
