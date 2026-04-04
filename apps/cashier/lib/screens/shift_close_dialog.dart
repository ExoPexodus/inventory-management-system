import 'package:flutter/material.dart';

import '../cashier_tokens.dart';
import '../services/inventory_api.dart';
import '../util/money_format.dart';

class ShiftCloseDialog extends StatefulWidget {
  const ShiftCloseDialog({
    super.key,
    required this.accessToken,
    required this.api,
    required this.shift,
    required this.shopId,
  });

  final String accessToken;
  final InventoryApi api;
  final Map<String, dynamic> shift;
  final String shopId;

  @override
  State<ShiftCloseDialog> createState() => _ShiftCloseDialogState();
}

class _ShiftCloseDialogState extends State<ShiftCloseDialog> {
  final _cashController = TextEditingController();
  final _notesController = TextEditingController();
  bool _saving = false;
  String? _error;
  Map<String, dynamic>? _summary;
  bool _summaryLoading = true;

  @override
  void initState() {
    super.initState();
    _loadSummary();
  }

  @override
  void dispose() {
    _cashController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  Future<void> _loadSummary() async {
    try {
      final data = await widget.api.shiftSummary(
        accessToken: widget.accessToken,
        shopId: widget.shopId,
        sinceIso: widget.shift['opened_at'] as String?,
      );
      if (!mounted) return;
      setState(() { _summary = data; _summaryLoading = false; });
    } catch (_) {
      if (!mounted) return;
      setState(() => _summaryLoading = false);
    }
  }

  Future<void> _submit() async {
    final dollars = double.tryParse(_cashController.text.trim());
    if (dollars == null || dollars < 0) {
      setState(() => _error = 'Enter a valid cash amount');
      return;
    }
    final cents = (dollars * 100).round();
    setState(() { _saving = true; _error = null; });
    try {
      await widget.api.closeShift(
        accessToken: widget.accessToken,
        shiftId: widget.shift['id'] as String,
        reportedCashCents: cents,
        notes: _notesController.text.trim().isEmpty ? null : _notesController.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      String msg = 'Failed (${e.statusCode})';
      if (e.statusCode == 409) msg = 'Shift is already closed.';
      setState(() { _saving = false; _error = msg; });
    } catch (_) {
      setState(() { _saving = false; _error = 'Unexpected error. Try again.'; });
    }
  }

  String _duration() {
    final openedAt = DateTime.tryParse(widget.shift['opened_at'] as String? ?? '');
    if (openedAt == null) return '';
    final diff = DateTime.now().difference(openedAt);
    final h = diff.inHours;
    final m = diff.inMinutes % 60;
    return h > 0 ? '${h}h ${m}m' : '${m}m';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final txCount = _summary?['transaction_count'] as int? ?? 0;
    final totalCents = _summary?['total_cents'] as int? ?? 0;
    final totalLabel = formatMinorUnits(totalCents, code: 'USD', exponent: 2);

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(CashierSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Close shift', style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text(
                'Duration: ${_duration()}',
                style: theme.textTheme.bodySmall?.copyWith(color: CashierColors.onSurfaceVariant),
              ),
              const SizedBox(height: CashierSpacing.md),
              if (_summaryLoading)
                const Center(child: CircularProgressIndicator())
              else
                Container(
                  decoration: BoxDecoration(
                    color: CashierColors.surfaceContainer,
                    borderRadius: BorderRadius.circular(CashierRadius.quickTile),
                  ),
                  padding: const EdgeInsets.all(CashierSpacing.md),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      Column(children: [
                        Text('$txCount', style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                        Text('Sales', style: theme.textTheme.labelSmall),
                      ]),
                      Column(children: [
                        Text(totalLabel, style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                        Text('Gross', style: theme.textTheme.labelSmall),
                      ]),
                    ],
                  ),
                ),
              const SizedBox(height: CashierSpacing.md),
              TextField(
                controller: _cashController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(
                  labelText: 'Cash counted in drawer *',
                  hintText: 'e.g. 47.50',
                  prefixText: '\$ ',
                ),
              ),
              const SizedBox(height: CashierSpacing.sm),
              TextField(
                controller: _notesController,
                decoration: const InputDecoration(
                  labelText: 'Notes (optional)',
                  hintText: 'Any discrepancy explanation…',
                ),
                maxLines: 2,
              ),
              if (_error != null) ...[
                const SizedBox(height: CashierSpacing.sm),
                Text(_error!, style: theme.textTheme.bodySmall?.copyWith(color: CashierColors.error)),
              ],
              const SizedBox(height: CashierSpacing.md),
              FilledButton(
                onPressed: _saving ? null : _submit,
                style: FilledButton.styleFrom(backgroundColor: CashierColors.error),
                child: Text(_saving ? 'Closing…' : 'Close shift'),
              ),
              const SizedBox(height: CashierSpacing.sm),
              TextButton(
                onPressed: _saving ? null : () => Navigator.of(context).pop(false),
                child: const Text('Cancel'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
