import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/cart_model.dart';
import '../models/catalog_model.dart';
import '../models/inventory_feed_model.dart';
import '../models/sync_state_model.dart';
import '../services/inventory_api.dart';
import '../services/outbox_service.dart';
import '../services/session_store.dart';
import 'cart_screen.dart';
import 'dashboard_screen.dart';
import 'history_screen.dart';
import 'inventory_lookup_screen.dart';

class CashierShell extends StatefulWidget {
  const CashierShell({super.key, required this.onLoggedOut});

  final VoidCallback onLoggedOut;

  @override
  State<CashierShell> createState() => _CashierShellState();
}

class _CashierShellState extends State<CashierShell> {
  int _index = 0;
  String? _lookupInitialQuery;
  StreamSubscription<List<ConnectivityResult>>? _conn;

  @override
  void initState() {
    super.initState();
    _conn = Connectivity().onConnectivityChanged.listen((_) => _flushOutbox());
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final sync = context.read<SyncStateModel>();
      final feed = context.read<InventoryFeedModel>();
      final catalog = context.read<CatalogModel>();
      await sync.refreshFromStorage();
      await feed.hydrateSession();
      if (feed.session != null && mounted) {
        await feed.refresh(sync: sync, catalog: catalog);
      }
      if (!mounted) return;
      _flushOutbox();
    });
  }

  @override
  void dispose() {
    _conn?.cancel();
    super.dispose();
  }

  Future<void> _flushOutbox() async {
    if (!mounted) return;
    final sync = context.read<SyncStateModel>();
    final s = await SessionStore.load();
    if (s == null || !mounted) return;
    final api = InventoryApi(s.baseUrl);
    await OutboxService.flush(api, sync);
  }

  Future<void> _onSaleComplete() async {
    if (!mounted) return;
    final feed = context.read<InventoryFeedModel>();
    final sync = context.read<SyncStateModel>();
    final catalog = context.read<CatalogModel>();
    await feed.refresh(sync: sync, catalog: catalog);
  }

  void _goLookup(String? query) {
    setState(() {
      _lookupInitialQuery = query;
      _index = 1;
    });
  }

  void _goHistory() {
    setState(() => _index = 3);
  }

  @override
  Widget build(BuildContext context) {
    final cart = context.watch<CartModel>();
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: [
          DashboardScreen(
            onLoggedOut: widget.onLoggedOut,
            onGoLookup: _goLookup,
            onGoCart: () => setState(() => _index = 2),
            onGoHistory: _goHistory,
          ),
          InventoryLookupScreen(key: ValueKey(_lookupInitialQuery ?? ''), initialSearchQuery: _lookupInitialQuery),
          CartScreen(onSaleComplete: _onSaleComplete),
          const HistoryScreen(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard_rounded),
            label: 'Home',
          ),
          const NavigationDestination(
            icon: Icon(Icons.search_rounded),
            selectedIcon: Icon(Icons.manage_search_rounded),
            label: 'Lookup',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: cart.itemCount > 0,
              label: Text('${cart.itemCount}'),
              child: const Icon(Icons.shopping_cart_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: cart.itemCount > 0,
              label: Text('${cart.itemCount}'),
              child: const Icon(Icons.shopping_cart),
            ),
            label: 'Cart',
          ),
          const NavigationDestination(
            icon: Icon(Icons.receipt_long_outlined),
            selectedIcon: Icon(Icons.receipt_long),
            label: 'History',
          ),
        ],
      ),
    );
  }
}
