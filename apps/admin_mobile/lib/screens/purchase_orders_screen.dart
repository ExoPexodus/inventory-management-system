import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../admin_tokens.dart';
import '../models/purchase_order.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import 'app_shell.dart';
import 'create_edit_purchase_order_screen.dart';
import 'purchase_order_detail_screen.dart';

const _statuses = ['All', 'Draft', 'Ordered', 'Received', 'Cancelled'];

Color _statusColor(String status) {
  switch (status) {
    case 'draft': return AdminColors.onSurfaceVariant;
    case 'ordered': return AdminColors.primary;
    case 'received': return const Color(0xFF1A6B3C);
    case 'cancelled': return AdminColors.onErrorContainer;
    default: return AdminColors.onSurfaceVariant;
  }
}

Color _statusBg(String status) {
  switch (status) {
    case 'draft': return AdminColors.surfaceContainerHigh;
    case 'ordered': return AdminColors.primaryContainer.withValues(alpha: 0.15);
    case 'received': return const Color(0xFFD6F0E3);
    case 'cancelled': return AdminColors.errorContainer;
    default: return AdminColors.surfaceContainerHigh;
  }
}

class PurchaseOrdersScreen extends StatefulWidget {
  const PurchaseOrdersScreen({super.key, required this.onLogout});
  final VoidCallback onLogout;

  @override
  State<PurchaseOrdersScreen> createState() => _PurchaseOrdersScreenState();
}

class _PurchaseOrdersScreenState extends State<PurchaseOrdersScreen> {
  bool _loading = true;
  String? _error;
  List<PurchaseOrder> _orders = [];
  String? _nextCursor;
  bool _loadingMore = false;
  String _filterStatus = 'All';
  AdminApi? _api;

  @override
  void initState() {
    super.initState();
    _load();
  }

  static const _pageSize = 20;

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; _nextCursor = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { widget.onLogout(); return; }
      _api = AdminApi(session.baseUrl, session.token);
      final raw = await _api!.getPurchaseOrders(
        status: _filterStatus.toLowerCase() == 'all' ? null : _filterStatus.toLowerCase(),
        limit: _pageSize,
      );
      if (!mounted) return;
      final items = raw
          .map((e) => PurchaseOrder.fromJson(e as Map<String, dynamic>))
          .toList();
      // Use the last item's created_at as cursor if a full page was returned.
      final cursor = items.length >= _pageSize ? items.last.createdAt : null;
      setState(() {
        _orders = items;
        _nextCursor = cursor;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (e.statusCode == 401) { await SessionStore.clearLogin(); if (mounted) widget.onLogout(); return; }
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (_) {
      if (mounted) setState(() { _error = 'Connection error'; _loading = false; });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _nextCursor == null || _api == null) return;
    setState(() => _loadingMore = true);
    try {
      final raw = await _api!.getPurchaseOrders(
        status: _filterStatus.toLowerCase() == 'all' ? null : _filterStatus.toLowerCase(),
        cursor: _nextCursor,
        limit: _pageSize,
      );
      final items = raw
          .map((e) => PurchaseOrder.fromJson(e as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      final cursor = items.length >= _pageSize ? items.last.createdAt : null;
      setState(() {
        _orders.addAll(items);
        _nextCursor = cursor;
        _loadingMore = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Purchases'),
        actions: [
          IconButton(
            onPressed: () => showLogoutDialog(context, widget.onLogout),
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Sign out',
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () async {
          await Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => const CreateEditPurchaseOrderScreen(),
          ));
          _load();
        },
        child: const Icon(Icons.add_rounded),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AdminSpacing.gutter, AdminSpacing.md, AdminSpacing.gutter, 0,
            ),
            child: SizedBox(
              height: 36,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: _statuses.map((s) {
                  final selected = _filterStatus == s;
                  return Padding(
                    padding: const EdgeInsets.only(right: AdminSpacing.xs),
                    child: FilterChip(
                      label: Text(s),
                      selected: selected,
                      onSelected: (_) {
                        setState(() => _filterStatus = s);
                        _load();
                      },
                      selectedColor: AdminColors.primary.withValues(alpha: 0.14),
                      labelStyle: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: selected ? AdminColors.primary : AdminColors.onSurfaceVariant,
                        fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
          const SizedBox(height: AdminSpacing.md),
          Expanded(
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
                    : RefreshIndicator(
                        onRefresh: _load,
                        child: _orders.isEmpty
                            ? ListView(children: [
                                SizedBox(
                                  height: 300,
                                  child: Center(
                                    child: Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(Icons.shopping_bag_outlined, size: 48,
                                            color: AdminColors.onSurfaceVariant),
                                        const SizedBox(height: 12),
                                        Text('No purchase orders',
                                          style: Theme.of(context).textTheme.bodyMedium
                                              ?.copyWith(color: AdminColors.onSurfaceVariant)),
                                      ],
                                    ),
                                  ),
                                ),
                              ])
                            : ListView.separated(
                                padding: const EdgeInsets.fromLTRB(
                                  AdminSpacing.gutter, 0, AdminSpacing.gutter, 100,
                                ),
                                itemCount: _orders.length + (_nextCursor != null ? 1 : 0),
                                separatorBuilder: (context, index) => const SizedBox(height: AdminSpacing.sm),
                                itemBuilder: (context, i) {
                                  if (i == _orders.length) {
                                    if (!_loadingMore) {
                                      WidgetsBinding.instance.addPostFrameCallback(
                                        (_) => _loadMore(),
                                      );
                                    }
                                    return const Padding(
                                      padding: EdgeInsets.all(16),
                                      child: Center(child: CircularProgressIndicator()),
                                    );
                                  }
                                  final po = _orders[i];
                                  return _POTile(
                                    po: po,
                                    onTap: () async {
                                      await Navigator.of(context).push(MaterialPageRoute(
                                        builder: (_) => PurchaseOrderDetailScreen(poId: po.id),
                                      ));
                                      _load();
                                    },
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

class _POTile extends StatelessWidget {
  const _POTile({required this.po, required this.onTap});
  final PurchaseOrder po;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String dateLabel = '';
    try {
      final dt = DateTime.parse(po.createdAt).toLocal();
      dateLabel = DateFormat('MMM d, y').format(dt);
    } catch (_) {}

    return Material(
      color: AdminColors.card,
      borderRadius: BorderRadius.circular(AdminRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AdminSpacing.md),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(po.supplierName, style: theme.textTheme.titleMedium),
                    const SizedBox(height: 2),
                    Text(
                      '$dateLabel · ${po.lineCount} item${po.lineCount == 1 ? '' : 's'}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: AdminColors.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AdminSpacing.sm),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _statusBg(po.status),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  po.status[0].toUpperCase() + po.status.substring(1),
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: _statusColor(po.status),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(width: AdminSpacing.xs),
              const Icon(Icons.chevron_right_rounded, color: AdminColors.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}
