import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../admin_tokens.dart';
import '../models/transaction.dart';

class TransactionCard extends StatelessWidget {
  const TransactionCard({
    super.key,
    required this.transaction,
    required this.onTap,
    required this.formatMoney,
  });

  final Transaction transaction;
  final VoidCallback onTap;
  final String Function(int cents) formatMoney;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tx = transaction;
    final status = tx.status;

    Color statusColor;
    Color statusBg;
    IconData statusIcon;

    switch (status) {
      case 'posted':
      case 'completed':
        statusColor = AdminColors.primary;
        statusBg = AdminColors.primary.withValues(alpha: 0.10);
        statusIcon = Icons.check_circle_outline_rounded;
      case 'refunded':
      case 'voided':
        statusColor = AdminColors.onErrorContainer;
        statusBg = AdminColors.errorContainer.withValues(alpha: 0.7);
        statusIcon = Icons.cancel_outlined;
      default:
        statusColor = AdminColors.onSecondaryContainer;
        statusBg = AdminColors.secondaryContainer.withValues(alpha: 0.5);
        statusIcon = Icons.hourglass_empty_rounded;
    }

    String dateStr = '';
    try {
      final dt = DateTime.parse(tx.createdAt).toLocal();
      dateStr = DateFormat('MMM d, h:mm a').format(dt);
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
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: statusBg,
                  borderRadius: BorderRadius.circular(AdminRadius.chip),
                ),
                child: Icon(statusIcon, color: statusColor, size: 20),
              ),
              const SizedBox(width: AdminSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'ORD-${tx.shortId}',
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: statusBg,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            _statusLabel(status),
                            style: theme.textTheme.labelSmall?.copyWith(color: statusColor),
                          ),
                        ),
                        const SizedBox(width: AdminSpacing.xs),
                        Expanded(
                          child: Text(
                            '${tx.itemSummary} · $dateStr',
                            style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AdminSpacing.md),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    formatMoney(tx.totalCents),
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 2),
                  const Icon(Icons.chevron_right_rounded, color: AdminColors.onSurfaceVariant, size: 18),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'posted': return 'Completed';
      case 'refunded': return 'Refunded';
      case 'voided': return 'Voided';
      case 'pending': return 'Pending';
      default: return status[0].toUpperCase() + status.substring(1);
    }
  }
}
