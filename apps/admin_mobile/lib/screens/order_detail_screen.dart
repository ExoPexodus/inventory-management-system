import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../admin_tokens.dart';
import '../models/transaction.dart';

class OrderDetailScreen extends StatelessWidget {
  const OrderDetailScreen({
    super.key,
    required this.transaction,
    required this.formatMoney,
  });

  final Transaction transaction;
  final String Function(int cents) formatMoney;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tx = transaction;

    String dateStr = '';
    try {
      final dt = DateTime.parse(tx.createdAt).toLocal();
      dateStr = DateFormat('EEEE, MMMM d, y · h:mm a').format(dt);
    } catch (_) {}

    return Scaffold(
      appBar: AppBar(
        title: Text('ORD-${tx.shortId}'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AdminSpacing.gutter),
        children: [
          // Header card
          Material(
            color: AdminColors.card,
            borderRadius: BorderRadius.circular(AdminRadius.quickTile),
            child: Padding(
              padding: const EdgeInsets.all(AdminSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Total', style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant)),
                      Text(
                        formatMoney(tx.totalCents),
                        style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: AdminSpacing.xs),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Status', style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant)),
                      _StatusBadge(status: tx.status),
                    ],
                  ),
                  const SizedBox(height: AdminSpacing.xs),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Date', style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant)),
                      Flexible(
                        child: Text(
                          dateStr,
                          style: theme.textTheme.bodySmall,
                          textAlign: TextAlign.end,
                        ),
                      ),
                    ],
                  ),
                  if (tx.deviceId.isNotEmpty) ...[
                    const SizedBox(height: AdminSpacing.xs),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Device', style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant)),
                        Flexible(
                          child: Text(
                            tx.deviceId.length > 12 ? tx.deviceId.substring(0, 12).toUpperCase() : tx.deviceId,
                            style: theme.textTheme.bodySmall,
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: AdminSpacing.lg),

          // Line items
          if (tx.lines.isNotEmpty) ...[
            Text(
              'ITEMS',
              style: theme.textTheme.labelSmall?.copyWith(
                color: AdminColors.onSurfaceVariant,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: AdminSpacing.sm),
            Material(
              color: AdminColors.card,
              borderRadius: BorderRadius.circular(AdminRadius.quickTile),
              child: Column(
                children: tx.lines.asMap().entries.map((entry) {
                  final i = entry.key;
                  final line = entry.value;
                  final isLast = i == tx.lines.length - 1;
                  return Column(
                    children: [
                      Padding(
                        padding: const EdgeInsets.all(AdminSpacing.md),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(line.productName, style: theme.textTheme.titleMedium),
                                  Text(
                                    '${line.sku} · ${line.quantity} × ${formatMoney(line.unitPriceCents)}',
                                    style: theme.textTheme.bodySmall?.copyWith(
                                      color: AdminColors.onSurfaceVariant,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Text(
                              formatMoney(line.lineTotalCents),
                              style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
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
            const SizedBox(height: AdminSpacing.lg),
          ],

          // Tax & total breakdown
          Text(
            'SUMMARY',
            style: theme.textTheme.labelSmall?.copyWith(
              color: AdminColors.onSurfaceVariant,
              letterSpacing: 1.2,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: AdminSpacing.sm),
          Material(
            color: AdminColors.card,
            borderRadius: BorderRadius.circular(AdminRadius.quickTile),
            child: Padding(
              padding: const EdgeInsets.all(AdminSpacing.md),
              child: Column(
                children: [
                  _SummaryRow(
                    label: 'Subtotal',
                    value: formatMoney(tx.totalCents - tx.taxCents),
                    theme: theme,
                  ),
                  const SizedBox(height: AdminSpacing.xs),
                  _SummaryRow(
                    label: 'Tax',
                    value: formatMoney(tx.taxCents),
                    theme: theme,
                  ),
                  Divider(
                    height: AdminSpacing.md,
                    color: AdminColors.outlineVariant.withValues(alpha: 0.4),
                  ),
                  _SummaryRow(
                    label: 'Total',
                    value: formatMoney(tx.totalCents),
                    theme: theme,
                    bold: true,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AdminSpacing.lg),

          // Payments
          if (tx.payments.isNotEmpty) ...[
            Text(
              'PAYMENT',
              style: theme.textTheme.labelSmall?.copyWith(
                color: AdminColors.onSurfaceVariant,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: AdminSpacing.sm),
            Material(
              color: AdminColors.card,
              borderRadius: BorderRadius.circular(AdminRadius.quickTile),
              child: Column(
                children: tx.payments.asMap().entries.map((entry) {
                  final i = entry.key;
                  final pay = entry.value;
                  final isLast = i == tx.payments.length - 1;
                  return Column(
                    children: [
                      Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: AdminSpacing.md,
                          vertical: AdminSpacing.sm,
                        ),
                        child: Row(
                          children: [
                            Icon(
                              _tenderIcon(pay.tenderType),
                              size: 18,
                              color: AdminColors.onSurfaceVariant,
                            ),
                            const SizedBox(width: AdminSpacing.sm),
                            Expanded(
                              child: Text(
                                _tenderLabel(pay.tenderType),
                                style: theme.textTheme.bodyMedium,
                              ),
                            ),
                            Text(
                              formatMoney(pay.amountCents),
                              style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
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
          const SizedBox(height: AdminSpacing.xxl),
        ],
      ),
    );
  }

  IconData _tenderIcon(String tender) {
    switch (tender) {
      case 'cash': return Icons.payments_outlined;
      case 'card': return Icons.credit_card_outlined;
      default: return Icons.account_balance_wallet_outlined;
    }
  }

  String _tenderLabel(String tender) {
    switch (tender) {
      case 'cash': return 'Cash';
      case 'card': return 'Card';
      case 'gateway': return 'Gateway';
      default: return tender;
    }
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    Color color;
    Color bg;
    String label;
    switch (status) {
      case 'posted':
      case 'completed':
        color = AdminColors.primary;
        bg = AdminColors.primary.withValues(alpha: 0.10);
        label = 'Completed';
      case 'refunded':
      case 'voided':
        color = AdminColors.onErrorContainer;
        bg = AdminColors.errorContainer.withValues(alpha: 0.7);
        label = status == 'refunded' ? 'Refunded' : 'Voided';
      default:
        color = AdminColors.onSecondaryContainer;
        bg = AdminColors.secondaryContainer.withValues(alpha: 0.5);
        label = 'Pending';
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AdminRadius.chip),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({required this.label, required this.value, required this.theme, this.bold = false});
  final String label;
  final String value;
  final ThemeData theme;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: bold
              ? theme.textTheme.titleMedium
              : theme.textTheme.bodyMedium?.copyWith(color: AdminColors.onSurfaceVariant),
        ),
        Text(
          value,
          style: bold
              ? theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)
              : theme.textTheme.bodyMedium,
        ),
      ],
    );
  }
}
