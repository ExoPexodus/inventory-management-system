import 'package:flutter/material.dart';

import '../admin_tokens.dart';

class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.label,
    required this.title,
    this.trailing,
  });

  final String label;
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label.toUpperCase(),
                style: theme.textTheme.labelSmall?.copyWith(
                  color: AdminColors.onSurfaceVariant,
                  letterSpacing: 1.2,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                title,
                style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
            ],
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}
