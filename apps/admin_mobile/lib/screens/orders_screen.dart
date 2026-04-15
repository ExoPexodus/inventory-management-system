import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../admin_tokens.dart';
import '../models/currency.dart';
import '../models/transaction.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/transaction_card.dart';
import 'app_shell.dart';
import 'order_detail_screen.dart';

class OrdersScreen extends StatefulWidget {
  const OrdersScreen({super.key, required this.onLogout});

  final VoidCallback onLogout;

  @override
  State<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends State<OrdersScreen> {
  bool _loading = true;
  bool _loadingMore = false;
  String? _error;
  List<Transaction> _transactions = [];
  String? _nextCursor;
  String _searchQuery = '';
  String? _statusFilter;
  AdminApi? _api;
  Timer? _debounce;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  Future<void> _load({bool append = false}) async {
    if (!append) {
      setState(() { _loading = true; _error = null; _nextCursor = null; });
    }
    try {
      final session = await SessionStore.load();
      if (session == null) { widget.onLogout(); return; }
      _api = AdminApi(session.baseUrl, session.token);
      final data = await _api!.getTransactions(
        q: _searchQuery.isEmpty ? null : _searchQuery,
        status: _statusFilter,
        cursor: append ? _nextCursor : null,
      );
      final items = (data['items'] as List<dynamic>? ?? [])
          .map((e) => Transaction.fromJson(e as Map<String, dynamic>))
          .toList();
      final next = data['next_cursor'] as String?;
      if (!mounted) return;
      setState(() {
        if (append) {
          _transactions = [..._transactions, ...items];
        } else {
          _transactions = items;
        }
        _nextCursor = next;
        _loading = false;
        _loadingMore = false;
      });
    } on ApiException catch (e) {
      if (e.statusCode == 401) { await SessionStore.clearLogin(); if (mounted) widget.onLogout(); return; }
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; _loadingMore = false; });
    } catch (e) {
      if (mounted) setState(() { _error = 'Connection error'; _loading = false; _loadingMore = false; });
    }
  }

  void _onSearch(String val) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      setState(() => _searchQuery = val);
      _load();
    });
  }

  void _loadMore() {
    if (_loadingMore || _nextCursor == null) return;
    setState(() => _loadingMore = true);
    _load(append: true);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final currency = context.watch<CurrencyModel>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Orders'),
        actions: [
          IconButton(
            onPressed: () => showLogoutDialog(context, widget.onLogout),
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Sign out',
          ),
        ],
      ),
      body: Column(
        children: [
          // Search + filter
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AdminSpacing.gutter, AdminSpacing.md, AdminSpacing.gutter, 0,
            ),
            child: Column(
              children: [
                TextField(
                  decoration: const InputDecoration(
                    hintText: 'Search by product or SKU...',
                    prefixIcon: Icon(Icons.search_rounded),
                  ),
                  onChanged: _onSearch,
                ),
                const SizedBox(height: AdminSpacing.sm),
                SizedBox(
                  height: 36,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    children: [
                      _StatusChip(
                        label: 'All',
                        selected: _statusFilter == null,
                        onTap: () { setState(() => _statusFilter = null); _load(); },
                      ),
                      const SizedBox(width: AdminSpacing.xs),
                      _StatusChip(
                        label: 'Completed',
                        selected: _statusFilter == 'posted',
                        onTap: () { setState(() => _statusFilter = 'posted'); _load(); },
                      ),
                      const SizedBox(width: AdminSpacing.xs),
                      _StatusChip(
                        label: 'Pending',
                        selected: _statusFilter == 'pending',
                        onTap: () { setState(() => _statusFilter = 'pending'); _load(); },
                      ),
                      const SizedBox(width: AdminSpacing.xs),
                      _StatusChip(
                        label: 'Voided',
                        selected: _statusFilter == 'voided',
                        onTap: () { setState(() => _statusFilter = 'voided'); _load(); },
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // List
          Expanded(
            child: RefreshIndicator(
              onRefresh: _load,
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : _error != null
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(AdminSpacing.gutter),
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
                          ),
                        )
                      : _transactions.isEmpty
                          ? Center(
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(Icons.receipt_long_outlined, size: 48, color: AdminColors.onSurfaceVariant),
                                  const SizedBox(height: 12),
                                  Text(
                                    'No orders found',
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      color: AdminColors.onSurfaceVariant,
                                    ),
                                  ),
                                ],
                              ),
                            )
                          : ListView.separated(
                              padding: const EdgeInsets.fromLTRB(
                                AdminSpacing.gutter, AdminSpacing.md, AdminSpacing.gutter, AdminSpacing.xxl,
                              ),
                              itemCount: _transactions.length + (_nextCursor != null ? 1 : 0),
                              separatorBuilder: (_, __) => const SizedBox(height: AdminSpacing.sm),
                              itemBuilder: (_, i) {
                                if (i == _transactions.length) {
                                  return Padding(
                                    padding: const EdgeInsets.symmetric(vertical: AdminSpacing.md),
                                    child: Center(
                                      child: _loadingMore
                                          ? const CircularProgressIndicator()
                                          : OutlinedButton.icon(
                                              onPressed: _loadMore,
                                              icon: const Icon(Icons.expand_more_rounded),
                                              label: const Text('Load more'),
                                            ),
                                    ),
                                  );
                                }
                                final tx = _transactions[i];
                                return TransactionCard(
                                  transaction: tx,
                                  formatMoney: currency.format,
                                  onTap: () => Navigator.push(
                                    context,
                                    MaterialPageRoute(
                                      builder: (_) => OrderDetailScreen(
                                        transaction: tx,
                                        formatMoney: currency.format,
                                      ),
                                    ),
                                  ),
                                );
                              },
                            ),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return FilterChip(
      label: Text(label),
      selected: selected,
      onSelected: (_) => onTap(),
      selectedColor: AdminColors.primary.withValues(alpha: 0.14),
      labelStyle: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: selected ? AdminColors.primary : AdminColors.onSurfaceVariant,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
          ),
    );
  }
}
