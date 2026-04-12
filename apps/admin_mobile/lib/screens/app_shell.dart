import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../admin_tokens.dart';
import '../models/session.dart';
import '../services/session_store.dart';
import 'analytics_screen.dart';
import 'home_screen.dart';
import 'orders_screen.dart';
import 'staff_screen.dart';

class AppShellModel extends ChangeNotifier {
  int _index = 0;
  int get index => _index;

  void setIndex(int i) {
    if (_index == i) return;
    _index = i;
    notifyListeners();
  }
}

// Tab definition with optional required permission
class _TabDef {
  const _TabDef({
    required this.label,
    required this.icon,
    required this.selectedIcon,
    required this.buildScreen,
    this.permission,
  });

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final Widget Function(VoidCallback onLogout) buildScreen;
  final String? permission;
}

final _allTabs = [
  _TabDef(
    label: 'Home',
    icon: Icons.home_outlined,
    selectedIcon: Icons.home_rounded,
    buildScreen: (onLogout) => HomeScreen(
      onNavigateToStaff: () {},
      onNavigateToOrders: () {},
      onLogout: onLogout,
    ),
    permission: null,
  ),
  _TabDef(
    label: 'Staff',
    icon: Icons.people_outlined,
    selectedIcon: Icons.people_rounded,
    buildScreen: (onLogout) => StaffScreen(onLogout: onLogout),
    permission: 'staff:read',
  ),
  _TabDef(
    label: 'Orders',
    icon: Icons.receipt_long_outlined,
    selectedIcon: Icons.receipt_long_rounded,
    buildScreen: (onLogout) => OrdersScreen(onLogout: onLogout),
    permission: 'sales:read',
  ),
  _TabDef(
    label: 'Analytics',
    icon: Icons.bar_chart_outlined,
    selectedIcon: Icons.bar_chart_rounded,
    buildScreen: (onLogout) => AnalyticsScreen(onLogout: onLogout),
    permission: 'analytics:read',
  ),
];

class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.session, required this.onLogout});

  final AdminSession session;
  final VoidCallback onLogout;

  Future<void> _logout(BuildContext context) async {
    await SessionStore.clear();
    onLogout();
  }

  @override
  Widget build(BuildContext context) {
    final model = context.watch<AppShellModel>();

    // Filter tabs by permissions (Home is always visible)
    final visibleTabs = _allTabs.where((tab) {
      if (tab.permission == null) return true;
      // If permissions list is empty (e.g. no role data yet), show all tabs
      if (session.permissions.isEmpty) return true;
      return session.hasPermission(tab.permission!);
    }).toList();

    // Clamp index so it never goes out of bounds after filtering
    final safeIndex = model.index.clamp(0, visibleTabs.length - 1);

    void onLogoutCallback() => _logout(context);

    // Build navigation callbacks for HomeScreen quick-access tiles
    void navigateTo(String permission) {
      final idx = visibleTabs.indexWhere((t) => t.permission == permission);
      if (idx >= 0) context.read<AppShellModel>().setIndex(idx);
    }

    return Scaffold(
      body: IndexedStack(
        index: safeIndex,
        children: visibleTabs.map((tab) {
          if (tab.label == 'Home') {
            return HomeScreen(
              onNavigateToStaff: () => navigateTo('staff:read'),
              onNavigateToOrders: () => navigateTo('sales:read'),
              onLogout: onLogoutCallback,
            );
          }
          return tab.buildScreen(onLogoutCallback);
        }).toList(),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: safeIndex,
        onDestinationSelected: (i) => context.read<AppShellModel>().setIndex(i),
        destinations: visibleTabs
            .map((tab) => NavigationDestination(
                  icon: Icon(tab.icon),
                  selectedIcon: Icon(tab.selectedIcon),
                  label: tab.label,
                ))
            .toList(),
      ),
    );
  }
}

// ── Logout confirmation helper ────────────────────────────────────────────────

Future<void> showLogoutDialog(BuildContext context, VoidCallback onLogout) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Sign out'),
      content: const Text('Are you sure you want to sign out?'),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, true),
          style: FilledButton.styleFrom(
            backgroundColor: AdminColors.error,
            minimumSize: const Size(0, 44),
          ),
          child: const Text('Sign out'),
        ),
      ],
    ),
  );
  if (confirmed == true) onLogout();
}
