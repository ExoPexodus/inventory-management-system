import 'package:flutter/material.dart';

import '../cashier_tokens.dart';

class CashierMetricCard extends StatelessWidget {
  const CashierMetricCard({
    super.key,
    required this.title,
    required this.value,
    this.icon,
    this.onTap,
  });

  final String title;
  final String value;
  final IconData? icon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final child = Padding(
      padding: const EdgeInsets.all(CashierSpacing.md),
      child: Row(
        children: [
          if (icon != null) ...[
            Icon(icon, color: CashierColors.primary, size: 26),
            const SizedBox(width: CashierSpacing.md),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: theme.textTheme.labelMedium),
                const SizedBox(height: 4),
                Text(value, style: theme.textTheme.titleMedium),
              ],
            ),
          ),
          if (onTap != null)
            Icon(Icons.chevron_right, color: CashierColors.onSurfaceVariant),
        ],
      ),
    );

    return Material(
      color: CashierColors.card,
      borderRadius: BorderRadius.circular(CashierRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: child,
      ),
    );
  }
}
