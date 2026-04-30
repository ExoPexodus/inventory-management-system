import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../cashier_tokens.dart';
import '../models/sync_state_model.dart';
import '../services/authenticated_api.dart';
import '../services/inventory_api.dart';
import '../services/outbox_service.dart';
import '../services/policy_store.dart';
import '../services/session_store.dart';
import '../util/datetime_format.dart';
import '../widgets/metric_card.dart';

class SyncStatusScreen extends StatefulWidget {
  const SyncStatusScreen({super.key});

  @override
  State<SyncStatusScreen> createState() => _SyncStatusScreenState();
}

class _SyncStatusScreenState extends State<SyncStatusScreen> {
  bool _flushing = false;
  String _connectivity = 'checking...';
  String _shopTimezone = 'UTC';

  @override
  void initState() {
    super.initState();
    _refreshConnectivity();
    PolicyStore.getShopTimezone().then((tz) {
      if (mounted) setState(() => _shopTimezone = tz);
    });
  }

  Future<void> _refreshConnectivity() async {
    final r = await Connectivity().checkConnectivity();
    final hasTransport = r.any((e) =>
        e == ConnectivityResult.mobile ||
        e == ConnectivityResult.wifi ||
        e == ConnectivityResult.ethernet);
    if (!hasTransport) {
      if (!mounted) return;
      setState(() => _connectivity = 'offline');
      return;
    }
    final s = await SessionStore.load();
    if (s == null) {
      if (!mounted) return;
      setState(() => _connectivity = 'no session');
      return;
    }
    final api = InventoryApi(s.baseUrl);
    final reachable = await api.ping(timeoutMs: 2500);
    if (!mounted) return;
    setState(() => _connectivity = reachable ? 'online' : 'server unreachable');
  }

  Future<void> _flushNow() async {
    if (_flushing) return;
    setState(() => _flushing = true);
    try {
      final sync = context.read<SyncStateModel>();
      final auth = context.read<AuthenticatedApi>();
      await OutboxService.flush(auth, sync);
      await sync.refreshFromStorage();
      await _refreshConnectivity();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Sync attempt completed')),
      );
    } finally {
      if (mounted) setState(() => _flushing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final sync = context.watch<SyncStateModel>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sync status'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(CashierSpacing.gutter),
        children: [
          CashierMetricCard(
            title: 'Connectivity',
            value: _connectivity,
            icon: Icons.wifi_tethering_rounded,
            onTap: _refreshConnectivity,
          ),
          const SizedBox(height: CashierSpacing.sm),
          CashierMetricCard(
            title: 'Last sync',
            value: sync.lastSyncIso == null
                ? 'Never'
                : formatShortLocalDateTime(sync.lastSyncIso!, shopTimezone: _shopTimezone),
            icon: Icons.schedule_rounded,
          ),
          const SizedBox(height: CashierSpacing.sm),
          CashierMetricCard(
            title: 'Pending outbox events',
            value: '${sync.pendingOutboxCount}',
            icon: Icons.cloud_queue_outlined,
          ),
          if (sync.pendingOutboxCount > 0 && sync.lastOutboxFailure != null) ...[
            const SizedBox(height: CashierSpacing.sm),
            Material(
              color: CashierColors.errorContainer.withValues(alpha: 0.85),
              borderRadius: BorderRadius.circular(CashierRadius.quickTile),
              child: Padding(
                padding: const EdgeInsets.all(CashierSpacing.md),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.cloud_off_rounded, color: CashierColors.onErrorContainer),
                    const SizedBox(width: CashierSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${sync.pendingOutboxCount} event${sync.pendingOutboxCount == 1 ? '' : 's'} waiting to sync',
                            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                  color: CashierColors.onErrorContainer,
                                  fontWeight: FontWeight.bold,
                                ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            sync.lastOutboxFailure!,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                  color: CashierColors.onErrorContainer,
                                ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ] else if (sync.lastOutboxFailure != null) ...[
            const SizedBox(height: CashierSpacing.sm),
            Material(
              color: CashierColors.errorContainer.withValues(alpha: 0.65),
              borderRadius: BorderRadius.circular(CashierRadius.quickTile),
              child: Padding(
                padding: const EdgeInsets.all(CashierSpacing.md),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.error_outline, color: CashierColors.onErrorContainer),
                    const SizedBox(width: CashierSpacing.sm),
                    Expanded(
                      child: Text(
                        sync.lastOutboxFailure!,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: CashierColors.onErrorContainer,
                            ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
          const SizedBox(height: CashierSpacing.lg),
          FilledButton.icon(
            onPressed: _flushing ? null : _flushNow,
            icon: _flushing
                ? const SizedBox(
                    height: 16,
                    width: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.sync_rounded),
            label: const Text('Sync now'),
          ),
        ],
      ),
    );
  }
}
