import 'package:flutter/material.dart';

import '../admin_tokens.dart';
import '../models/stock_alert.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/section_header.dart';

class StockAlertsScreen extends StatefulWidget {
  const StockAlertsScreen({super.key});

  @override
  State<StockAlertsScreen> createState() => _StockAlertsScreenState();
}

class _StockAlertsScreenState extends State<StockAlertsScreen> {
  bool _loading = true;
  String? _error;
  List<StockAlert> _alerts = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) {
        if (mounted) Navigator.of(context).pop();
        return;
      }
      final api = AdminApi(session.baseUrl, session.token);
      final alerts = await api.getStockAlerts();
      if (!mounted) return;
      setState(() { _alerts = alerts; _loading = false; });
    } on ApiException catch (e) {
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (_) {
      if (mounted) setState(() { _error = 'Connection error. Pull to refresh.'; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Stock Alerts')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.cloud_off_rounded, size: 48, color: AdminColors.onSurfaceVariant),
                        const SizedBox(height: 12),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh_rounded),
                          label: const Text('Retry'),
                        ),
                      ],
                    ),
                  )
                : _alerts.isEmpty
                    ? ListView(children: [
                        SizedBox(
                          height: 300,
                          child: Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.check_circle_outline_rounded,
                                    size: 56, color: const Color(0xFF1A6B3C)),
                                const SizedBox(height: 12),
                                Text(
                                  'All stock levels are healthy',
                                  style: theme.textTheme.titleMedium?.copyWith(
                                    color: AdminColors.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ])
                    : CustomScrollView(
                        slivers: [
                          SliverPadding(
                            padding: const EdgeInsets.fromLTRB(
                              AdminSpacing.gutter, AdminSpacing.lg,
                              AdminSpacing.gutter, 0,
                            ),
                            sliver: SliverToBoxAdapter(
                              child: SectionHeader(
                                label: '${_alerts.length} product${_alerts.length == 1 ? '' : 's'}',
                                title: 'Low Stock',
                              ),
                            ),
                          ),
                          SliverPadding(
                            padding: const EdgeInsets.fromLTRB(
                              AdminSpacing.gutter, AdminSpacing.md,
                              AdminSpacing.gutter, 80,
                            ),
                            sliver: SliverList.separated(
                              itemCount: _alerts.length,
                              separatorBuilder: (context, index) => const SizedBox(height: AdminSpacing.sm),
                              itemBuilder: (_, i) => _AlertTile(alert: _alerts[i]),
                            ),
                          ),
                        ],
                      ),
      ),
    );
  }
}

class _AlertTile extends StatelessWidget {
  const _AlertTile({required this.alert});
  final StockAlert alert;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isOut = alert.isOutOfStock;
    final borderColor = isOut ? AdminColors.error : const Color(0xFFE65100);
    final bgColor = isOut ? AdminColors.errorContainer : const Color(0xFFFFF3E0);
    final labelColor = isOut ? AdminColors.onErrorContainer : const Color(0xFFBF360C);

    return Container(
      decoration: BoxDecoration(
        color: AdminColors.card,
        borderRadius: BorderRadius.circular(AdminRadius.quickTile),
        border: Border(left: BorderSide(color: borderColor, width: 4)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AdminSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(alert.name, style: theme.textTheme.titleMedium),
                  Text(
                    '${alert.sku} · ${alert.shopName}',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: AdminColors.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: bgColor,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                isOut ? 'Out of stock' : '${alert.quantity} / min. ${alert.threshold}',
                style: theme.textTheme.labelMedium?.copyWith(
                  color: labelColor,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
