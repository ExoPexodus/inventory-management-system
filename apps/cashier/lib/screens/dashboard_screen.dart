import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../cashier_tokens.dart';
import '../models/cart_model.dart';
import '../models/inventory_feed_model.dart';
import '../models/sync_state_model.dart';
import '../services/inventory_api.dart';
import '../services/session_store.dart';
import '../util/datetime_format.dart';
import '../util/money_format.dart';
import '../widgets/archive_section_header.dart';
import '../widgets/cashier_hero.dart';
import '../widgets/compact_transaction_row.dart';
import '../widgets/gradient_primary_button.dart';
import '../widgets/metric_card.dart';
import '../widgets/quick_access_tile.dart';
import 'shift_close_dialog.dart';
import 'shift_open_dialog.dart';
import 'sync_status_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({
    super.key,
    required this.onLoggedOut,
    required this.onGoLookup,
    required this.onGoCart,
    required this.onGoHistory,
  });

  final VoidCallback onLoggedOut;
  final void Function(String? query) onGoLookup;
  final VoidCallback onGoCart;
  final VoidCallback onGoHistory;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _search = TextEditingController();
  String _connectivity = 'Checking...';
  List<Map<String, dynamic>> _recentTx = [];
  Map<String, dynamic>? _shift;
  Map<String, dynamic>? _activeShift;
  bool _dashLoading = false;

  @override
  void initState() {
    super.initState();
    _refreshNet();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadDashData();
    });
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _refreshNet() async {
    final r = await Connectivity().checkConnectivity();
    final hasTransport = r.any((e) =>
        e == ConnectivityResult.mobile ||
        e == ConnectivityResult.wifi ||
        e == ConnectivityResult.ethernet);
    if (!hasTransport) {
      if (!mounted) return;
      setState(() => _connectivity = 'No internet');
      return;
    }
    final s = await SessionStore.load();
    if (s == null) {
      if (!mounted) return;
      setState(() => _connectivity = 'No session');
      return;
    }
    final api = InventoryApi(s.baseUrl);
    final reachable = await api.ping(timeoutMs: 2500);
    if (!mounted) return;
    setState(() => _connectivity = reachable ? 'Online' : 'Server unreachable');
  }

  Future<void> _loadDashData() async {
    final s = await SessionStore.load();
    if (s == null || !mounted) return;
    setState(() => _dashLoading = true);
    final api = InventoryApi(s.baseUrl);
    try {
      Future<TransactionListPage> tx() => api.listTransactions(
            accessToken: s.accessToken,
            shopId: s.defaultShopId,
            limit: 5,
          );

      Future<Map<String, dynamic>> sh() => api.shiftSummary(
            accessToken: s.accessToken,
            shopId: s.defaultShopId,
          );

      late TransactionListPage page;
      late Map<String, dynamic> shiftBody;
      Map<String, dynamic>? activeShift;
      try {
        page = await tx();
        shiftBody = await sh();
        activeShift = await api.getActiveShift(accessToken: s.accessToken);
      } on ApiException catch (e) {
        if (e.statusCode == 401) {
          final body = await api.refresh(refreshToken: s.refreshToken);
          await SessionStore.save(
            baseUrl: s.baseUrl,
            accessToken: body['access_token'] as String,
            refreshToken: body['refresh_token'] as String,
            tenantId: body['tenant_id'] as String,
            shopIds: (body['shop_ids'] as List<dynamic>).map((x) => x.toString()).toList(),
          );
          final s2 = await SessionStore.load();
          if (s2 == null) rethrow;
          page = await api.listTransactions(
            accessToken: s2.accessToken,
            shopId: s2.defaultShopId,
            limit: 5,
          );
          shiftBody = await api.shiftSummary(
            accessToken: s2.accessToken,
            shopId: s2.defaultShopId,
          );
          activeShift = await api.getActiveShift(accessToken: s2.accessToken);
        } else {
          rethrow;
        }
      }
      if (!mounted) return;
      setState(() {
        _recentTx = page.items;
        _shift = shiftBody;
        _activeShift = activeShift;
        _dashLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _dashLoading = false);
    }
  }

  Future<void> _openSync() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (context) => const SyncStatusScreen()),
    );
    if (!mounted) return;
    await context.read<SyncStateModel>().refreshFromStorage();
    await _refreshNet();
    await _loadDashData();
  }

  Future<void> _openShiftFlow() async {
    final s = await SessionStore.load();
    if (s == null || !mounted) return;
    final result = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => ShiftOpenDialog(accessToken: s.accessToken, api: InventoryApi(s.baseUrl)),
    );
    if (result == true) await _loadDashData();
  }

  Future<void> _closeShiftFlow() async {
    final s = await SessionStore.load();
    if (s == null || !mounted || _activeShift == null) return;
    final result = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (_) => ShiftCloseDialog(
        accessToken: s.accessToken,
        api: InventoryApi(s.baseUrl),
        shift: _activeShift!,
        shopId: s.defaultShopId,
      ),
    );
    if (result == true) await _loadDashData();
  }

  String _lineSummary(Map<String, dynamic> t) {
    final lines = (t['lines'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();

    if (lines.isEmpty) return '';
    final parts = <String>[];
    for (final ln in lines.take(3)) {
      final name = ln['product_name'] as String? ?? ln['product_sku'] as String? ?? 'Item';
      final qty = ln['quantity'];
      parts.add('$qty× $name');
    }
    if (lines.length > 3) parts.add('…');
    return parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final sync = context.watch<SyncStateModel>();
    final feed = context.watch<InventoryFeedModel>();
    final cart = context.watch<CartModel>();
    final tier = feed.policyTier;
    final theme = Theme.of(context);
    final code = feed.currencyCode;
    final exp = feed.currencyExponent;
    final sym = feed.currencySymbolOverride;

    final quick = feed.products.where((p) => p.quantity > 0).take(6).toList();
    final subF = formatMinorUnits(
      cart.subtotalCents,
      code: code,
      exponent: exp,
      symbolOverride: sym,
    );
    final taxF = formatMinorUnits(
      cart.taxCents,
      code: code,
      exponent: exp,
      symbolOverride: sym,
    );
    final grandF = formatMinorUnits(
      cart.grandTotalCents,
      code: code,
      exponent: exp,
      symbolOverride: sym,
    );

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar.medium(
            pinned: true,
            title: const Text('Cashier'),
            actions: [
              IconButton(
                tooltip: 'Log out',
                onPressed: widget.onLoggedOut,
                icon: const Icon(Icons.logout_rounded),
              ),
            ],
          ),
          SliverToBoxAdapter(
            child: CashierHeroBackground(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Welcome back', style: theme.textTheme.headlineSmall?.copyWith(color: CashierColors.onPrimary)),
                  const SizedBox(height: 8),
                  Text(
                    'Search the catalog or jump into the ledger.',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: CashierColors.onPrimary.withValues(alpha: 0.85),
                    ),
                  ),
                  const SizedBox(height: CashierSpacing.md),
                  TextField(
                    controller: _search,
                    style: theme.textTheme.bodyLarge?.copyWith(color: CashierColors.onSurface),
                    decoration: InputDecoration(
                      hintText: 'Search name or SKU',
                      prefixIcon: const Icon(Icons.search_rounded, color: CashierColors.primary),
                      filled: true,
                      fillColor: CashierColors.card,
                    ),
                    onSubmitted: (q) => widget.onGoLookup(q.trim().isEmpty ? null : q.trim()),
                  ),
                  const SizedBox(height: CashierSpacing.sm),
                  Row(
                    children: [
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: () =>
                              widget.onGoLookup(_search.text.trim().isEmpty ? null : _search.text.trim()),
                          icon: const Icon(Icons.manage_search_rounded, size: 20),
                          label: const Text('Open lookup'),
                          style: FilledButton.styleFrom(
                            backgroundColor: CashierColors.secondaryContainer,
                            foregroundColor: CashierColors.onSecondaryContainer,
                          ),
                        ),
                      ),
                      const SizedBox(width: CashierSpacing.sm),
                      IconButton(
                        onPressed: () => widget.onGoLookup(null),
                        style: IconButton.styleFrom(
                          backgroundColor: CashierColors.card,
                          foregroundColor: CashierColors.primary,
                        ),
                        icon: const Icon(Icons.qr_code_scanner_rounded),
                        tooltip: 'Barcode (lookup)',
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: _ShiftBanner(
              activeShift: _activeShift,
              loading: _dashLoading,
              onOpen: _openShiftFlow,
              onClose: _closeShiftFlow,
            ),
          ),
          if (tier != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  CashierSpacing.gutter,
                  CashierSpacing.md,
                  CashierSpacing.gutter,
                  0,
                ),
                child: Material(
                  color: CashierColors.surfaceContainer,
                  borderRadius: BorderRadius.circular(CashierRadius.quickTile),
                  child: Padding(
                    padding: const EdgeInsets.all(CashierSpacing.md),
                    child: Row(
                      children: [
                        Icon(Icons.shield_outlined, color: CashierColors.primary),
                        const SizedBox(width: CashierSpacing.sm),
                        Expanded(
                          child: Text(
                            'Offline policy: $tier — card tenders need connectivity.',
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          if (sync.lastOutboxFailure != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  CashierSpacing.gutter,
                  CashierSpacing.md,
                  CashierSpacing.gutter,
                  0,
                ),
                child: Material(
                  color: CashierColors.errorContainer.withValues(alpha: 0.75),
                  borderRadius: BorderRadius.circular(CashierRadius.quickTile),
                  child: Padding(
                    padding: const EdgeInsets.all(CashierSpacing.sm),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          Icons.warning_amber_rounded,
                          color: CashierColors.onErrorContainer,
                          size: 22,
                        ),
                        const SizedBox(width: CashierSpacing.sm),
                        Expanded(
                          child: Text(
                            sync.lastOutboxFailure!,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: CashierColors.onErrorContainer,
                            ),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Dismiss',
                          icon: const Icon(Icons.close, size: 20),
                          onPressed: () =>
                              context.read<SyncStateModel>().clearTransientFailures(),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          SliverToBoxAdapter(
            child: ArchiveSectionHeader(
              kicker: 'Quick',
              title: 'Access',
              subtitle: 'Tap an SKU to add to cart',
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisSpacing: CashierSpacing.sm,
                crossAxisSpacing: CashierSpacing.sm,
                childAspectRatio: 1.25,
              ),
              delegate: SliverChildBuilderDelegate(
                (context, i) {
                  if (feed.loading && quick.isEmpty) {
                    return const Center(child: CircularProgressIndicator());
                  }
                  if (i >= quick.length) return const SizedBox.shrink();
                  final p = quick[i];
                  final price = formatMinorUnits(
                    p.unitPriceCents,
                    code: code,
                    exponent: exp,
                    symbolOverride: sym,
                  );
                  return QuickAccessTile(
                    label: p.name,
                    secondary: '${p.sku} · $price',
                    onTap: () {
                      final c = context.read<CartModel>();
                      final inCart = c.lines.fold<int>(0, (sum, l) => l.productId == p.id ? sum + l.quantity : sum);
                      if (inCart + 1 > p.quantity) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Not enough stock for this item')),
                        );
                        return;
                      }
                      c.addProduct(p);
                    },
                  );
                },
                childCount: feed.loading && quick.isEmpty ? 2 : quick.length,
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: ArchiveSectionHeader(
              kicker: 'Active',
              title: 'Folio',
              subtitle: 'Cart subtotal, tax, and total',
              trailing: TextButton(
                onPressed: widget.onGoCart,
                child: const Text('Open cart'),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
              child: Material(
                color: CashierColors.card,
                borderRadius: BorderRadius.circular(CashierRadius.quickTile),
                child: Padding(
                  padding: const EdgeInsets.all(CashierSpacing.md),
                  child: cart.lines.isEmpty
                      ? Text(
                          'No lines yet — use Quick Access or Lookup.',
                          style: theme.textTheme.bodyMedium?.copyWith(color: CashierColors.onSurfaceVariant),
                        )
                      : Column(
                          children: [
                            ...cart.lines.take(4).map((l) {
                              return Padding(
                                padding: const EdgeInsets.only(bottom: CashierSpacing.sm),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        l.name,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: theme.textTheme.labelLarge,
                                      ),
                                    ),
                                    Text(
                                      formatMinorUnits(
                                        l.lineSubtotalCents,
                                        code: code,
                                        exponent: exp,
                                        symbolOverride: sym,
                                      ),
                                      style: theme.textTheme.labelLarge,
                                    ),
                                  ],
                                ),
                              );
                            }),
                            const Divider(height: 24),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('Subtotal', style: theme.textTheme.labelMedium),
                                Text(subF, style: theme.textTheme.titleSmall),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('Tax', style: theme.textTheme.labelMedium),
                                Text(taxF, style: theme.textTheme.titleSmall),
                              ],
                            ),
                            const SizedBox(height: CashierSpacing.sm),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text('Total', style: theme.textTheme.titleMedium),
                                Text(
                                  grandF,
                                  style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
                                ),
                              ],
                            ),
                            const SizedBox(height: CashierSpacing.md),
                            CashierGradientButton(
                              label: 'Review cart',
                              icon: Icons.shopping_cart_checkout_rounded,
                              onPressed: widget.onGoCart,
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: ArchiveSectionHeader(
              kicker: 'Shift',
              title: 'Pulse',
              subtitle: _shift == null
                  ? (_dashLoading ? 'Loading…' : 'Today on this register (UTC day)')
                  : '${_shift!['transaction_count']} sales · ${formatMinorUnits(
                      _shift!['total_cents'] as int,
                      code: code,
                      exponent: exp,
                      symbolOverride: sym,
                    )}',
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                CashierMetricCard(
                  title: 'Network',
                  value: _connectivity,
                  icon: Icons.wifi_tethering_rounded,
                  onTap: _refreshNet,
                ),
                const SizedBox(height: CashierSpacing.sm),
                CashierMetricCard(
                  title: 'Last sync',
                  value: sync.lastSyncIso == null || sync.lastSyncIso!.isEmpty
                      ? 'Not yet'
                      : formatShortLocalDateTime(sync.lastSyncIso!),
                  icon: Icons.schedule_rounded,
                ),
                const SizedBox(height: CashierSpacing.sm),
                CashierMetricCard(
                  title: 'Pending uploads',
                  value: sync.pendingOutboxCount == 0
                      ? 'None'
                      : '${sync.pendingOutboxCount} sale(s)',
                  icon: Icons.cloud_upload_outlined,
                ),
                const SizedBox(height: CashierSpacing.sm),
                CashierMetricCard(
                  title: 'Sync & recovery',
                  value: 'Open details',
                  icon: Icons.sync_rounded,
                  onTap: _openSync,
                ),
              ]),
            ),
          ),
          SliverToBoxAdapter(
            child: ArchiveSectionHeader(
              kicker: 'Recent',
              title: 'Transactions',
              subtitle: 'This device',
              trailing: TextButton(
                onPressed: widget.onGoHistory,
                child: const Text('View journal'),
              ),
            ),
          ),
          if (_recentTx.isEmpty && _dashLoading)
            const SliverToBoxAdapter(
              child: Padding(
                padding: EdgeInsets.all(CashierSpacing.gutter),
                child: Center(child: CircularProgressIndicator()),
              ),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
              sliver: SliverList.separated(
                itemCount: _recentTx.length,
                separatorBuilder: (_, _) => const SizedBox(height: CashierSpacing.sm),
                itemBuilder: (context, i) {
                  final t = _recentTx[i];
                  final total = formatMinorUnits(
                    t['total_cents'] as int,
                    code: code,
                    exponent: exp,
                    symbolOverride: sym,
                  );
                  final createdRaw = t['created_at'] as String;
                  final created = formatShortLocalDateTime(createdRaw);
                  final status = t['status'] as String? ?? '';
                  return CompactTransactionRow(
                    amountLabel: total,
                    meta: '$created · $status',
                    subline: _lineSummary(t),
                  );
                },
              ),
            ),
          const SliverToBoxAdapter(
            child: SizedBox(height: CashierSpacing.xl),
          ),
        ],
      ),
    );
  }
}

class _ShiftBanner extends StatelessWidget {
  const _ShiftBanner({
    required this.activeShift,
    required this.loading,
    required this.onOpen,
    required this.onClose,
  });

  final Map<String, dynamic>? activeShift;
  final bool loading;
  final VoidCallback onOpen;
  final VoidCallback onClose;

  String _duration(String openedAt) {
    final start = DateTime.tryParse(openedAt);
    if (start == null) return '';
    final diff = DateTime.now().difference(start);
    final h = diff.inHours;
    final m = diff.inMinutes % 60;
    return h > 0 ? '${h}h ${m}m' : '${m}m';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (loading && activeShift == null) {
      return const Padding(
        padding: EdgeInsets.fromLTRB(CashierSpacing.gutter, CashierSpacing.md, CashierSpacing.gutter, 0),
        child: SizedBox.shrink(),
      );
    }

    final bool hasShift = activeShift != null;

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        CashierSpacing.gutter,
        CashierSpacing.md,
        CashierSpacing.gutter,
        0,
      ),
      child: Material(
        color: hasShift ? CashierColors.primary.withValues(alpha: 0.12) : CashierColors.surfaceContainer,
        borderRadius: BorderRadius.circular(CashierRadius.quickTile),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.md, vertical: CashierSpacing.sm),
          child: Row(
            children: [
              Icon(
                hasShift ? Icons.radio_button_checked_rounded : Icons.radio_button_unchecked_rounded,
                color: hasShift ? CashierColors.primary : CashierColors.onSurfaceVariant,
                size: 20,
              ),
              const SizedBox(width: CashierSpacing.sm),
              Expanded(
                child: hasShift
                    ? Text(
                        'Shift active · ${_duration(activeShift!['opened_at'] as String)}',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: CashierColors.primary,
                          fontWeight: FontWeight.w600,
                        ),
                      )
                    : Text(
                        'No active shift — tap to open one',
                        style: theme.textTheme.bodyMedium?.copyWith(color: CashierColors.onSurfaceVariant),
                      ),
              ),
              if (hasShift)
                TextButton(
                  onPressed: onClose,
                  child: const Text('Close shift'),
                )
              else
                FilledButton(
                  onPressed: onOpen,
                  style: FilledButton.styleFrom(
                    backgroundColor: CashierColors.primary,
                    foregroundColor: CashierColors.onPrimary,
                    padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.md),
                    minimumSize: const Size(0, 36),
                  ),
                  child: const Text('Open shift'),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
