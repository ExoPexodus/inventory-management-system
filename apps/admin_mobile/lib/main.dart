import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const AdminMobileApp());
}

class AdminMobileApp extends StatelessWidget {
  const AdminMobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Admin Mobile',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2C3E50)),
      ),
      home: const AdminHomePage(),
    );
  }
}

class AdminHomePage extends StatefulWidget {
  const AdminHomePage({super.key});

  @override
  State<AdminHomePage> createState() => _AdminHomePageState();
}

class _AdminHomePageState extends State<AdminHomePage> {
  int _tab = 0;
  final _baseCtl = TextEditingController(text: 'http://10.0.2.2:8001');
  final _tokenCtl = TextEditingController(text: 'dev-api-token');
  Map<String, dynamic>? _overview;
  List<dynamic> _shops = [];
  List<dynamic> _sales = [];
  List<dynamic> _alerts = [];
  List<dynamic> _audit = [];
  bool _loading = false;
  String? _error;

  Future<void> _refresh() async {
    final base = _baseCtl.text.trim();
    final token = _tokenCtl.text.trim();
    if (base.isEmpty || token.isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final headers = {'X-Admin-Token': token};
      final rs = await Future.wait([
        http.get(Uri.parse('$base/v1/admin/overview'), headers: headers),
        http.get(Uri.parse('$base/v1/shops'), headers: headers),
        http.get(Uri.parse('$base/v1/reporting/sales-summary'), headers: headers),
        http.get(Uri.parse('$base/v1/notifications/stock-alerts'), headers: headers),
        http.get(Uri.parse('$base/v1/audit/events?limit=50'), headers: headers),
      ]);
      if (rs.first.statusCode >= 400) {
        throw StateError('overview HTTP ${rs.first.statusCode}');
      }
      setState(() {
        _overview = jsonDecode(rs[0].body) as Map<String, dynamic>;
        _shops = rs[1].statusCode < 400 ? (jsonDecode(rs[1].body) as List<dynamic>) : [];
        _sales = rs[2].statusCode < 400 ? (jsonDecode(rs[2].body) as List<dynamic>) : [];
        _alerts = rs[3].statusCode < 400 ? (jsonDecode(rs[3].body) as List<dynamic>) : [];
        _audit = rs[4].statusCode < 400 ? (jsonDecode(rs[4].body) as List<dynamic>) : [];
      });
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tenants = (_overview?['tenants'] as List<dynamic>?) ?? [];
    return Scaffold(
      appBar: AppBar(
        title: const Text('Admin Mobile'),
        actions: [
          IconButton(onPressed: _loading ? null : _refresh, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              children: [
                TextField(
                  controller: _baseCtl,
                  decoration: const InputDecoration(labelText: 'API base URL'),
                ),
                TextField(
                  controller: _tokenCtl,
                  decoration: const InputDecoration(labelText: 'Admin token'),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      _error!,
                      style: TextStyle(color: Theme.of(context).colorScheme.error),
                    ),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: IndexedStack(
              index: _tab,
              children: [
                _SimpleList(
                  title: 'Tenant summary',
                  items: tenants.map((t) {
                    final m = t as Map<String, dynamic>;
                    return '${m['name']} (${m['slug']}) · ${m['shop_count']} shops';
                  }).toList(),
                ),
                _SimpleList(
                  title: 'Shops',
                  items: _shops.map((s) {
                    final m = s as Map<String, dynamic>;
                    return '${m['name']} · tenant ${m['tenant_id']}';
                  }).toList(),
                ),
                _SimpleList(
                  title: 'Sales',
                  items: _sales.map((s) {
                    final m = s as Map<String, dynamic>;
                    return '${m['shop_name']} · ${m['sale_count']} txns · ${m['gross_cents']}';
                  }).toList(),
                ),
                _SimpleList(
                  title: 'Stock alerts',
                  items: _alerts.map((a) {
                    final m = a as Map<String, dynamic>;
                    return '${m['shop_name']} · ${m['sku']} ${m['name']} · qty ${m['quantity']}';
                  }).toList(),
                ),
                _SimpleList(
                  title: 'Device status / audit',
                  items: _audit.map((a) {
                    final m = a as Map<String, dynamic>;
                    return '${m['kind']} · ${m['detail']}';
                  }).toList(),
                ),
                const _SimpleList(
                  title: 'Quick approvals',
                  items: ['Approval workflows are planned for phase 3+'],
                ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.apartment_outlined), label: 'Tenant'),
          NavigationDestination(icon: Icon(Icons.store_outlined), label: 'Shops'),
          NavigationDestination(icon: Icon(Icons.analytics_outlined), label: 'Sales'),
          NavigationDestination(icon: Icon(Icons.warning_amber_outlined), label: 'Alerts'),
          NavigationDestination(icon: Icon(Icons.devices_other_outlined), label: 'Devices'),
          NavigationDestination(icon: Icon(Icons.rule_outlined), label: 'Approvals'),
        ],
      ),
    );
  }
}

class _SimpleList extends StatelessWidget {
  const _SimpleList({required this.title, required this.items});

  final String title;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (items.isEmpty) const Text('No data yet'),
        ...items.map((i) => Card(child: ListTile(title: Text(i)))),
      ],
    );
  }
}
