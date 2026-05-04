import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'package:provider/provider.dart';

import '../admin_tokens.dart';
import '../models/analytics.dart';
import '../models/currency.dart';
import 'stock_alerts_screen.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/metric_card.dart';
import '../widgets/pin_setup_sheet.dart';
import '../widgets/revenue_bar_chart.dart';
import '../widgets/section_header.dart';
import 'app_shell.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.onNavigateToPurchases,
    required this.onLogout,
  });

  final VoidCallback onNavigateToPurchases;
  final VoidCallback onLogout;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _loading = true;
  String? _error;
  AnalyticsSummary? _summary;
  List<SalesPoint> _series = [];
  String _email = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final session = await SessionStore.load();
      if (session == null) {
        widget.onLogout();
        return;
      }
      _email = session.email;
      final api = AdminApi(session.baseUrl, session.token);
      final results = await Future.wait([
        api.getAnalyticsSummary(days: 7),
        api.getSalesSeries(days: 7),
      ]);
      if (!mounted) return;
      setState(() {
        _summary = results[0] as AnalyticsSummary;
        _series = (results[1] as List).cast<SalesPoint>();
        _loading = false;
      });
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        await SessionStore.clearLogin();
        if (mounted) widget.onLogout();
        return;
      }
      if (mounted) setState(() { _error = 'Failed to load data (${e.statusCode})'; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = 'Connection error. Pull to refresh.'; _loading = false; });
    }
  }

  Future<void> _showManagePinDialog() async {
    final session = await SessionStore.load();
    if (session == null || !mounted) return;
    final hasPin = await SessionStore.isPinEnabled();
    if (!mounted) return;
    final action = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Manage PIN'),
        content: Text(hasPin
            ? 'Quick-unlock PIN is enabled on this device.'
            : 'You haven\'t set a PIN on this device yet.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, null),
            child: const Text('Close'),
          ),
          if (hasPin)
            TextButton(
              onPressed: () => Navigator.pop(ctx, 'reset'),
              child: const Text('Clear PIN'),
            ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, 'set'),
            child: Text(hasPin ? 'Change PIN' : 'Set PIN'),
          ),
        ],
      ),
    );
    if (action == null || !mounted) return;
    final api = AdminApi(session.baseUrl, session.token);
    if (action == 'reset') {
      try {
        await api.resetPin();
        await SessionStore.setPinEnabled(false);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('PIN cleared')),
          );
        }
      } catch (_) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not clear PIN')),
          );
        }
      }
      return;
    }
    if (action == 'set') {
      final pin = await showModalBottomSheet<String>(
        context: context,
        isScrollControlled: true,
        isDismissible: true,
        builder: (ctx) => const PinSetupSheet(
          title: 'Choose a PIN',
          subtitle: 'Use 4–8 digits. Remember it — you\'ll use it to sign in.',
          cancelLabel: 'Cancel',
        ),
      );
      if (pin == null || pin.isEmpty || !mounted) return;
      try {
        await api.setPin(pin);
        await SessionStore.setPinEnabled(true);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('PIN saved')),
          );
        }
      } catch (_) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not save PIN')),
          );
        }
      }
    }
  }

  String _formatDelta(double? pct) {
    if (pct == null) return '';
    final sign = pct >= 0 ? '+' : '';
    return '$sign${pct.toStringAsFixed(1)}%';
  }

  String get _greeting {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  }

  String get _emailPrefix => _email.split('@').first;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final currency = context.watch<CurrencyModel>();
    final today = DateFormat('EEEE, MMMM d, y').format(DateTime.now());
    final summary = _summary;
    final recentSeries = _series;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          slivers: [
            // Hero header
            SliverToBoxAdapter(
              child: Container(
                decoration: const BoxDecoration(gradient: AdminHeroGradient.archive),
                padding: EdgeInsets.only(
                  top: MediaQuery.of(context).padding.top + AdminSpacing.md,
                  left: AdminSpacing.gutter,
                  right: AdminSpacing.gutter,
                  bottom: AdminSpacing.xl,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 20,
                          backgroundColor: Colors.white.withValues(alpha: 0.15),
                          child: Text(
                            _emailPrefix.isNotEmpty ? _emailPrefix[0].toUpperCase() : 'A',
                            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                          ),
                        ),
                        const SizedBox(width: AdminSpacing.sm),
                        Expanded(
                          child: Text(
                            'Admin',
                            style: theme.textTheme.titleMedium?.copyWith(color: Colors.white),
                          ),
                        ),
                        PopupMenuButton<String>(
                          icon: const Icon(Icons.more_vert_rounded, color: Colors.white70),
                          tooltip: 'Account',
                          onSelected: (v) {
                            if (v == 'logout') {
                              showLogoutDialog(context, widget.onLogout);
                            } else if (v == 'pin') {
                              _showManagePinDialog();
                            }
                          },
                          itemBuilder: (ctx) => const [
                            PopupMenuItem(
                              value: 'pin',
                              child: ListTile(
                                leading: Icon(Icons.pin_outlined),
                                title: Text('Manage PIN'),
                                dense: true,
                              ),
                            ),
                            PopupMenuItem(
                              value: 'logout',
                              child: ListTile(
                                leading: Icon(Icons.logout_rounded),
                                title: Text('Sign out'),
                                dense: true,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: AdminSpacing.lg),
                    Text(
                      '$_greeting, $_emailPrefix',
                      style: theme.textTheme.headlineSmall?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      today,
                      style: theme.textTheme.bodySmall?.copyWith(color: Colors.white60),
                    ),
                  ],
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
                      Text(_error!, textAlign: TextAlign.center, style: theme.textTheme.bodyMedium),
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
              // KPI grid
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(
                  AdminSpacing.gutter, AdminSpacing.lg, AdminSpacing.gutter, 0,
                ),
                sliver: SliverGrid.count(
                  crossAxisCount: 2,
                  mainAxisSpacing: AdminSpacing.sm,
                  crossAxisSpacing: AdminSpacing.sm,
                  childAspectRatio: 1.35,
                  children: [
                    AdminMetricCard(
                      title: 'Revenue (7d)',
                      value: summary != null
                          ? currency.formatAbbreviated(summary.grossCents)
                          : '--',
                      icon: Icons.attach_money_rounded,
                      trend: summary != null && summary.deltaPct != null
                          ? _formatDelta(summary.deltaPct)
                          : null,
                      trendPositive:
                          summary != null && (summary.deltaPct ?? 0) >= 0,
                    ),
                    AdminMetricCard(
                      title: 'Transactions (7d)',
                      value: summary != null
                          ? '${summary.transactionCount}'
                          : '--',
                      icon: Icons.swap_horiz_rounded,
                    ),
                    AdminMetricCard(
                      title: 'Pending POs',
                      value: summary != null
                          ? '${summary.pendingOrderCount}'
                          : '--',
                      icon: Icons.shopping_bag_outlined,
                      onTap: widget.onNavigateToPurchases,
                    ),
                    AdminMetricCard(
                      title: 'Stock Alerts',
                      value: summary != null
                          ? '${summary.stockAlertCount}'
                          : '--',
                      icon: Icons.warning_amber_rounded,
                      trendPositive: summary != null &&
                          summary.stockAlertCount == 0,
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => const StockAlertsScreen(),
                        ),
                      ),
                    ),
                  ],
                ),
              ),

              // Revenue trend chart
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(
                  AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, 0,
                ),
                sliver: SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SectionHeader(
                        label: 'Last 7 days',
                        title: 'Revenue Trend',
                      ),
                      const SizedBox(height: AdminSpacing.md),
                      Container(
                        padding: const EdgeInsets.all(AdminSpacing.md),
                        decoration: BoxDecoration(
                          color: AdminColors.card,
                          borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                        ),
                        child: RevenueBarChart(
                          points: recentSeries,
                          formatValue: currency.formatAbbreviated,
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              // Quick actions
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(
                  AdminSpacing.gutter, AdminSpacing.xl, AdminSpacing.gutter, AdminSpacing.xl,
                ),
                sliver: SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SectionHeader(label: 'Jump to', title: 'Quick Actions'),
                      const SizedBox(height: AdminSpacing.md),
                      _QuickActionTile(
                        icon: Icons.shopping_bag_outlined,
                        title: 'Purchase Orders',
                        subtitle: summary != null &&
                                summary.pendingOrderCount > 0
                            ? '${summary.pendingOrderCount} pending'
                            : 'View and manage orders',
                        onTap: widget.onNavigateToPurchases,
                      ),
                      const SizedBox(height: AdminSpacing.sm),
                      _QuickActionTile(
                        icon: Icons.warning_amber_rounded,
                        title: 'Inventory Alerts',
                        subtitle: summary != null
                            ? '${summary.stockAlertCount} product${summary.stockAlertCount == 1 ? '' : 's'} low on stock'
                            : 'Check stock levels',
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const StockAlertsScreen(),
                          ),
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

class _QuickActionTile extends StatelessWidget {
  const _QuickActionTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: AdminColors.card,
      borderRadius: BorderRadius.circular(AdminRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AdminSpacing.md,
            vertical: AdminSpacing.md,
          ),
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: AdminColors.primary.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(AdminRadius.chip),
                ),
                child: Icon(icon, size: 20, color: AdminColors.primary),
              ),
              const SizedBox(width: AdminSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: theme.textTheme.titleMedium),
                    Text(
                      subtitle,
                      style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right_rounded, color: AdminColors.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}
