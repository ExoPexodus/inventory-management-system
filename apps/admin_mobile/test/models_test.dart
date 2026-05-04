import 'package:flutter_test/flutter_test.dart';
import 'package:admin_mobile/models/analytics.dart';
import 'package:admin_mobile/models/purchase_order.dart';
import 'package:admin_mobile/models/stock_alert.dart';

void main() {
  group('SalesPoint.fromJson', () {
    test('parses day field and formats as abbreviated date label', () {
      final sp = SalesPoint.fromJson({
        'day': '2026-05-04',
        'gross_cents': 5930,
        'transaction_count': 4,
      });
      expect(sp.grossCents, 5930);
      expect(sp.transactionCount, 4);
      expect(sp.label, 'May 4');
    });

    test('returns empty label on missing day', () {
      final sp = SalesPoint.fromJson({'gross_cents': 0, 'transaction_count': 0});
      expect(sp.label, '');
    });
  });

  group('PurchaseOrder.fromJson', () {
    test('parses header and computes totalCents from lines', () {
      final po = PurchaseOrder.fromJson({
        'id': 'po-1', 'supplier_id': 'sup-1', 'supplier_name': 'Acme',
        'status': 'draft', 'created_at': '2026-05-04T10:00:00Z',
        'lines': [
          {
            'id': 'l-1', 'product_id': 'p-1', 'product_name': 'Widget',
            'product_sku': 'WGT', 'quantity_ordered': 3,
            'quantity_received': 0, 'unit_cost_cents': 500,
          },
        ],
      });
      expect(po.supplierName, 'Acme');
      expect(po.status, 'draft');
      expect(po.lineCount, 1);
      expect(po.totalCents, 1500);
    });

    test('handles empty lines gracefully', () {
      final po = PurchaseOrder.fromJson({
        'id': 'po-2', 'supplier_id': 'sup-1', 'supplier_name': 'X',
        'status': 'ordered', 'created_at': '2026-05-04T10:00:00Z',
      });
      expect(po.totalCents, 0);
      expect(po.lineCount, 0);
    });
  });

  group('StockAlert.fromJson', () {
    test('parses fields correctly', () {
      final alert = StockAlert.fromJson({
        'shop_id': 's1', 'shop_name': 'Main', 'product_id': 'p1',
        'sku': 'ABC', 'name': 'Chai', 'quantity': 0, 'threshold': 5,
      });
      expect(alert.name, 'Chai');
      expect(alert.quantity, 0);
      expect(alert.isOutOfStock, true);
    });

    test('isOutOfStock false when quantity > 0', () {
      final alert = StockAlert.fromJson({
        'shop_id': 's1', 'shop_name': 'Main', 'product_id': 'p1',
        'sku': 'ABC', 'name': 'Tea', 'quantity': 3, 'threshold': 5,
      });
      expect(alert.isOutOfStock, false);
    });
  });

  group('HeatmapBucket.fromJson', () {
    test('parses hour and avgGrossCents', () {
      final b = HeatmapBucket.fromJson({
        'hour': 14, 'avg_gross_cents': 2500, 'avg_tx_count': 3.5,
      });
      expect(b.hour, 14);
      expect(b.avgGrossCents, 2500);
      expect(b.avgTxCount, 3.5);
    });
  });
}
