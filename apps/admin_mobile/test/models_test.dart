import 'package:flutter_test/flutter_test.dart';
import 'package:admin_mobile/models/analytics.dart';

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
}
