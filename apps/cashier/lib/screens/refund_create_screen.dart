import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../cashier_tokens.dart';
import '../services/authenticated_api.dart';
import '../services/session_store.dart' show SessionStore;
import '../util/money_format.dart';

/// Cashier-initiated refund request for an in-store sale.
///
/// Backed by POST /v1/cashier/refund-requests. The cashier picks which lines
/// (and quantities) to refund from the original transaction, selects a reason
/// code, and submits. The merchant approves the request from admin-web.
class RefundCreateScreen extends StatefulWidget {
  const RefundCreateScreen({
    super.key,
    required this.transaction,
  });

  /// The transaction to refund against, as returned by `GET /v1/transactions`.
  /// Expected keys: `id`, `total_cents`, `customer_phone`, `customer_email`,
  /// `lines` (list of {id, product_name, product_sku, quantity, unit_price_cents}).
  final Map<String, dynamic> transaction;

  @override
  State<RefundCreateScreen> createState() => _RefundCreateScreenState();
}

class _RefundCreateScreenState extends State<RefundCreateScreen> {
  // Per-line refund quantity (line_id -> qty). 0 means "skip this line".
  late Map<String, int> _refundQty;
  String _reasonCode = 'damaged';
  final _noteCtrl = TextEditingController();

  String _currencyCode = 'USD';
  int _currencyExponent = 2;
  String? _currencySymbolOverride;

  bool _submitting = false;
  String? _error;

  static const _reasonOptions = <Map<String, String>>[
    {'value': 'damaged', 'label': 'Damaged'},
    {'value': 'wrong_item', 'label': 'Wrong item'},
    {'value': 'doesnt_fit', 'label': "Doesn't fit"},
    {'value': 'changed_mind', 'label': 'Changed mind'},
    {'value': 'other', 'label': 'Other'},
  ];

  @override
  void initState() {
    super.initState();
    final lines = (widget.transaction['lines'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
    _refundQty = {
      for (final ln in lines) ln['id'] as String: 0,
    };
    _loadCurrency();
  }

  Future<void> _loadCurrency() async {
    final code = await SessionStore.getCurrencyCode();
    final exp = await SessionStore.getCurrencyExponent();
    final sym = await SessionStore.getCurrencySymbolOverride();
    if (!mounted) return;
    setState(() {
      _currencyCode = code;
      _currencyExponent = exp;
      _currencySymbolOverride = sym;
    });
  }

  @override
  void dispose() {
    _noteCtrl.dispose();
    super.dispose();
  }

  int get _totalRefundCents {
    final lines = (widget.transaction['lines'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
    int total = 0;
    for (final ln in lines) {
      final qty = _refundQty[ln['id'] as String] ?? 0;
      total += qty * (ln['unit_price_cents'] as int);
    }
    return total;
  }

  bool get _canSubmit {
    if (_submitting) return false;
    if (_refundQty.values.every((q) => q == 0)) return false;
    if (_reasonCode == 'other' && _noteCtrl.text.trim().isEmpty) return false;
    return true;
  }

  Future<void> _submit() async {
    final payloadLines = <Map<String, dynamic>>[];
    for (final entry in _refundQty.entries) {
      if (entry.value > 0) {
        payloadLines.add({
          'transaction_line_id': entry.key,
          'quantity_requested': entry.value,
        });
      }
    }
    if (payloadLines.isEmpty) return;

    setState(() {
      _submitting = true;
      _error = null;
    });

    final auth = context.read<AuthenticatedApi>();
    try {
      await auth.run((api, sess) => api.createRefundRequest(
            accessToken: sess.accessToken,
            saleTransactionId: widget.transaction['id'] as String,
            reasonCode: _reasonCode,
            reasonNote: _noteCtrl.text.trim().isEmpty ? null : _noteCtrl.text.trim(),
            customerEmail: widget.transaction['customer_email'] as String?,
            customerName: widget.transaction['customer_name'] as String?,
            lines: payloadLines,
          ));
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Refund request submitted. Merchant will review.'),
      ));
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lines = (widget.transaction['lines'] as List<dynamic>)
        .cast<Map<String, dynamic>>();
    final saleTotal = widget.transaction['total_cents'] as int;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Refund sale'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(CashierSpacing.md),
                children: [
                  // Sale header
                  Card(
                    color: CashierColors.card,
                    child: Padding(
                      padding: const EdgeInsets.all(CashierSpacing.md),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Original sale',
                            style: theme.textTheme.labelMedium?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            formatMinorUnits(
                              saleTotal,
                              code: _currencyCode,
                              exponent: _currencyExponent,
                              symbolOverride: _currencySymbolOverride,
                            ),
                            style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                          ),
                          if (widget.transaction['customer_phone'] != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 4),
                              child: Text(
                                'Customer: ${widget.transaction['customer_phone']}',
                                style: theme.textTheme.bodySmall,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: CashierSpacing.md),

                  // Reason
                  Text('Reason', style: theme.textTheme.labelMedium),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 8,
                    children: _reasonOptions.map((opt) {
                      final selected = _reasonCode == opt['value'];
                      return ChoiceChip(
                        label: Text(opt['label']!),
                        selected: selected,
                        onSelected: (_) => setState(() => _reasonCode = opt['value']!),
                      );
                    }).toList(),
                  ),
                  if (_reasonCode == 'other') ...[
                    const SizedBox(height: CashierSpacing.sm),
                    TextField(
                      controller: _noteCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Reason details (required)',
                        border: OutlineInputBorder(),
                      ),
                      maxLines: 2,
                      onChanged: (_) => setState(() {}),
                    ),
                  ],

                  const SizedBox(height: CashierSpacing.md),
                  Text('Items to refund', style: theme.textTheme.labelMedium),
                  const SizedBox(height: 6),

                  // Lines
                  ...lines.map((ln) {
                    final lineId = ln['id'] as String;
                    final qtyOriginal = ln['quantity'] as int;
                    final qtyToRefund = _refundQty[lineId] ?? 0;
                    final cents = ln['unit_price_cents'] as int;
                    final unit = formatMinorUnits(
                      cents,
                      code: _currencyCode,
                      exponent: _currencyExponent,
                      symbolOverride: _currencySymbolOverride,
                    );
                    final title = ln['product_name'] as String? ??
                        ln['product_sku'] as String? ??
                        'Product';

                    return Card(
                      color: CashierColors.card,
                      child: Padding(
                        padding: const EdgeInsets.all(CashierSpacing.sm),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(title, style: theme.textTheme.bodyMedium),
                                  Text(
                                    'Sold: $qtyOriginal × $unit',
                                    style: theme.textTheme.labelSmall,
                                  ),
                                ],
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.remove_circle_outline),
                              onPressed: qtyToRefund > 0
                                  ? () => setState(() => _refundQty[lineId] = qtyToRefund - 1)
                                  : null,
                            ),
                            SizedBox(
                              width: 32,
                              child: Text(
                                '$qtyToRefund',
                                textAlign: TextAlign.center,
                                style: theme.textTheme.titleMedium,
                              ),
                            ),
                            IconButton(
                              icon: const Icon(Icons.add_circle_outline),
                              onPressed: qtyToRefund < qtyOriginal
                                  ? () => setState(() => _refundQty[lineId] = qtyToRefund + 1)
                                  : null,
                            ),
                          ],
                        ),
                      ),
                    );
                  }),

                  if (_error != null) ...[
                    const SizedBox(height: CashierSpacing.md),
                    Container(
                      padding: const EdgeInsets.all(CashierSpacing.sm),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.errorContainer,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        _error!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onErrorContainer,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),

            // Bottom action bar
            Container(
              padding: const EdgeInsets.all(CashierSpacing.md),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                border: Border(top: BorderSide(color: theme.dividerColor)),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Refund total', style: theme.textTheme.labelSmall),
                        Text(
                          formatMinorUnits(
                            _totalRefundCents,
                            code: _currencyCode,
                            exponent: _currencyExponent,
                            symbolOverride: _currencySymbolOverride,
                          ),
                          style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                        ),
                      ],
                    ),
                  ),
                  FilledButton(
                    onPressed: _canSubmit ? _submit : null,
                    child: _submitting
                        ? const SizedBox(
                            width: 16, height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Submit refund request'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
