class PurchaseOrderLine {
  const PurchaseOrderLine({
    required this.id,
    required this.productId,
    required this.productName,
    required this.productSku,
    required this.quantityOrdered,
    required this.quantityReceived,
    required this.unitCostCents,
  });

  final String id;
  final String productId;
  final String productName;
  final String productSku;
  final int quantityOrdered;
  final int quantityReceived;
  final int unitCostCents;

  int get lineTotalCents => quantityOrdered * unitCostCents;

  factory PurchaseOrderLine.fromJson(Map<String, dynamic> j) => PurchaseOrderLine(
        id: j['id'] as String,
        productId: j['product_id'] as String,
        productName: j['product_name'] as String? ?? '',
        productSku: j['product_sku'] as String? ?? '',
        quantityOrdered: j['quantity_ordered'] as int? ?? 0,
        quantityReceived: j['quantity_received'] as int? ?? 0,
        unitCostCents: j['unit_cost_cents'] as int? ?? 0,
      );
}

class PurchaseOrder {
  const PurchaseOrder({
    required this.id,
    required this.supplierId,
    required this.supplierName,
    required this.status,
    required this.createdAt,
    required this.lines,
    this.notes,
    this.expectedDeliveryDate,
  });

  final String id;
  final String supplierId;
  final String supplierName;
  final String status; // draft | ordered | received | cancelled
  final String createdAt;
  final List<PurchaseOrderLine> lines;
  final String? notes;
  final String? expectedDeliveryDate;

  int get totalCents => lines.fold(0, (sum, l) => sum + l.lineTotalCents);
  int get lineCount => lines.length;

  factory PurchaseOrder.fromJson(Map<String, dynamic> j) => PurchaseOrder(
        id: j['id'] as String,
        supplierId: j['supplier_id'] as String,
        supplierName: j['supplier_name'] as String? ?? '',
        status: j['status'] as String? ?? 'draft',
        createdAt: j['created_at'] as String? ?? '',
        notes: j['notes'] as String?,
        expectedDeliveryDate: j['expected_delivery_date'] as String?,
        lines: ((j['lines'] as List<dynamic>?) ?? [])
            .map((e) => PurchaseOrderLine.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
