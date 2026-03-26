import 'package:flutter/material.dart';

import '../cashier_tokens.dart';
import '../services/inventory_api.dart';

class ProductCard extends StatelessWidget {
  const ProductCard({
    super.key,
    required this.product,
    required this.priceLabel,
    required this.onAdd,
    this.lowStockThreshold = 5,
  });

  final ProductRow product;
  final String priceLabel;
  final VoidCallback onAdd;
  final int lowStockThreshold;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final q = product.quantity;
    final low = q > 0 && q <= lowStockThreshold;
    final out = q == 0;

    return Material(
      color: CashierColors.card,
      borderRadius: BorderRadius.circular(CashierRadius.quickTile),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: out ? null : onAdd,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: CashierSpacing.md,
            vertical: CashierSpacing.md,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _StockDot(low: low, out: out),
              const SizedBox(width: CashierSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      product.name,
                      style: theme.textTheme.titleMedium,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (product.variantLabel != null && product.variantLabel!.trim().isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        product.variantLabel!.trim(),
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: CashierColors.onSurfaceVariant,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: CashierColors.surfaceContainerLow,
                            borderRadius: BorderRadius.circular(CashierRadius.chip),
                          ),
                          child: Text(
                            product.sku,
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: CashierColors.onSurfaceVariant,
                              letterSpacing: 0.3,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          out
                              ? 'Out of stock'
                              : low
                                  ? '$q left'
                                  : '$q on hand',
                          style: theme.textTheme.labelMedium?.copyWith(
                            color: out
                                ? CashierColors.onErrorContainer
                                : low
                                    ? CashierColors.onSecondaryContainer
                                    : CashierColors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: CashierSpacing.sm),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    priceLabel,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 6),
                  IconButton(
                    onPressed: out ? null : onAdd,
                    icon: const Icon(Icons.add_shopping_cart_rounded),
                    tooltip: 'Add to cart',
                    style: IconButton.styleFrom(
                      backgroundColor: CashierColors.surfaceContainer,
                      foregroundColor: CashierColors.primary,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StockDot extends StatelessWidget {
  const _StockDot({required this.low, required this.out});

  final bool low;
  final bool out;

  @override
  Widget build(BuildContext context) {
    Color c;
    if (out) {
      c = CashierColors.errorContainer;
    } else if (low) {
      c = CashierColors.tertiaryFixed;
    } else {
      c = CashierColors.surfaceContainerHigh;
    }
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(
          color: c,
          shape: BoxShape.circle,
        ),
      ),
    );
  }
}
