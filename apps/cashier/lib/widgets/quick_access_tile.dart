import 'package:flutter/material.dart';

import '../cashier_tokens.dart';

class QuickAccessTile extends StatelessWidget {
  const QuickAccessTile({
    super.key,
    required this.label,
    required this.secondary,
    required this.onTap,
    this.icon = Icons.inventory_2_outlined,
  });

  final String label;
  final String secondary;
  final VoidCallback onTap;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: CashierColors.card,
      elevation: 0.5,
      shadowColor: CashierColors.onSurface.withValues(alpha: 0.06),
      surfaceTintColor: Colors.transparent,
      borderRadius: BorderRadius.circular(CashierRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(CashierSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: CashierColors.primary, size: 26),
              const SizedBox(height: CashierSpacing.sm),
              Text(
                label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              Text(
                secondary,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.labelSmall?.copyWith(color: CashierColors.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
