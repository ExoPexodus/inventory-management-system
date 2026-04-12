class AnalyticsSummary {
  const AnalyticsSummary({
    required this.grossCents,
    required this.prevGrossCents,
    required this.deltaPct,
    required this.transactionCount,
    required this.avgTicketCents,
    required this.topCategory,
    required this.stockAlertCount,
    required this.pendingOrderCount,
  });

  final int grossCents;
  final int prevGrossCents;
  final double? deltaPct;
  final int transactionCount;
  final int avgTicketCents;
  final String? topCategory;
  final int stockAlertCount;
  final int pendingOrderCount;

  factory AnalyticsSummary.fromJson(Map<String, dynamic> j) => AnalyticsSummary(
        grossCents: j['gross_cents'] as int? ?? 0,
        prevGrossCents: j['prev_gross_cents'] as int? ?? 0,
        deltaPct: (j['delta_pct'] as num?)?.toDouble(),
        transactionCount: j['transaction_count'] as int? ?? 0,
        avgTicketCents: j['avg_ticket_cents'] as int? ?? 0,
        topCategory: j['top_category'] as String?,
        stockAlertCount: j['stock_alert_count'] as int? ?? 0,
        pendingOrderCount: j['pending_order_count'] as int? ?? 0,
      );
}

class SalesPoint {
  const SalesPoint({
    required this.label,
    required this.grossCents,
    required this.transactionCount,
  });

  final String label;
  final int grossCents;
  final int transactionCount;

  factory SalesPoint.fromJson(Map<String, dynamic> j) => SalesPoint(
        label: j['label'] as String? ?? '',
        grossCents: j['gross_cents'] as int? ?? 0,
        transactionCount: j['transaction_count'] as int? ?? 0,
      );
}

class CategoryItem {
  const CategoryItem({
    required this.category,
    required this.grossCents,
    required this.transactionCount,
    required this.pct,
  });

  final String category;
  final int grossCents;
  final int transactionCount;
  final double pct;

  factory CategoryItem.fromJson(Map<String, dynamic> j) => CategoryItem(
        category: j['category'] as String? ?? 'Unknown',
        grossCents: j['gross_cents'] as int? ?? 0,
        transactionCount: j['transaction_count'] as int? ?? 0,
        pct: (j['pct'] as num?)?.toDouble() ?? 0.0,
      );
}

class TopProduct {
  const TopProduct({
    required this.productId,
    required this.productName,
    required this.sku,
    required this.category,
    required this.qtySold,
    required this.grossCents,
  });

  final String productId;
  final String productName;
  final String sku;
  final String? category;
  final int qtySold;
  final int grossCents;

  factory TopProduct.fromJson(Map<String, dynamic> j) => TopProduct(
        productId: j['product_id'] as String? ?? '',
        productName: j['product_name'] as String? ?? '',
        sku: j['sku'] as String? ?? '',
        category: j['category'] as String?,
        qtySold: j['qty_sold'] as int? ?? 0,
        grossCents: j['gross_cents'] as int? ?? 0,
      );
}
