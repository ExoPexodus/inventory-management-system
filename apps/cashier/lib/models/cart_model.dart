import 'package:flutter/foundation.dart';

import '../services/inventory_api.dart';
import '../util/tax.dart' as sale_tax;

class CartLine {
  CartLine({
    required this.productId,
    required this.name,
    required this.sku,
    required this.unitPriceCents,
    required this.effectiveTaxRateBps,
    required this.taxExempt,
    this.variantLabel,
    this.quantity = 1,
  });

  final String productId;
  final String name;
  final String sku;
  final String? variantLabel;
  final int unitPriceCents;
  final int effectiveTaxRateBps;
  final bool taxExempt;
  int quantity;

  int get lineSubtotalCents => unitPriceCents * quantity;

  int get lineTaxCents => sale_tax.lineTaxCents(
        lineSubtotalCents: lineSubtotalCents,
        effectiveTaxRateBps: effectiveTaxRateBps,
        taxExempt: taxExempt,
      );
}

class CartModel extends ChangeNotifier {
  final List<CartLine> _lines = [];

  // Customer attachment
  String? _customerId;
  String? _customerPhone;
  String? _customerName;

  String? get customerId => _customerId;
  String? get customerPhone => _customerPhone;
  String? get customerName => _customerName;

  String? get customerDisplayLabel {
    if (_customerName != null && _customerName!.isNotEmpty) return _customerName;
    if (_customerPhone != null) return _customerPhone;
    return null;
  }

  void setCustomer({String? id, String? phone, String? name}) {
    _customerId = id;
    _customerPhone = phone;
    _customerName = name;
    notifyListeners();
  }

  void clearCustomer() {
    _customerId = null;
    _customerPhone = null;
    _customerName = null;
    notifyListeners();
  }

  List<CartLine> get lines => List.unmodifiable(_lines);

  int get lineKindCount => _lines.length;

  int get itemCount => _lines.fold(0, (a, b) => a + b.quantity);

  int get subtotalCents => _lines.fold(0, (a, b) => a + b.lineSubtotalCents);

  int get taxCents => _lines.fold(0, (a, b) => a + b.lineTaxCents);

  int get grandTotalCents => subtotalCents + taxCents;

  void addProduct(ProductRow p, {int qty = 1}) {
    final i = _lines.indexWhere((l) => l.productId == p.id);
    if (i >= 0) {
      _lines[i].quantity += qty;
    } else {
      _lines.add(
        CartLine(
          productId: p.id,
          name: p.name,
          sku: p.sku,
          unitPriceCents: p.unitPriceCents,
          effectiveTaxRateBps: p.effectiveTaxRateBps,
          taxExempt: p.taxExempt,
          variantLabel: p.variantLabel,
          quantity: qty,
        ),
      );
    }
    notifyListeners();
  }

  void setLineQuantity(String productId, int q) {
    final i = _lines.indexWhere((l) => l.productId == productId);
    if (i < 0) return;
    if (q < 1) {
      _lines.removeAt(i);
    } else {
      _lines[i].quantity = q;
    }
    notifyListeners();
  }

  void removeLine(String productId) {
    _lines.removeWhere((l) => l.productId == productId);
    notifyListeners();
  }

  void clear() {
    _lines.clear();
    clearCustomer();
  }
}
