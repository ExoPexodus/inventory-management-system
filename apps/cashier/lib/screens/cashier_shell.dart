import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config/cashier_timings.dart';
import '../models/cart_model.dart';
import '../models/catalog_model.dart';
import '../models/inventory_feed_model.dart';
import '../models/sync_state_model.dart';
import '../services/authenticated_api.dart';
import '../services/inactivity_controller.dart';
import '../services/inventory_api.dart';
import '../services/offline_limit_controller.dart';
import '../services/outbox_service.dart';
import '../services/session_store.dart';
import 'cart_screen.dart';
import 'dashboard_screen.dart';
import 'history_screen.dart';
import 'inventory_lookup_screen.dart';
import 'walls/deactivated_wall.dart';
import 'walls/offline_limit_wall.dart';

class CashierShell extends StatefulWidget {
  const CashierShell({
    super.key,
    required this.onLoggedOut,
    required this.onSessionExpired,
  });

  final VoidCallback onLoggedOut;

  /// Called when only the employee session expires (inactivity timeout or
  /// deactivation). Device enrollment is preserved — app goes back to the
  /// PIN/password screen, not re-enrollment.
  final VoidCallback onSessionExpired;

  @override
  State<CashierShell> createState() => _CashierShellState();
}

class _CashierShellState extends State<CashierShell> with WidgetsBindingObserver {
  int _index = 0;
  String? _lookupInitialQuery;

  StreamSubscription<List<ConnectivityResult>>? _conn;
  Timer? _outboxTimer;

  late final InactivityController _inactivity;
  late final OfflineLimitController _offline;

  bool _employeeDeactivated = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _inactivity = InactivityController(onTimeout: () async {
      if (mounted) widget.onSessionExpired();
    });
    _offline = OfflineLimitController(probe: _runFeedRefresh)..addListener(_onOfflineChange);

    // Record that the employee just became active (right after login).
    _inactivity.recordActivity();

    _inactivity.start();
    _offline.start();

    _conn = Connectivity().onConnectivityChanged.listen((_) => _onConnectivityChanged());
    _outboxTimer = Timer.periodic(CashierTimings.outboxFlushInterval, (_) => _flushOutbox());

    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _conn?.cancel();
    _outboxTimer?.cancel();
    _offline.removeListener(_onOfflineChange);
    _inactivity.dispose();
    _offline.dispose();
    super.dispose();
  }

  // ── AppLifecycle ──────────────────────────────────────────────────────────

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _inactivity.checkNow();
      _offline.checkNow();
    }
  }

  // ── Initial pull ──────────────────────────────────────────────────────────

  Future<void> _bootstrap() async {
    if (!mounted) return;
    final sync = context.read<SyncStateModel>();
    final feed = context.read<InventoryFeedModel>();
    await sync.refreshFromStorage();
    await feed.hydrateSession();
    if (feed.session != null && mounted) {
      try {
        await _runFeedRefresh();
        if (!mounted) return;
        await _offline.checkNow();
      } on ApiException catch (e) {
        if (e.statusCode == 401 && mounted) {
          // Refresh token is dead — clear session and go back to enrollment.
          await SessionStore.clear();
          widget.onLoggedOut();
          return;
        }
      } catch (_) {
        // Network error on startup — not fatal, but check offline limit.
        if (mounted) await _offline.checkNow();
      }
    }
    if (!mounted) return;
    _flushOutbox();
  }

  // ── Connectivity / sync ───────────────────────────────────────────────────

  Future<void> _onConnectivityChanged() async {
    _flushOutbox();
    if (!mounted) return;
    try {
      await _runFeedRefresh();
      if (mounted) await _offline.checkNow();
    } catch (_) {
      // Still offline — limit check will keep the wall up if needed.
    }
  }

  Future<void> _flushOutbox() async {
    if (!mounted) return;
    final sync = context.read<SyncStateModel>();
    final auth = context.read<AuthenticatedApi>();
    await OutboxService.flush(auth, sync);
  }

  Future<void> _runFeedRefresh() async {
    if (!mounted) return;
    final feed = context.read<InventoryFeedModel>();
    final sync = context.read<SyncStateModel>();
    final catalog = context.read<CatalogModel>();
    final auth = context.read<AuthenticatedApi>();
    await feed.refresh(auth: auth, sync: sync, catalog: catalog);
  }

  void _onOfflineChange() {
    if (mounted) setState(() {});
  }

  // ── Wall actions ──────────────────────────────────────────────────────────

  Future<void> _retrySync() async {
    try {
      await _runFeedRefresh();
      if (mounted) await _offline.checkNow();
    } catch (_) {
      // Surfaced via feed.error in the wall's diagnostics panel.
    }
  }

  Future<void> _signOutEmployee() async {
    await SessionStore.clearEmployeeSession();
    if (mounted) widget.onSessionExpired();
  }

  Future<void> _onSaleComplete() async {
    if (!mounted) return;
    await _runFeedRefresh();
  }

  // ── Navigation helpers ────────────────────────────────────────────────────

  void _goLookup(String? query) {
    setState(() {
      _lookupInitialQuery = query;
      _index = 1;
    });
  }

  void _goHistory() {
    setState(() => _index = 3);
  }

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final feed = context.watch<InventoryFeedModel>();
    final cart = context.watch<CartModel>();

    // Deactivation takes priority: clear employee session and show the wall.
    final deactivated = _employeeDeactivated || feed.employeeDeactivated;
    if (deactivated) {
      // Clear in storage so the next app open goes straight to employee login.
      SessionStore.clearEmployeeSession();
      return DeactivatedWall(
        onRetry: () {
          setState(() => _employeeDeactivated = false);
          context.read<InventoryFeedModel>().resetForLogout();
          widget.onSessionExpired();
        },
      );
    }

    if (_offline.exceeded) {
      return OfflineLimitWall(onRetry: _retrySync, onSignOut: _signOutEmployee);
    }

    return Listener(
      onPointerDown: (_) => _inactivity.recordActivity(),
      child: Scaffold(
        body: IndexedStack(
          index: _index,
          children: [
            DashboardScreen(
              onLoggedOut: widget.onLoggedOut,
              onGoLookup: _goLookup,
              onGoCart: () => setState(() => _index = 2),
              onGoHistory: _goHistory,
            ),
            InventoryLookupScreen(
              key: ValueKey(_lookupInitialQuery ?? ''),
              initialSearchQuery: _lookupInitialQuery,
            ),
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
      ),
    );
  }
}
