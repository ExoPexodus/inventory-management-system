import 'package:flutter/foundation.dart';

import '../services/inventory_api.dart';

class CatalogModel extends ChangeNotifier {
  final Map<String, int> _stockByProductId = {};

  int stockFor(String productId) => _stockByProductId[productId] ?? 0;

  void applyFromProducts(List<ProductRow> rows) {
    _stockByProductId
      ..clear()
      ..addEntries(rows.map((r) => MapEntry(r.id, r.quantity)));
    notifyListeners();
  }

  void clear() {
    _stockByProductId.clear();
    notifyListeners();
  }
}
