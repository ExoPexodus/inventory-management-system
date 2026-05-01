import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/cart_model.dart';
import '../services/authenticated_api.dart';
import '../services/inventory_api.dart';
import '../services/session_store.dart';

/// Collapsible customer picker for the cart screen.
/// Collapsed: shows "Add customer" chip or selected customer label.
/// Expanded: phone/name search field with live results from API.
class CustomerPickerWidget extends StatefulWidget {
  const CustomerPickerWidget({super.key});

  @override
  State<CustomerPickerWidget> createState() => _CustomerPickerWidgetState();
}

class _CustomerPickerWidgetState extends State<CustomerPickerWidget> {
  bool _expanded = false;
  final TextEditingController _ctrl = TextEditingController();
  List<CustomerLookupItem> _results = [];
  bool _searching = false;
  String? _searchError;
  Timer? _debounce;

  bool _showNameField = false;
  final TextEditingController _nameCtrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    _nameCtrl.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  void _onQueryChanged(String q) {
    _debounce?.cancel();
    if (q.trim().length < 2) {
      setState(() { _results = []; _searchError = null; });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () => _search(q.trim()));
  }

  Future<void> _search(String q) async {
    setState(() { _searching = true; _searchError = null; });
    try {
      final auth = context.read<AuthenticatedApi>();
      final results = await auth.run(
        (api, s) => api.customerLookup(accessToken: s.accessToken, query: q),
      );
      if (mounted) setState(() { _results = results; _searching = false; });
    } catch (e) {
      if (mounted) setState(() { _searching = false; _searchError = 'Search failed'; });
    }
  }

  void _selectCustomer(CustomerLookupItem item) {
    context.read<CartModel>().setCustomer(
      id: item.id,
      phone: item.phone,
      name: item.name,
    );
    setState(() {
      _expanded = false;
      _ctrl.clear();
      _results = [];
      _showNameField = false;
    });
  }

  void _confirmNewCustomer() {
    final phone = _ctrl.text.trim();
    if (phone.isEmpty) return;
    context.read<CartModel>().setCustomer(
      phone: phone,
      name: _nameCtrl.text.trim().isEmpty ? null : _nameCtrl.text.trim(),
    );
    setState(() {
      _expanded = false;
      _ctrl.clear();
      _nameCtrl.clear();
      _results = [];
      _showNameField = false;
    });
  }

  void _collapse() {
    setState(() {
      _expanded = false;
      _ctrl.clear();
      _nameCtrl.clear();
      _results = [];
      _showNameField = false;
      _searchError = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final cart = context.watch<CartModel>();

    if (!_expanded) {
      final label = cart.customerDisplayLabel;
      if (label != null) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.person, size: 16),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 6),
              GestureDetector(
                onTap: () => cart.clearCustomer(),
                child: const Icon(Icons.close, size: 14),
              ),
            ],
          ),
        );
      }
      return TextButton.icon(
        onPressed: () => setState(() => _expanded = true),
        icon: const Icon(Icons.person_add_outlined, size: 18),
        label: const Text('Add customer'),
      );
    }

    // Expanded search UI
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _ctrl,
          autofocus: true,
          decoration: InputDecoration(
            hintText: 'Search phone or name…',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: IconButton(
              icon: const Icon(Icons.close),
              onPressed: _collapse,
            ),
          ),
          onChanged: _onQueryChanged,
        ),
        if (_searching) const LinearProgressIndicator(),
        if (_searchError != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Text(
              _searchError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 12),
            ),
          ),
        ..._results.map((item) => ListTile(
          dense: true,
          leading: const Icon(Icons.person_outline),
          title: Text(item.name ?? item.phone),
          subtitle: item.name != null
              ? Text(item.phone, style: const TextStyle(fontSize: 11))
              : null,
          trailing: item.groupName != null
              ? Chip(label: Text(item.groupName!, style: const TextStyle(fontSize: 11)))
              : null,
          onTap: () => _selectCustomer(item),
        )),
        if (_ctrl.text.trim().length >= 2 && !_searching) ...[
          const Divider(),
          if (!_showNameField)
            ListTile(
              dense: true,
              leading: const Icon(Icons.person_add_outlined),
              title: Text('New customer: ${_ctrl.text.trim()}'),
              subtitle: const Text('Tap to add a name (optional)'),
              onTap: () => setState(() => _showNameField = true),
              trailing: TextButton(
                onPressed: _confirmNewCustomer,
                child: const Text('Add'),
              ),
            )
          else ...[
            TextField(
              controller: _nameCtrl,
              decoration: const InputDecoration(hintText: 'Customer name (optional)'),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _confirmNewCustomer,
              child: const Text('Confirm new customer'),
            ),
          ],
        ],
      ],
    );
  }
}
