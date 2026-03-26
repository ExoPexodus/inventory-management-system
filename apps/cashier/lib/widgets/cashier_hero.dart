import 'package:flutter/material.dart';

import '../cashier_tokens.dart';

/// Rounded hero band with archive gradient (Stitch dashboard header).
class CashierHeroBackground extends StatelessWidget {
  const CashierHeroBackground({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.fromLTRB(
      CashierSpacing.gutter,
      CashierSpacing.md,
      CashierSpacing.gutter,
      CashierSpacing.lg,
    ),
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: const BorderRadius.vertical(
          bottom: Radius.circular(CashierRadius.hero),
        ),
        gradient: CashierHeroGradient.archive,
        boxShadow: [
          BoxShadow(
            color: CashierColors.onSurface.withValues(alpha: 0.12),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: padding,
        child: DefaultTextStyle.merge(
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: CashierColors.onPrimary),
          child: IconTheme.merge(
            data: const IconThemeData(color: CashierColors.onPrimary),
            child: child,
          ),
        ),
      ),
    );
  }
}
