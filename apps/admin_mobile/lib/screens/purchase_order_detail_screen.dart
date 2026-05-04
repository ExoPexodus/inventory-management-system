import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../admin_tokens.dart';
import '../models/currency.dart';
import '../models/purchase_order.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import 'create_edit_purchase_order_screen.dart';

class PurchaseOrderDetailScreen extends StatefulWidget {
  const PurchaseOrderDetailScreen({super.key, required this.poId});
  final String poId;

  @override
  State<PurchaseOrderDetailScreen> createState() =>
      _PurchaseOrderDetailScreenState();
}

class _PurchaseOrderDetailScreenState
    extends State<PurchaseOrderDetailScreen> {
  bool _loading = true;
  bool _acting = false;
  String? _error;
  PurchaseOrder? _po;
  AdminApi? _api;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { if (mounted) Navigator.of(context).pop(); return; }
      _api = AdminApi(session.baseUrl, session.token);
      final po = await _api!.getPurchaseOrder(widget.poId);
      if (!mounted) return;
      setState(() { _po = po; _loading = false; });
    } on ApiException catch (e) {
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (_) {
      if (mounted) setState(() { _error = 'Connection error'; _loading = false; });
    }
  }

  Future<void> _transition(String newStatus) async {
    final confirmed = newStatus == 'cancelled'
        ? await showDialog<bool>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('Cancel purchase order'),
              content: const Text('This cannot be undone. Are you sure?'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('No'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  style: FilledButton.styleFrom(
                    backgroundColor: AdminColors.error,
                  ),
                  child: const Text('Cancel PO'),
                ),
              ],
            ),
          )
        : true;
    if (confirmed != true || _api == null) return;
    setState(() => _acting = true);
    try {
      await _api!.updatePurchaseOrder(widget.poId, status: newStatus);
      await _load();
      if (mounted) setState(() => _acting = false);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _acting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed (${e.statusCode})')),
        );
      }
    } catch (_) {
      if (mounted) {
        setState(() => _acting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Connection error')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final currency = context.watch<CurrencyModel>();
    final po = _po;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Purchase Order'),
        actions: [
          if (po?.status == 'draft')
            IconButton(
              onPressed: () async {
                await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => CreateEditPurchaseOrderScreen(existingPo: po),
                ));
                _load();
              },
              icon: const Icon(Icons.edit_outlined),
              tooltip: 'Edit',
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.cloud_off_rounded,
                          size: 48, color: AdminColors.onSurfaceVariant),
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
              : po == null
                  ? const SizedBox.shrink()
                  : Column(
                      children: [
                        Expanded(
                          child: ListView(
                            padding:
                                const EdgeInsets.all(AdminSpacing.gutter),
                            children: [
                              // Header card
                              Material(
                                color: AdminColors.card,
                                borderRadius: BorderRadius.circular(
                                    AdminRadius.quickTile),
                                child: Padding(
                                  padding:
                                      const EdgeInsets.all(AdminSpacing.md),
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        mainAxisAlignment:
                                            MainAxisAlignment.spaceBetween,
                                        children: [
                                          Expanded(
                                            child: Text(
                                              po.supplierName,
                                              style: theme.textTheme.titleLarge
                                                  ?.copyWith(
                                                fontWeight: FontWeight.bold,
                                              ),
                                            ),
                                          ),
                                          const SizedBox(
                                              width: AdminSpacing.sm),
                                          _StatusBadge(status: po.status),
                                        ],
                                      ),
                                      const SizedBox(height: AdminSpacing.sm),
                                      _InfoRow(
                                        label: 'Created',
                                        value: _fmtDate(po.createdAt),
                                      ),
                                      if (po.expectedDeliveryDate != null)
                                        _InfoRow(
                                          label: 'Expected delivery',
                                          value: _fmtDate(
                                              po.expectedDeliveryDate!),
                                        ),
                                      if (po.notes != null &&
                                          po.notes!.isNotEmpty)
                                        _InfoRow(
                                          label: 'Notes',
                                          value: po.notes!,
                                        ),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(height: AdminSpacing.lg),

                              // Line items
                              Text('Line Items',
                                  style: theme.textTheme.titleMedium),
                              const SizedBox(height: AdminSpacing.sm),
                              Material(
                                color: AdminColors.card,
                                borderRadius: BorderRadius.circular(
                                    AdminRadius.quickTile),
                                child: Column(
                                  children: [
                                    ...po.lines.asMap().entries.map((entry) {
                                      final i = entry.key;
                                      final line = entry.value;
                                      final isLast = i == po.lines.length - 1;
                                      return Column(
                                        children: [
                                          Padding(
                                            padding: const EdgeInsets.all(
                                                AdminSpacing.md),
                                            child: Row(
                                              children: [
                                                Expanded(
                                                  child: Column(
                                                    crossAxisAlignment:
                                                        CrossAxisAlignment
                                                            .start,
                                                    children: [
                                                      Text(line.productName,
                                                          style: theme
                                                              .textTheme
                                                              .titleMedium),
                                                      Text(
                                                        '${line.productSku} · ${line.quantityOrdered} × ${currency.format(line.unitCostCents)}',
                                                        style: theme
                                                            .textTheme
                                                            .bodySmall
                                                            ?.copyWith(
                                                          color: AdminColors
                                                              .onSurfaceVariant,
                                                        ),
                                                      ),
                                                    ],
                                                  ),
                                                ),
                                                Text(
                                                  currency.format(
                                                      line.lineTotalCents),
                                                  style: theme
                                                      .textTheme.titleMedium
                                                      ?.copyWith(
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
                                              color: AdminColors.outlineVariant
                                                  .withValues(alpha: 0.4),
                                            ),
                                        ],
                                      );
                                    }),
                                    // Total row
                                    Divider(
                                      height: 1,
                                      color: AdminColors.outlineVariant
                                          .withValues(alpha: 0.4),
                                    ),
                                    Padding(
                                      padding: const EdgeInsets.all(
                                          AdminSpacing.md),
                                      child: Row(
                                        mainAxisAlignment:
                                            MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(
                                            'Total',
                                            style: theme.textTheme.titleMedium
                                                ?.copyWith(
                                              fontWeight: FontWeight.bold,
                                            ),
                                          ),
                                          Text(
                                            currency.format(po.totalCents),
                                            style: theme
                                                .textTheme.titleLarge
                                                ?.copyWith(
                                              fontWeight: FontWeight.bold,
                                              color: AdminColors.primary,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 100),
                            ],
                          ),
                        ),

                        // Status action bar
                        if (po.status == 'draft' || po.status == 'ordered')
                          SafeArea(
                            child: Padding(
                              padding: const EdgeInsets.all(AdminSpacing.gutter),
                              child: _acting
                                  ? const Center(
                                      child: CircularProgressIndicator())
                                  : Row(
                                      children: [
                                        Expanded(
                                          child: OutlinedButton(
                                            onPressed: () =>
                                                _transition('cancelled'),
                                            style: OutlinedButton.styleFrom(
                                              foregroundColor: AdminColors.error,
                                              side: BorderSide(
                                                  color: AdminColors.error),
                                              minimumSize: const Size(0, 48),
                                            ),
                                            child: const Text('Cancel PO'),
                                          ),
                                        ),
                                        const SizedBox(width: AdminSpacing.md),
                                        Expanded(
                                          flex: 2,
                                          child: FilledButton(
                                            onPressed: () => _transition(
                                              po.status == 'draft'
                                                  ? 'ordered'
                                                  : 'received',
                                            ),
                                            style: FilledButton.styleFrom(
                                              minimumSize: const Size(0, 48),
                                            ),
                                            child: Text(
                                              po.status == 'draft'
                                                  ? 'Mark as Ordered'
                                                  : 'Mark as Received',
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                            ),
                          ),
                      ],
                    ),
    );
  }

  static String _fmtDate(String iso) {
    try {
      return DateFormat('MMM d, y').format(DateTime.parse(iso).toLocal());
    } catch (_) {
      return iso;
    }
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final String status;

  Color get _fg {
    switch (status) {
      case 'ordered': return AdminColors.primary;
      case 'received': return const Color(0xFF1A6B3C);
      case 'cancelled': return AdminColors.onErrorContainer;
      default: return AdminColors.onSurfaceVariant;
    }
  }

  Color get _bg {
    switch (status) {
      case 'ordered':
        return AdminColors.primaryContainer.withValues(alpha: 0.15);
      case 'received': return const Color(0xFFD6F0E3);
      case 'cancelled': return AdminColors.errorContainer;
      default: return AdminColors.surfaceContainerHigh;
    }
  }

  @override
  Widget build(BuildContext context) => Container(
        padding:
            const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
        decoration:
            BoxDecoration(color: _bg, borderRadius: BorderRadius.circular(20)),
        child: Text(
          status[0].toUpperCase() + status.substring(1),
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: _fg,
                fontWeight: FontWeight.w700,
              ),
        ),
      );
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: AdminSpacing.xs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 130,
              child: Text(
                label,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: AdminColors.onSurfaceVariant,
                    ),
              ),
            ),
            Expanded(
              child: Text(
                value,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ],
        ),
      );
}
