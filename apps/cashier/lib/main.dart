import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'models/cart_model.dart';
import 'models/catalog_model.dart';
import 'models/inventory_feed_model.dart';
import 'models/sync_state_model.dart';
import 'screens/cashier_shell.dart';
import 'screens/onboarding_screen.dart';
import 'services/outbox_crypto.dart';
import 'services/outbox_db.dart';
import 'services/session_store.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
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
}

class CashierBootstrap extends StatefulWidget {
  const CashierBootstrap({super.key});

  @override
  State<CashierBootstrap> createState() => _CashierBootstrapState();
}

class _CashierBootstrapState extends State<CashierBootstrap> {
  bool _loading = true;
  bool _hasSession = false;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final s = await SessionStore.load();
    setState(() {
      _hasSession = s != null && s.accessToken.isNotEmpty;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cashier',
      theme: cashierTheme(),
      home: _loading
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _hasSession
              ? CashierShell(
                  onLoggedOut: () async {
                    final cart = context.read<CartModel>();
                    final catalog = context.read<CatalogModel>();
                    final sync = context.read<SyncStateModel>();
                    final feed = context.read<InventoryFeedModel>();
                    await SessionStore.clear();
                    await OutboxDb.clearAll();
                    await OutboxCrypto.wipeKeyForNextUser();
                    if (!mounted) return;
                    cart.clear();
                    catalog.clear();
                    sync.resetForLogout();
                    feed.resetForLogout();
                    setState(() => _hasSession = false);
                  },
                )
              : OnboardingScreen(onSuccess: () => setState(() => _hasSession = true)),
    );
  }
}
