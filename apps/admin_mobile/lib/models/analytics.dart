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

  static const _monthAbbr = [
    'Jan','Feb','Mar','Apr','May','Jun',
    'Jul','Aug','Sep','Oct','Nov','Dec',
  ];

  factory SalesPoint.fromJson(Map<String, dynamic> j) {
    final dayStr = j['day'] as String? ?? j['label'] as String? ?? '';
    String label = dayStr;
    if (dayStr.length >= 10) {
      try {
        final dt = DateTime.parse(dayStr);
        label = '${_monthAbbr[dt.month - 1]} ${dt.day}';
      } catch (_) {}
    }
    return SalesPoint(
      label: label,
      grossCents: j['gross_cents'] as int? ?? 0,
      transactionCount: j['transaction_count'] as int? ?? 0,
    );
  }
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
