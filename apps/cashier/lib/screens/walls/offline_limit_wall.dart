import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/inventory_feed_model.dart';
import '../../services/debug_log.dart';
import '../../services/session_store.dart';

class OfflineLimitWall extends StatefulWidget {
  const OfflineLimitWall({super.key, required this.onRetry, required this.onSignOut});

  final Future<void> Function() onRetry;
  final Future<void> Function() onSignOut;

  @override
  State<OfflineLimitWall> createState() => _OfflineLimitWallState();
}

class _OfflineLimitWallState extends State<OfflineLimitWall> {
  bool _retrying = false;
  // Only used when kDebugMode is true; release builds short-circuit the diag UI.
  bool _showDiag = false;
  String? _lastSyncIso;
  int? _elapsedMin;
  int? _maxMin;
  String? _baseUrl;

  @override
  void initState() {
    super.initState();
    _loadDiag();
  }

  Future<void> _loadDiag() async {
    final iso = await SessionStore.getLastSyncIso();
    final max = await SessionStore.getMaxOfflineMinutes();
    final session = await SessionStore.load();
    int? elapsed;
    if (iso != null && iso.isNotEmpty) {
      final parsed = DateTime.tryParse(iso);
      if (parsed != null) {
        elapsed = DateTime.now().difference(parsed.toLocal()).inMinutes;
      }
    }
    if (!mounted) return;
    setState(() {
      _lastSyncIso = iso;
      _maxMin = max;
      _elapsedMin = elapsed;
      _baseUrl = session?.baseUrl;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final feedError = context.watch<InventoryFeedModel>().error;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 40),
              const Icon(Icons.cloud_off_rounded, size: 64, color: Colors.orange),
              const SizedBox(height: 24),
              Text(
                'Connection required',
                style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                'This device has been offline for too long. Please connect to the server to continue using the app.',
                style: theme.textTheme.bodyMedium?.copyWith(color: Colors.grey[600]),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _retrying
                    ? null
                    : () async {
                        setState(() => _retrying = true);
                        await widget.onRetry();
                        await _loadDiag();
                        if (mounted) setState(() => _retrying = false);
                      },
                icon: _retrying
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.refresh_rounded),
                label: Text(_retrying ? 'Connecting…' : 'Retry connection'),
              ),
              const SizedBox(height: 8),
              TextButton.icon(
                onPressed: _retrying ? null : () => widget.onSignOut(),
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Sign out'),
              ),
              if (kDebugMode) ...[
                const SizedBox(height: 8),
                TextButton.icon(
                  onPressed: () => setState(() => _showDiag = !_showDiag),
                  icon: Icon(_showDiag ? Icons.expand_less : Icons.bug_report_outlined),
                  label: Text(_showDiag ? 'Hide diagnostics' : 'Show diagnostics'),
                ),
              ],
              if (kDebugMode && _showDiag) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.grey[100],
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.grey[300]!),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _DiagRow(label: 'Base URL', value: _baseUrl ?? '(none)'),
                      _DiagRow(label: 'Last sync', value: _lastSyncIso ?? '(never)'),
                      _DiagRow(
                        label: 'Elapsed',
                        value: _elapsedMin == null ? '—' : '${_elapsedMin}m / ${_maxMin}m limit',
                      ),
                      _DiagRow(label: 'Last error', value: feedError ?? '(none)'),
                      const SizedBox(height: 8),
                      Text('Recent log', style: theme.textTheme.labelMedium),
                      const SizedBox(height: 4),
                      Container(
                        padding: const EdgeInsets.all(8),
                        color: Colors.black,
                        child: Text(
                          DebugLog.tail(25).join('\n'),
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 10,
                            color: Colors.greenAccent,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _DiagRow extends StatelessWidget {
  const _DiagRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: RichText(
        text: TextSpan(
          style: const TextStyle(fontSize: 12, color: Colors.black87, fontFamily: 'monospace'),
          children: [
            TextSpan(text: '$label: ', style: const TextStyle(fontWeight: FontWeight.bold)),
            TextSpan(text: value),
          ],
        ),
      ),
    );
  }
}
