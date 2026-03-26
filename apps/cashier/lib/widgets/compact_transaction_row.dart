import 'package:flutter/material.dart';

import '../cashier_tokens.dart';

/// Single-line summary for recent sale / history list.
class CompactTransactionRow extends StatelessWidget {
  const CompactTransactionRow({
    super.key,
    required this.amountLabel,
    required this.meta,
    this.subline,
    this.statusLabel,
    this.statusColor,
    this.onTap,
  });

  final String amountLabel;
  final String meta;
  final String? subline;
  final String? statusLabel;
  final Color? statusColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: CashierColors.card,
      borderRadius: BorderRadius.circular(CashierRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: CashierSpacing.md,
            vertical: CashierSpacing.md,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      amountLabel,
                      style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 4),
                    Text(meta, style: theme.textTheme.labelMedium),
                    if (subline != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          subline!,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                  ],
                ),
              ),
              if (statusLabel != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: (statusColor ?? CashierColors.surfaceContainer).withValues(alpha: 0.85),
                    borderRadius: BorderRadius.circular(CashierRadius.chip),
                  ),
                  child: Text(
                    statusLabel!,
                    style: theme.textTheme.labelSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: CashierColors.onSurfaceVariant,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
