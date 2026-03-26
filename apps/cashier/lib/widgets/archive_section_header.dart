import 'package:flutter/material.dart';

import '../cashier_tokens.dart';

/// Ledger / archive section title (Stitch journal hierarchy).
class ArchiveSectionHeader extends StatelessWidget {
  const ArchiveSectionHeader({
    super.key,
    this.kicker,
    required this.title,
    this.subtitle,
    this.trailing,
  });

  /// Small caps line above [title] (e.g. “Recent”).
  final String? kicker;
  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(
        left: CashierSpacing.gutter,
        right: CashierSpacing.gutter,
        top: CashierSpacing.lg,
        bottom: CashierSpacing.sm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (kicker != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      kicker!.toUpperCase(),
                      style: theme.textTheme.labelSmall?.copyWith(
                        letterSpacing: 1.2,
                        fontWeight: FontWeight.w700,
                        color: CashierColors.onSurfaceVariant,
                      ),
                    ),
                  ),
                Text(title, style: theme.textTheme.titleLarge),
                if (subtitle != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(subtitle!, style: theme.textTheme.bodySmall),
                  ),
              ],
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}
