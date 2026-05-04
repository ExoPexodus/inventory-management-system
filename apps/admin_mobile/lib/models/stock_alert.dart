class StockAlert {
  const StockAlert({
    required this.shopId,
    required this.shopName,
    required this.productId,
    required this.sku,
    required this.name,
    required this.quantity,
    required this.threshold,
  });

  final String shopId;
  final String shopName;
  final String productId;
  final String sku;
  final String name;
  final int quantity;
  final int threshold;

  bool get isOutOfStock => quantity == 0;

  factory StockAlert.fromJson(Map<String, dynamic> j) => StockAlert(
        shopId: j['shop_id'] as String? ?? '',
        shopName: j['shop_name'] as String? ?? '',
        productId: j['product_id'] as String? ?? '',
        sku: j['sku'] as String? ?? '',
        name: j['name'] as String? ?? '',
        quantity: j['quantity'] as int? ?? 0,
        threshold: j['threshold'] as int? ?? 5,
      );
}
