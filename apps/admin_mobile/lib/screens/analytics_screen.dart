import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../admin_tokens.dart';
import '../models/analytics.dart';
import '../models/currency.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/metric_card.dart';
import '../widgets/revenue_bar_chart.dart';
import '../widgets/section_header.dart';
import 'app_shell.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key, required this.onLogout});

  final VoidCallback onLogout;

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  int _days = 7;
  bool _loading = true;
  String? _error;
  AnalyticsSummary? _summary;
  List<SalesPoint> _series = [];
  List<CategoryItem> _categories = [];
  List<TopProduct> _topProducts = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { widget.onLogout(); return; }
      final api = AdminApi(session.baseUrl, session.token);
      final results = await Future.wait([
        api.getAnalyticsSummary(days: _days),
        api.getSalesSeries(days: _days),
        api.getCategoryRevenue(days: _days),
        api.getTopProducts(days: _days, limit: 5),
      ]);
      if (!mounted) return;
      setState(() {
        _summary = results[0] as AnalyticsSummary;
        _series = (results[1] as List).cast<SalesPoint>();
        _categories = (results[2] as List).cast<CategoryItem>();
        _topProducts = (results[3] as List).cast<TopProduct>();
        _loading = false;
      });
    } on ApiException catch (e) {
      if (e.statusCode == 401) { await SessionStore.clearLogin(); if (mounted) widget.onLogout(); return; }
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = 'Connection error'; _loading = false; });
    }
  }


  String _formatDelta(double? pct) {
    if (pct == null) return '';
    final sign = pct >= 0 ? '+' : '';
    return '$sign${pct.toStringAsFixed(1)}%';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final currency = context.watch<CurrencyModel>();
    final summary = _summary;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Analytics'),
        actions: [
          IconButton(
            onPressed: () => showLogoutDialog(context, widget.onLogout),
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Sign out',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          slivers: [
            // Period selector
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(
                AdminSpacing.gutter, AdminSpacing.md, AdminSpacing.gutter, 0,
              ),
              sliver: SliverToBoxAdapter(
                child: SegmentedButton<int>(
                  segments: const [
                    ButtonSegment(value: 7, label: Text('7 days')),
                    ButtonSegment(value: 30, label: Text('30 days')),
                    ButtonSegment(value: 90, label: Text('90 days')),
                  ],
                  selected: {_days},
                  onSelectionChanged: (s) {
                    setState(() => _days = s.first);
                    _load();
                  },
                ),
              ),
            ),

            if (_loading)
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.all(48),
                  child: Center(child: CircularProgressIndicator()),
                ),
              )
            else if (_error != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(AdminSpacing.gutter),
                  child: Column(
                    children: [
                      const SizedBox(height: 24),
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
                ),
              )
            else ...[
              // KPI horizontal scroll
              SliverToBoxAdapter(
                child: SizedBox(
                  height: 140,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(
                      AdminSpacing.gutter, AdminSpacing.lg, AdminSpacing.gutter, 0,
                    ),
                    scrollDirection: Axis.horizontal,
                    children: [
                      SizedBox(
                        width: 160,
                        child: AdminMetricCard(
                          title: 'Revenue',
                          value: summary != null ? currency.formatAbbreviated(summary.grossCents) : '--',
                          icon: Icons.attach_money_rounded,
                          trend: summary != null ? _formatDelta(summary.deltaPct) : null,
                          trendPositive: summary != null && (summary.deltaPct ?? 0) >= 0,
                        ),
                      ),
                      const SizedBox(width: AdminSpacing.sm),
                      SizedBox(
                        width: 160,
                        child: AdminMetricCard(
                          title: 'Avg. Ticket',
                          value: summary != null ? currency.formatAbbreviated(summary.avgTicketCents) : '--',
                          icon: Icons.confirmation_number_outlined,
                        ),
                      ),
                      const SizedBox(width: AdminSpacing.sm),
                      SizedBox(
                        width: 160,
                        child: AdminMetricCard(
                          title: 'Transactions',
                          value: summary != null ? '${summary.transactionCount}' : '--',
                          icon: Icons.swap_horiz_rounded,
                        ),
                      ),
                      const SizedBox(width: AdminSpacing.sm),
                      SizedBox(
                        width: 160,
                        child: AdminMetricCard(
                          title: 'Stock Alerts',
                          value: summary != null ? '${summary.stockAlertCount}' : '--',
                          icon: Icons.warning_amber_rounded,
                          trendPositive: summary != null && summary.stockAlertCount == 0,
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              // Revenue bar chart
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(
                  AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, 0,
                ),
                sliver: SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SectionHeader(
                        label: '$_days-day trend',
                        title: 'Revenue',
                      ),
                      const SizedBox(height: AdminSpacing.md),
                      Container(
                        padding: const EdgeInsets.all(AdminSpacing.md),
                        decoration: BoxDecoration(
                          color: AdminColors.card,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                        ),
                        child: RevenueBarChart(
                          points: _series,
                          formatValue: currency.formatAbbreviated,
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              // Top categories
              if (_categories.isNotEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(
                    AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, 0,
                  ),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SectionHeader(label: 'By category', title: 'Top Categories'),
                        const SizedBox(height: AdminSpacing.md),
                        Material(
                          color: AdminColors.card,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                          child: Column(
                            children: _categories.asMap().entries.map((entry) {
                              final i = entry.key;
                              final cat = entry.value;
                              final isLast = i == _categories.length - 1;
                              return Column(
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: AdminSpacing.md,
                                      vertical: AdminSpacing.sm,
                                    ),
                                    child: Row(
                                      children: [
                                        Container(
                                          width: 8,
                                          height: 8,
                                          decoration: BoxDecoration(
                                            color: AdminColors.primary.withValues(
                                              alpha: 1.0 - (i * 0.15).clamp(0.0, 0.7),
                                            ),
                                            shape: BoxShape.circle,
                                          ),
                                        ),
                                        const SizedBox(width: AdminSpacing.sm),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(cat.category, style: theme.textTheme.titleMedium),
                                              Text(
                                                '${cat.transactionCount} sales · ${cat.pct.toStringAsFixed(1)}% of revenue',
                                                style: theme.textTheme.bodySmall?.copyWith(
                                                  color: AdminColors.onSurfaceVariant,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        Text(
                                          currency.formatAbbreviated(cat.grossCents),
                                          style: theme.textTheme.titleMedium?.copyWith(
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  if (!isLast)
                                    Divider(
                                      height: 1,
                                      indent: AdminSpacing.md,
                                      endIndent: AdminSpacing.md,
                                      color: AdminColors.outlineVariant.withValues(alpha: 0.4),
                                    ),
                                ],
                              );
                            }).toList(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

              // Top products
              if (_topProducts.isNotEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(
                    AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, AdminSpacing.xl,
                  ),
                  sliver: SliverToBoxAdapter(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SectionHeader(label: 'Best sellers', title: 'Top Products'),
                        const SizedBox(height: AdminSpacing.md),
                        Material(
                          color: AdminColors.card,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                          child: Column(
                            children: _topProducts.asMap().entries.map((entry) {
                              final i = entry.key;
                              final prod = entry.value;
                              final isLast = i == _topProducts.length - 1;
                              return Column(
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: AdminSpacing.md,
                                      vertical: AdminSpacing.sm,
                                    ),
                                    child: Row(
                                      children: [
                                        SizedBox(
                                          width: 24,
                                          child: Text(
                                            '#${i + 1}',
                                            style: theme.textTheme.labelMedium?.copyWith(
                                              color: i == 0 ? AdminColors.primary : AdminColors.onSurfaceVariant,
                                              fontWeight: FontWeight.bold,
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: AdminSpacing.sm),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(prod.productName, style: theme.textTheme.titleMedium),
                                              Text(
                                                '${prod.sku} · ${prod.qtySold} sold',
                                                style: theme.textTheme.bodySmall?.copyWith(
                                                  color: AdminColors.onSurfaceVariant,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        Text(
                                          currency.formatAbbreviated(prod.grossCents),
                                          style: theme.textTheme.titleMedium?.copyWith(
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  if (!isLast)
                                    Divider(
                                      height: 1,
                                      indent: AdminSpacing.md + 24 + AdminSpacing.sm,
                                      endIndent: AdminSpacing.md,
                                      color: AdminColors.outlineVariant.withValues(alpha: 0.4),
                                    ),
                                ],
                              );
                            }).toList(),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
