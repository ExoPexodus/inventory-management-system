import 'package:flutter/material.dart';

import '../admin_tokens.dart';

class AdminMetricCard extends StatelessWidget {
  const AdminMetricCard({
    super.key,
    required this.title,
    required this.value,
    required this.icon,
    this.trend,
    this.trendPositive,
    this.onTap,
    this.subtitle,
  });

  final String title;
  final String value;
  final IconData icon;
  final String? trend;
  final bool? trendPositive;
  final VoidCallback? onTap;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pos = trendPositive;
    final trendColor = pos == null
        ? AdminColors.onSurfaceVariant
        : pos
            ? const Color(0xFF1A6B3C)
            : AdminColors.onErrorContainer;
    final trendBg = pos == null
        ? AdminColors.surfaceContainerHigh
        : pos
            ? const Color(0xFFD6F0E3)
            : AdminColors.errorContainer;

    return Material(
      color: AdminColors.card,
      borderRadius: BorderRadius.circular(AdminRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AdminSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: AdminColors.primary.withValues(alpha: 0.10),
                      borderRadius: BorderRadius.circular(AdminRadius.chip),
                    ),
                    child: Icon(icon, size: 18, color: AdminColors.primary),
                  ),
                  const Spacer(),
                  if (trend != null)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: trendBg,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        trend!,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: trendColor,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: AdminSpacing.sm),
              Text(
                value,
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: AdminColors.onSurface,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                title,
                style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 2),
                Text(
                  subtitle!,
                  style: theme.textTheme.labelSmall?.copyWith(color: AdminColors.onSurfaceVariant),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
