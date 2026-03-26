import 'package:flutter/material.dart';

import '../cashier_tokens.dart';
import '../services/inventory_api.dart';
import '../services/session_store.dart' show SessionData, SessionStore;
import '../util/datetime_format.dart';
import '../util/money_format.dart';
import '../widgets/archive_section_header.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final _searchCtrl = TextEditingController();
  List<Map<String, dynamic>> _items = [];
  String? _nextCursor;
  String _currencyCode = 'USD';
  int _currencyExponent = 2;
  String? _currencySymbolOverride;
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  String? _statusFilter;

  @override
  void initState() {
    super.initState();
    _searchCtrl.addListener(() {
      setState(() {});
    });
    _load(reset: true);
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load({required bool reset}) async {
    if (reset) {
      setState(() {
        _loading = true;
        _error = null;
        _nextCursor = null;
        _items = [];
      });
    } else {
      if (_nextCursor == null || _loadingMore) return;
      setState(() => _loadingMore = true);
    }
    final s = await SessionStore.load();
    if (s == null) {
      setState(() {
        _loading = false;
        _loadingMore = false;
        _error = 'No session';
      });
      return;
    }
    final api = InventoryApi(s.baseUrl);
    try {
      _currencyCode = await SessionStore.getCurrencyCode();
      _currencyExponent = await SessionStore.getCurrencyExponent();
      _currencySymbolOverride = await SessionStore.getCurrencySymbolOverride();

      Future<TransactionListPage> fetch(SessionData sess, {String? cursor}) {
        return api.listTransactions(
          accessToken: sess.accessToken,
          shopId: sess.defaultShopId,
          limit: 30,
          cursor: cursor,
          status: _statusFilter,
          q: _searchCtrl.text.trim().isEmpty ? null : _searchCtrl.text.trim(),
        );
      }

      SessionData active = s;
      TransactionListPage page;
      try {
        page = await fetch(active, cursor: reset ? null : _nextCursor);
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
          active = s2;
          page = await fetch(active, cursor: reset ? null : _nextCursor);
        } else {
          rethrow;
        }
      }
      if (!mounted) return;
      setState(() {
        if (reset) {
          _items = page.items;
        } else {
          _items = [..._items, ...page.items];
        }
        _nextCursor = page.nextCursor;
        _loading = false;
        _loadingMore = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
        _loadingMore = false;
      });
    }
  }

  void _setStatus(String? v) {
    setState(() => _statusFilter = v);
    _load(reset: true);
  }

  int get _pageSubtotal {
    var t = 0;
    for (final tx in _items) {
      final tax = tx['tax_cents'] as int? ?? 0;
      final total = tx['total_cents'] as int;
      t += total - tax;
    }
    return t;
  }

  int get _pageTax {
    var t = 0;
    for (final tx in _items) {
      t += tx['tax_cents'] as int? ?? 0;
    }
    return t;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () => _load(reset: true),
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverAppBar.medium(
              title: const Text('Transaction history'),
              actions: [
                IconButton(
                  onPressed: _loading ? null : () => _load(reset: true),
                  icon: const Icon(Icons.refresh_rounded),
                ),
              ],
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  CashierSpacing.gutter,
                  0,
                  CashierSpacing.gutter,
                  CashierSpacing.sm,
                ),
                child: TextField(
                  controller: _searchCtrl,
                  decoration: InputDecoration(
                    hintText: 'Search product or SKU',
                    prefixIcon: const Icon(Icons.search_rounded),
                    suffixIcon: IconButton(
                      icon: const Icon(Icons.check_rounded),
                      onPressed: () => _load(reset: true),
                    ),
                  ),
                  onSubmitted: (_) => _load(reset: true),
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: SizedBox(
                height: 44,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: const Text('All'),
                        selected: _statusFilter == null,
                        onSelected: (_) => _setStatus(null),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: const Text('Posted'),
                        selected: _statusFilter == 'posted',
                        onSelected: (_) => _setStatus('posted'),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: const Text('Pending'),
                        selected: _statusFilter == 'pending',
                        onSelected: (_) => _setStatus('pending'),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: ChoiceChip(
                        label: const Text('Refunded'),
                        selected: _statusFilter == 'refunded',
                        onSelected: (_) => _setStatus('refunded'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (_items.isNotEmpty)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
                  child: Material(
                    color: CashierColors.surfaceContainerLow,
                    borderRadius: BorderRadius.circular(CashierRadius.quickTile),
                    child: Padding(
                      padding: const EdgeInsets.all(CashierSpacing.md),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Ledger summary (this page)',
                            style: theme.textTheme.labelSmall?.copyWith(
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.8,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '${_items.length} transaction(s) · '
                            'Subtotal ${formatMinorUnits(_pageSubtotal, code: _currencyCode, exponent: _currencyExponent, symbolOverride: _currencySymbolOverride)} · '
                            'Tax ${formatMinorUnits(_pageTax, code: _currencyCode, exponent: _currencyExponent, symbolOverride: _currencySymbolOverride)}',
                            style: theme.textTheme.bodySmall,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            if (_items.isNotEmpty)
              const SliverToBoxAdapter(child: SizedBox(height: CashierSpacing.sm)),
            if (_loading && _items.isEmpty)
              const SliverFillRemaining(
                hasScrollBody: false,
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(CashierSpacing.gutter),
                    child: Text(_error!, textAlign: TextAlign.center),
                  ),
                ),
              )
            else if (_items.isEmpty)
              SliverFillRemaining(
                hasScrollBody: false,
                child: Padding(
                  padding: const EdgeInsets.all(CashierSpacing.gutter),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.receipt_long_outlined,
                        size: 48,
                        color: CashierColors.onSurfaceVariant.withValues(alpha: 0.45),
                      ),
                      const SizedBox(height: CashierSpacing.md),
                      Text(
                        'No matching sales',
                        style: theme.textTheme.titleMedium,
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              )
            else ...[
              const SliverToBoxAdapter(
                child: ArchiveSectionHeader(
                  kicker: 'Journal',
                  title: 'Entries',
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
                sliver: SliverList.separated(
                  itemCount: _items.length + (_nextCursor != null ? 1 : 0),
                  separatorBuilder: (context, _) => const SizedBox(height: CashierSpacing.sm),
                  itemBuilder: (context, i) {
                    if (i >= _items.length) {
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: CashierSpacing.md),
                        child: Center(
                          child: _loadingMore
                              ? const CircularProgressIndicator()
                              : TextButton(
                                  onPressed: () => _load(reset: false),
                                  child: const Text('Load more'),
                                ),
                        ),
                      );
                    }
                    final t = _items[i];
                    final grand = formatMinorUnits(
                      t['total_cents'] as int,
                      code: _currencyCode,
                      exponent: _currencyExponent,
                      symbolOverride: _currencySymbolOverride,
                    );
                    final taxAmt = t['tax_cents'] as int? ?? 0;
                    final taxLabel = formatMinorUnits(
                      taxAmt,
                      code: _currencyCode,
                      exponent: _currencyExponent,
                      symbolOverride: _currencySymbolOverride,
                    );
                    final createdRaw = t['created_at'] as String;
                    final created = formatShortLocalDateTime(createdRaw);
                    final lines = (t['lines'] as List<dynamic>).cast<Map<String, dynamic>>();
                    final pays = (t['payments'] as List<dynamic>)
                        .map((p) => (p as Map<String, dynamic>)['tender_type'] as String)
                        .join(', ');
                    final st = t['status'] as String? ?? '';
                    return Material(
                      color: CashierColors.card,
                      borderRadius: BorderRadius.circular(CashierRadius.quickTile),
                      child: Theme(
                        data: theme.copyWith(dividerColor: Colors.transparent),
                        child: ExpansionTile(
                          tilePadding: const EdgeInsets.symmetric(
                            horizontal: CashierSpacing.md,
                            vertical: CashierSpacing.sm,
                          ),
                          childrenPadding: const EdgeInsets.fromLTRB(
                            CashierSpacing.md,
                            0,
                            CashierSpacing.md,
                            CashierSpacing.md,
                          ),
                          title: Text(
                            grand,
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          subtitle: Padding(
                            padding: const EdgeInsets.only(top: 6),
                            child: Text(
                              '$created · $pays · $st · Tax $taxLabel',
                              style: theme.textTheme.labelMedium,
                            ),
                          ),
                          children: [
                            ...lines.map((ln) {
                              final qty = ln['quantity'] as int;
                              final cents = ln['unit_price_cents'] as int;
                              final unit = formatMinorUnits(
                                cents,
                                code: _currencyCode,
                                exponent: _currencyExponent,
                                symbolOverride: _currencySymbolOverride,
                              );
                              final title =
                                  ln['product_name'] as String? ?? ln['product_sku'] as String? ?? 'Product';
                              return Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        title,
                                        style: theme.textTheme.bodySmall,
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    Text(
                                      '$qty× $unit',
                                      style: theme.textTheme.labelMedium,
                                    ),
                                  ],
                                ),
                              );
                            }),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
            const SliverToBoxAdapter(child: SizedBox(height: CashierSpacing.xl)),
          ],
        ),
      ),
    );
  }
}
