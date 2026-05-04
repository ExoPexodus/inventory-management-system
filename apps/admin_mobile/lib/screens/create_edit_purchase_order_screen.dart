import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../admin_tokens.dart';
import '../models/purchase_order.dart';
import '../models/supplier.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';

/// Pass [existingPo] to edit a draft PO; leave null to create a new one.
class CreateEditPurchaseOrderScreen extends StatefulWidget {
  const CreateEditPurchaseOrderScreen({super.key, this.existingPo});
  final PurchaseOrder? existingPo;

  @override
  State<CreateEditPurchaseOrderScreen> createState() =>
      _CreateEditPurchaseOrderScreenState();
}

class _LineItemState {
  String? productId;
  String? productName;
  final TextEditingController qtyCtrl;
  final TextEditingController costCtrl;

  _LineItemState({
    this.productId,
    this.productName,
    int quantity = 1,
    int unitCostCents = 0,
  })  : qtyCtrl = TextEditingController(text: quantity > 0 ? '$quantity' : ''),
        costCtrl = TextEditingController(
          text: unitCostCents > 0
              ? (unitCostCents / 100).toStringAsFixed(2)
              : '',
        );

  void dispose() {
    qtyCtrl.dispose();
    costCtrl.dispose();
  }

  int get qty => int.tryParse(qtyCtrl.text) ?? 0;
  int get costCents => ((double.tryParse(costCtrl.text) ?? 0.0) * 100).round();
  bool get isValid => productId != null && qty > 0;
}

class _CreateEditPurchaseOrderScreenState
    extends State<CreateEditPurchaseOrderScreen> {
  bool _loadingInit = true;
  bool _saving = false;
  String? _error;

  List<Supplier> _suppliers = [];
  Supplier? _selectedSupplier;
  final _notesCtrl = TextEditingController();
  DateTime? _deliveryDate;
  final List<_LineItemState> _lines = [];

  AdminApi? _api;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _notesCtrl.dispose();
    for (final l in _lines) {
      l.dispose();
    }
    super.dispose();
  }

  Future<void> _init() async {
    final session = await SessionStore.load();
    if (session == null) {
      if (mounted) Navigator.of(context).pop();
      return;
    }
    _api = AdminApi(session.baseUrl, session.token);
    try {
      final suppliers = await _api!.getSuppliers();
      if (!mounted) return;
      setState(() {
        _suppliers = suppliers.where((s) => s.status == 'active').toList();
      });

      final existing = widget.existingPo;
      if (existing != null) {
        _notesCtrl.text = existing.notes ?? '';
        if (existing.expectedDeliveryDate != null) {
          try {
            _deliveryDate = DateTime.parse(existing.expectedDeliveryDate!);
          } catch (_) {}
        }
        try {
          _selectedSupplier =
              _suppliers.firstWhere((s) => s.id == existing.supplierId);
        } catch (_) {}
        for (final line in existing.lines) {
          _lines.add(_LineItemState(
            productId: line.productId,
            productName: line.productName,
            quantity: line.quantityOrdered,
            unitCostCents: line.unitCostCents,
          ));
        }
      }

      if (_lines.isEmpty) _lines.add(_LineItemState());
      setState(() => _loadingInit = false);
    } catch (_) {
      if (mounted) {
        setState(() {
          _error = 'Failed to load suppliers';
          _loadingInit = false;
        });
      }
    }
  }

  Future<void> _pickDeliveryDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate:
          _deliveryDate ?? DateTime.now().add(const Duration(days: 7)),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null && mounted) setState(() => _deliveryDate = picked);
  }

  Future<void> _pickProduct(int lineIndex) async {
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => _ProductPickerDialog(api: _api!),
    );
    if (result == null || !mounted) return;
    setState(() {
      _lines[lineIndex].productId = result['id'] as String;
      _lines[lineIndex].productName = result['name'] as String? ?? '';
    });
  }

  bool get _canSave {
    if (_selectedSupplier == null) return false;
    return _lines.any((l) => l.isValid);
  }

  Future<void> _save() async {
    if (!_canSave || _api == null) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final deliveryIso = _deliveryDate?.toUtc().toIso8601String();
      final existing = widget.existingPo;

      if (existing == null) {
        final po = await _api!.createPurchaseOrder(
          supplierId: _selectedSupplier!.id,
          notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
          expectedDeliveryDate: deliveryIso,
        );
        for (final line in _lines) {
          if (!line.isValid) continue;
          await _api!.addPOLine(
            po.id,
            productId: line.productId!,
            quantity: line.qty,
            unitCostCents: line.costCents,
          );
        }
      } else {
        await _api!.updatePurchaseOrder(
          existing.id,
          notes: _notesCtrl.text.trim().isEmpty ? null : _notesCtrl.text.trim(),
          expectedDeliveryDate: deliveryIso,
        );
        for (final oldLine in existing.lines) {
          await _api!.deletePOLine(existing.id, oldLine.id);
        }
        for (final line in _lines) {
          if (!line.isValid) continue;
          await _api!.addPOLine(
            existing.id,
            productId: line.productId!,
            quantity: line.qty,
            unitCostCents: line.costCents,
          );
        }
      }

      if (!mounted) return;
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Failed to save (${e.statusCode})';
          _saving = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _error = 'Connection error';
          _saving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isEdit = widget.existingPo != null;

    return Scaffold(
      appBar: AppBar(
        title: Text(isEdit ? 'Edit Purchase Order' : 'New Purchase Order'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.all(16),
              child: SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            )
          else
            TextButton(
              onPressed: _canSave ? _save : null,
              child: const Text('Save'),
            ),
        ],
      ),
      body: _loadingInit
          ? const Center(child: CircularProgressIndicator())
          : _error != null && _suppliers.isEmpty
              ? Center(child: Text(_error!))
              : ListView(
                  padding: const EdgeInsets.all(AdminSpacing.gutter),
                  children: [
                    InputDecorator(
                      decoration: const InputDecoration(
                        labelText: 'Supplier *',
                        border: OutlineInputBorder(),
                        contentPadding: EdgeInsets.symmetric(
                            horizontal: 12, vertical: 4),
                      ),
                      child: DropdownButton<Supplier>(
                        value: _selectedSupplier,
                        isExpanded: true,
                        underline: const SizedBox.shrink(),
                        hint: const Text('Select supplier'),
                        items: _suppliers
                            .map((s) => DropdownMenuItem(
                                  value: s,
                                  child: Text(s.name),
                                ))
                            .toList(),
                        onChanged: isEdit
                            ? null
                            : (s) => setState(() => _selectedSupplier = s),
                      ),
                    ),
                    const SizedBox(height: AdminSpacing.md),
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        _deliveryDate != null
                            ? 'Delivery: ${DateFormat('MMM d, y').format(_deliveryDate!)}'
                            : 'Expected delivery date (optional)',
                        style: theme.textTheme.bodyMedium,
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (_deliveryDate != null)
                            IconButton(
                              onPressed: () =>
                                  setState(() => _deliveryDate = null),
                              icon: const Icon(Icons.close_rounded),
                              tooltip: 'Clear date',
                            ),
                          IconButton(
                            onPressed: _pickDeliveryDate,
                            icon: const Icon(Icons.calendar_today_outlined),
                            tooltip: 'Pick date',
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: AdminSpacing.md),
                    TextField(
                      controller: _notesCtrl,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        labelText: 'Notes (optional)',
                        border: OutlineInputBorder(),
                        alignLabelWithHint: true,
                      ),
                    ),
                    const SizedBox(height: AdminSpacing.xl),
                    Row(
                      children: [
                        Text('Line Items', style: theme.textTheme.titleMedium),
                        const Spacer(),
                        TextButton.icon(
                          onPressed: () =>
                              setState(() => _lines.add(_LineItemState())),
                          icon: const Icon(Icons.add_rounded, size: 18),
                          label: const Text('Add item'),
                        ),
                      ],
                    ),
                    const SizedBox(height: AdminSpacing.sm),
                    ..._lines.asMap().entries.map((entry) {
                      final i = entry.key;
                      final line = entry.value;
                      return Padding(
                        padding:
                            const EdgeInsets.only(bottom: AdminSpacing.md),
                        child: Material(
                          color: AdminColors.surfaceContainerLow,
                          borderRadius:
                              BorderRadius.circular(AdminRadius.quickTile),
                          child: Padding(
                            padding: const EdgeInsets.all(AdminSpacing.md),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: GestureDetector(
                                        onTap: () => _pickProduct(i),
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 12,
                                            vertical: 14,
                                          ),
                                          decoration: BoxDecoration(
                                            border: Border.all(
                                                color:
                                                    AdminColors.outlineVariant),
                                            borderRadius:
                                                BorderRadius.circular(8),
                                            color: AdminColors.card,
                                          ),
                                          child: Text(
                                            line.productName ??
                                                'Tap to select product',
                                            style: theme.textTheme.bodyMedium
                                                ?.copyWith(
                                              color: line.productName != null
                                                  ? AdminColors.onSurface
                                                  : AdminColors
                                                      .onSurfaceVariant,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ),
                                    if (_lines.length > 1) ...[
                                      const SizedBox(width: AdminSpacing.xs),
                                      IconButton(
                                        onPressed: () => setState(() {
                                          line.dispose();
                                          _lines.removeAt(i);
                                        }),
                                        icon: const Icon(
                                            Icons.delete_outline_rounded),
                                        color: AdminColors.onSurfaceVariant,
                                        tooltip: 'Remove line',
                                      ),
                                    ],
                                  ],
                                ),
                                const SizedBox(height: AdminSpacing.sm),
                                Row(
                                  children: [
                                    Expanded(
                                      child: TextField(
                                        controller: line.qtyCtrl,
                                        keyboardType: TextInputType.number,
                                        decoration: const InputDecoration(
                                          labelText: 'Qty',
                                          border: OutlineInputBorder(),
                                        ),
                                        onChanged: (_) => setState(() {}),
                                      ),
                                    ),
                                    const SizedBox(width: AdminSpacing.sm),
                                    Expanded(
                                      flex: 2,
                                      child: TextField(
                                        controller: line.costCtrl,
                                        keyboardType:
                                            const TextInputType.numberWithOptions(
                                                decimal: true),
                                        decoration: const InputDecoration(
                                          labelText: 'Unit cost',
                                          border: OutlineInputBorder(),
                                        ),
                                        onChanged: (_) => setState(() {}),
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    }),
                    if (_error != null) ...[
                      const SizedBox(height: AdminSpacing.md),
                      Text(
                        _error!,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: AdminColors.error),
                      ),
                    ],
                    const SizedBox(height: 80),
                  ],
                ),
    );
  }
}

class _ProductPickerDialog extends StatefulWidget {
  const _ProductPickerDialog({required this.api});
  final AdminApi api;

  @override
  State<_ProductPickerDialog> createState() => _ProductPickerDialogState();
}

class _ProductPickerDialogState extends State<_ProductPickerDialog> {
  final _ctrl = TextEditingController();
  List<Map<String, dynamic>> _results = [];
  bool _searching = false;
  Timer? _debounce;

  @override
  void dispose() {
    _ctrl.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  void _onChanged(String q) {
    _debounce?.cancel();
    if (q.length < 2) {
      setState(() => _results = []);
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 350), () async {
      setState(() => _searching = true);
      try {
        final results = await widget.api.searchProducts(q);
        if (mounted) {
          setState(() {
            _results = results;
            _searching = false;
          });
        }
      } catch (_) {
        if (mounted) setState(() => _searching = false);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Select Product'),
      content: SizedBox(
        width: double.maxFinite,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _ctrl,
              autofocus: true,
              decoration: const InputDecoration(
                hintText: 'Search by name or SKU...',
                prefixIcon: Icon(Icons.search_rounded),
                border: OutlineInputBorder(),
              ),
              onChanged: _onChanged,
            ),
            const SizedBox(height: 8),
            if (_searching)
              const Padding(
                padding: EdgeInsets.all(16),
                child: CircularProgressIndicator(),
              )
            else if (_results.isEmpty && _ctrl.text.length >= 2)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('No products found'),
              )
            else
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: _results.length,
                  itemBuilder: (context, i) {
                    final p = _results[i];
                    return ListTile(
                      title: Text(p['name'] as String? ?? ''),
                      subtitle: Text(p['sku'] as String? ?? ''),
                      onTap: () => Navigator.of(context).pop(p),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}
