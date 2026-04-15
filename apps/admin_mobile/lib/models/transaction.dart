class TransactionLine {
  const TransactionLine({
    required this.productId,
    required this.productName,
    required this.sku,
    required this.quantity,
    required this.unitPriceCents,
  });

  final String productId;
  final String productName;
  final String sku;
  final int quantity;
  final int unitPriceCents;

  int get lineTotalCents => quantity * unitPriceCents;

  factory TransactionLine.fromJson(Map<String, dynamic> j) => TransactionLine(
        productId: j['product_id'] as String? ?? '',
        productName: j['product_name'] as String? ?? '',
        sku: j['sku'] as String? ?? '',
        quantity: j['quantity'] as int? ?? 0,
        unitPriceCents: j['unit_price_cents'] as int? ?? 0,
      );
}

class PaymentAllocation {
  const PaymentAllocation({
    required this.tenderType,
    required this.amountCents,
    this.gatewayProvider,
    this.externalRef,
  });

  final String tenderType;
  final int amountCents;
  final String? gatewayProvider;
  final String? externalRef;

  factory PaymentAllocation.fromJson(Map<String, dynamic> j) => PaymentAllocation(
        tenderType: j['tender_type'] as String? ?? '',
        amountCents: j['amount_cents'] as int? ?? 0,
        gatewayProvider: j['gateway_provider'] as String?,
        externalRef: j['external_ref'] as String?,
      );
}

class Transaction {
  const Transaction({
    required this.id,
    required this.totalCents,
    required this.taxCents,
    required this.status,
    required this.createdAt,
    required this.shopId,
    required this.deviceId,
    this.cashierName,
    this.lines = const [],
    this.payments = const [],
  });

  final String id;
  final int totalCents;
  final int taxCents;
  final String status;
  final String createdAt;
  final String shopId;
  final String deviceId;
  final String? cashierName;
  final List<TransactionLine> lines;
  final List<PaymentAllocation> payments;

  String get shortId => id.length > 8 ? id.substring(0, 8).toUpperCase() : id.toUpperCase();

  String get itemSummary {
    if (lines.isEmpty) return 'No items';
    final total = lines.fold(0, (s, l) => s + l.quantity);
    return '$total item${total == 1 ? '' : 's'}';
  }

  factory Transaction.fromJson(Map<String, dynamic> j) => Transaction(
        id: j['id'] as String? ?? '',
        totalCents: j['total_cents'] as int? ?? 0,
        taxCents: j['tax_cents'] as int? ?? 0,
        status: j['status'] as String? ?? 'completed',
        createdAt: j['created_at'] as String? ?? '',
        shopId: j['shop_id'] as String? ?? '',
        deviceId: j['device_id'] as String? ?? '',
        cashierName: j['cashier_name'] as String?,
        lines: (j['lines'] as List<dynamic>?)
                ?.map((e) => TransactionLine.fromJson(e as Map<String, dynamic>))
                .toList() ??
            [],
        payments: (j['payments'] as List<dynamic>?)
                ?.map((e) => PaymentAllocation.fromJson(e as Map<String, dynamic>))
                .toList() ??
            [],
      );
}
