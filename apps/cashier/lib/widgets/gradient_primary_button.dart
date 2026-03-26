import 'package:flutter/material.dart';

import '../cashier_tokens.dart';

class CashierGradientButton extends StatelessWidget {
  const CashierGradientButton({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(CashierRadius.quickTile),
        gradient: disabled
            ? LinearGradient(
                colors: [
                  CashierColors.onSurfaceVariant.withValues(alpha: 0.35),
                  CashierColors.onSurfaceVariant.withValues(alpha: 0.45),
                ],
              )
            : const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  CashierColors.primary,
                  CashierColors.primaryContainer,
                ],
              ),
        boxShadow: disabled
            ? null
            : [
                BoxShadow(
                  color: CashierColors.onSurface.withValues(alpha: 0.08),
                  blurRadius: 24,
                  offset: const Offset(0, 8),
                ),
              ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(CashierRadius.quickTile),
          child: SizedBox(
            width: double.infinity,
            height: 52,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (icon != null) ...[
                  Icon(icon, color: CashierColors.onPrimary, size: 22),
                  const SizedBox(width: 8),
                ],
                Text(
                  label,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: CashierColors.onPrimary,
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
