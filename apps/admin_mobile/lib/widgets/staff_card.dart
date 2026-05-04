import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../admin_tokens.dart';
import '../models/employee.dart';

class StaffCard extends StatelessWidget {
  const StaffCard({
    super.key,
    required this.employee,
    required this.onDeactivate,
    required this.onReactivate,
  });

  final Employee employee;
  final VoidCallback onDeactivate;
  final VoidCallback onReactivate;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final emp = employee;

    return Material(
      color: AdminColors.card,
      borderRadius: BorderRadius.circular(AdminRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(AdminSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundColor: emp.isActive
                      ? AdminColors.primary.withValues(alpha: 0.12)
                      : AdminColors.surfaceContainerHigh,
                  child: Text(
                    emp.initials,
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: emp.isActive ? AdminColors.primary : AdminColors.onSurfaceVariant,
                    ),
                  ),
                ),
                const SizedBox(width: AdminSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(emp.name, style: theme.textTheme.titleMedium),
                      Row(
                        children: [
                          Container(
                            width: 7,
                            height: 7,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: emp.isActive
                                  ? const Color(0xFF1A6B3C)
                                  : AdminColors.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(width: 5),
                          Text(
                            emp.isActive ? 'Active' : 'Inactive',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: emp.isActive
                                  ? const Color(0xFF1A6B3C)
                                  : AdminColors.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(width: AdminSpacing.sm),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: AdminColors.surfaceContainerLow,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              emp.position,
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: AdminColors.onSurfaceVariant,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: AdminSpacing.sm),
            Text(
              emp.email,
              style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant),
            ),
            const SizedBox(height: AdminSpacing.md),
            Row(
              children: [
                if (emp.email.isNotEmpty)
                  _IconAction(
                    icon: Icons.email_outlined,
                    tooltip: 'Email',
                    onTap: () => launchUrl(Uri.parse('mailto:${emp.email}')),
                  ),
                if (emp.phone != null && emp.phone!.isNotEmpty) ...[
                  const SizedBox(width: AdminSpacing.xs),
                  _IconAction(
                    icon: Icons.phone_outlined,
                    tooltip: 'Call',
                    onTap: () => launchUrl(Uri.parse('tel:${emp.phone}')),
                  ),
                ],
                const Spacer(),
                TextButton.icon(
                  onPressed: () => _showActions(context),
                  icon: const Icon(Icons.more_horiz_rounded, size: 18),
                  label: const Text('Actions'),
                  style: TextButton.styleFrom(
                    foregroundColor: AdminColors.onSurfaceVariant,
                    textStyle: theme.textTheme.labelMedium,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _showActions(BuildContext context) {
    final emp = employee;
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(AdminRadius.hero)),
      ),
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AdminSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: AdminColors.outlineVariant,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: AdminSpacing.md),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: AdminSpacing.gutter),
                child: Text(
                  emp.name,
                  style: Theme.of(ctx).textTheme.titleMedium,
                ),
              ),
              const SizedBox(height: AdminSpacing.sm),
              if (emp.isActive) ...[
                _BottomSheetAction(
                  icon: Icons.person_off_rounded,
                  label: 'Deactivate',
                  color: AdminColors.onErrorContainer,
                  onTap: () { Navigator.pop(ctx); onDeactivate(); },
                ),
              ] else
                _BottomSheetAction(
                  icon: Icons.person_rounded,
                  label: 'Reactivate',
                  color: const Color(0xFF1A6B3C),
                  onTap: () { Navigator.pop(ctx); onReactivate(); },
                ),
              const SizedBox(height: AdminSpacing.sm),
            ],
          ),
        ),
      ),
    );
  }
}

class _IconAction extends StatelessWidget {
  const _IconAction({required this.icon, required this.tooltip, required this.onTap});

  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: onTap,
      icon: Icon(icon, size: 18),
      tooltip: tooltip,
      style: IconButton.styleFrom(
        backgroundColor: AdminColors.surfaceContainerLow,
        foregroundColor: AdminColors.onSurfaceVariant,
        padding: const EdgeInsets.all(8),
        minimumSize: const Size(36, 36),
      ),
    );
  }
}

class _BottomSheetAction extends StatelessWidget {
  const _BottomSheetAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final c = color ?? AdminColors.onSurface;
    return ListTile(
      leading: Icon(icon, color: c),
      title: Text(label, style: TextStyle(color: c)),
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: AdminSpacing.gutter),
    );
  }
}
