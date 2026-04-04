import 'package:flutter/material.dart';

import '../cashier_tokens.dart';
import '../services/inventory_api.dart';

class ShiftOpenDialog extends StatefulWidget {
  const ShiftOpenDialog({
    super.key,
    required this.accessToken,
    required this.api,
  });

  final String accessToken;
  final InventoryApi api;

  @override
  State<ShiftOpenDialog> createState() => _ShiftOpenDialogState();
}

class _ShiftOpenDialogState extends State<ShiftOpenDialog> {
  final _notesController = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _notesController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() { _saving = true; _error = null; });
    try {
      await widget.api.openShift(
        accessToken: widget.accessToken,
        notes: _notesController.text.trim().isEmpty ? null : _notesController.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      String msg = 'Failed (${e.statusCode})';
      if (e.statusCode == 409) msg = 'A shift is already open for this shop.';
      setState(() { _saving = false; _error = msg; });
    } catch (_) {
      setState(() { _saving = false; _error = 'Unexpected error. Try again.'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(CashierSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Open shift', style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text(
                'Starting a shift will track all cash sales against your till.',
                style: theme.textTheme.bodySmall?.copyWith(color: CashierColors.onSurfaceVariant),
              ),
              const SizedBox(height: CashierSpacing.md),
              TextField(
                controller: _notesController,
                decoration: const InputDecoration(
                  labelText: 'Opening notes (optional)',
                  hintText: 'e.g. Opening float: \$50',
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
                child: Text(_saving ? 'Opening…' : 'Open shift'),
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
