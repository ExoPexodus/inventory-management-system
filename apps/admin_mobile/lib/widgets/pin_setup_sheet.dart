import 'package:flutter/material.dart';

import '../admin_tokens.dart';

/// A bottom sheet that collects a 4–8 digit PIN with a confirmation step.
/// Pops with the PIN string on success, or `null` if the user skips/cancels.
class PinSetupSheet extends StatefulWidget {
  const PinSetupSheet({
    super.key,
    this.title = 'Set a PIN for quick access',
    this.subtitle =
        'Use 4–8 digits. You can sign in with your password any time.',
    this.cancelLabel = 'Skip',
  });

  final String title;
  final String subtitle;
  final String cancelLabel;

  @override
  State<PinSetupSheet> createState() => _PinSetupSheetState();
}

class _PinSetupSheetState extends State<PinSetupSheet> {
  String _pin = '';
  String _confirm = '';
  bool _confirming = false;
  String? _error;

  void _append(String d) {
    if (_confirming) {
      if (_confirm.length >= 8) return;
      setState(() {
        _confirm = '$_confirm$d';
        _error = null;
      });
      if (_confirm.length >= _pin.length) _finish();
    } else {
      if (_pin.length >= 8) return;
      setState(() => _pin = '$_pin$d');
    }
  }

  void _backspace() {
    setState(() {
      if (_confirming) {
        if (_confirm.isEmpty) return;
        _confirm = _confirm.substring(0, _confirm.length - 1);
      } else {
        if (_pin.isEmpty) return;
        _pin = _pin.substring(0, _pin.length - 1);
      }
    });
  }

  void _next() {
    if (_pin.length < 4) {
      setState(() => _error = 'PIN must be at least 4 digits');
      return;
    }
    setState(() {
      _confirming = true;
      _error = null;
    });
  }

  void _finish() {
    if (_confirm != _pin) {
      setState(() {
        _confirm = '';
        _error = 'PINs do not match. Try again.';
      });
      return;
    }
    Navigator.of(context).pop(_pin);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final current = _confirming ? _confirm : _pin;
    final dotCount =
        _confirming ? _pin.length : (_pin.isEmpty ? 4 : _pin.length);
    return Padding(
      padding: EdgeInsets.only(
        left: AdminSpacing.gutter,
        right: AdminSpacing.gutter,
        top: AdminSpacing.lg,
        bottom: MediaQuery.of(context).viewInsets.bottom + AdminSpacing.lg,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 40,
            height: 4,
            margin: const EdgeInsets.only(bottom: AdminSpacing.md),
            decoration: BoxDecoration(
              color: theme.colorScheme.outlineVariant,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Text(
            _confirming ? 'Confirm your PIN' : widget.title,
            style:
                theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 6),
          Text(
            _confirming ? 'Enter the same PIN again' : widget.subtitle,
            style: theme.textTheme.bodyMedium
                ?.copyWith(color: AdminColors.onSurfaceVariant),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(dotCount, (i) {
              final filled = i < current.length;
              return Container(
                margin: const EdgeInsets.symmetric(horizontal: 6),
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: filled
                      ? theme.colorScheme.primary
                      : theme.colorScheme.outlineVariant,
                ),
              );
            }),
          ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            alignment: WrapAlignment.center,
            children: [
              for (final n in ['1', '2', '3', '4', '5', '6', '7', '8', '9'])
                _Key(label: n, onTap: () => _append(n)),
              const SizedBox(width: 86, height: 56),
              _Key(label: '0', onTap: () => _append('0')),
              _Key(label: '⌫', onTap: _backspace),
            ],
          ),
          if (_error != null) ...[
            const SizedBox(height: AdminSpacing.md),
            Text(_error!,
                style: TextStyle(color: theme.colorScheme.error),
                textAlign: TextAlign.center),
          ],
          const SizedBox(height: AdminSpacing.lg),
          Row(
            children: [
              Expanded(
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(null),
                  child: Text(widget.cancelLabel),
                ),
              ),
              const SizedBox(width: AdminSpacing.md),
              Expanded(
                child: FilledButton(
                  onPressed: _confirming ? null : _next,
                  child: const Text('Continue'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Key extends StatelessWidget {
  const _Key({required this.label, required this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 86,
      height: 56,
      child: FilledButton.tonal(
        onPressed: onTap,
        child: Text(label,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
      ),
    );
  }
}
