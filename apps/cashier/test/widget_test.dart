import 'package:cashier/main.dart';
import 'package:cashier/models/cart_model.dart';
import 'package:cashier/models/catalog_model.dart';
import 'package:cashier/models/inventory_feed_model.dart';
import 'package:cashier/models/sync_state_model.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('shows onboarding when no session', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => CartModel()),
          ChangeNotifierProvider(create: (_) => CatalogModel()),
          ChangeNotifierProvider(create: (_) => SyncStateModel()),
          ChangeNotifierProvider(create: (_) => InventoryFeedModel()),
        ],
        child: const CashierBootstrap(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Device onboarding'), findsOneWidget);
  });
}
