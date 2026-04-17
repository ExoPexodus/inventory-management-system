import 'package:flutter/material.dart';

import '../cashier_tokens.dart';
import '../services/inventory_api.dart';
import '../services/session_store.dart';
import '../widgets/gradient_primary_button.dart';

class EmployeeLoginScreen extends StatefulWidget {
  const EmployeeLoginScreen({
    super.key,
    required this.session,
    required this.onSuccess,
  });

  final SessionData session;
  final VoidCallback onSuccess;

  @override
  State<EmployeeLoginScreen> createState() => _EmployeeLoginScreenState();
}

class _EmployeeLoginScreenState extends State<EmployeeLoginScreen> {
  final _passwordCtrl = TextEditingController();
  bool _busy = false;
  String? _error;
  bool _showReEnrollPrompt = false;
  late final bool _isPasswordMode;
  String _pin = '';

  @override
  void initState() {
    super.initState();
    // Prefer the freshly-enrolled credential type; fall back to any previously
    // stored employee session type (covers devices enrolled before this change).
    _isPasswordMode =
        (widget.session.pendingEmployeeCredentialType ?? widget.session.employeeCredentialType) == 'password';
  }

  @override
  void dispose() {
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = InventoryApi(widget.session.baseUrl);
      final credential = _isPasswordMode ? _passwordCtrl.text.trim() : _pin;
      if (credential.isEmpty) {
        throw Exception(_isPasswordMode ? 'Enter password' : 'Enter PIN');
      }
      final body = await api.employeeLogin(
        accessToken: widget.session.accessToken,
        credential: credential,
        employeeId: widget.session.pendingEmployeeId,
      );
      await SessionStore.saveEmployeeSession(
        employeeId: body['employee_id'] as String,
        name: body['name'] as String,
        email: body['email'] as String,
        position: body['position'] as String,
        credentialType: body['credential_type'] as String,
      );
      if (mounted) widget.onSuccess();
    } on ApiException catch (e) {
      if (e.statusCode == 403 && e.body.contains('deactivated')) {
        setState(() => _error = 'Your account has been deactivated. Please contact your administrator to reactivate it.');
      } else if (e.statusCode == 403 && e.body.contains('cashier app access')) {
        setState(() => _error = 'Your role no longer grants cashier app access. Contact your administrator.');
      } else if (e.statusCode == 401 && e.body.contains('not linked')) {
        setState(() {
          _error = 'This device is no longer linked to an employee account. Re-enroll to continue.';
          _showReEnrollPrompt = true;
        });
      } else if (e.statusCode == 401) {
        setState(() => _error = 'Incorrect PIN or password.');
      } else {
        setState(() => _error = 'Server error (${e.statusCode})');
      }
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _reEnroll() async {
    await SessionStore.clear();
    if (mounted) widget.onSuccess();
  }

  void _appendPin(String digit) {
    if (_pin.length >= 8) return;
    setState(() => _pin = '$_pin$digit');
  }

  void _backspacePin() {
    if (_pin.isEmpty) return;
    setState(() => _pin = _pin.substring(0, _pin.length - 1));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final name = widget.session.pendingEmployeeName;
    final hasName = name != null && name.isNotEmpty;

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.only(top: 48, bottom: 32),
                  child: Column(
                    children: [
                      // Avatar
                      CircleAvatar(
                        radius: 32,
                        backgroundColor: theme.colorScheme.primaryContainer,
                        child: Text(
                          hasName
                              ? name.trim().split(' ').map((w) => w.isNotEmpty ? w[0].toUpperCase() : '').take(2).join()
                              : '?',
                          style: theme.textTheme.titleLarge?.copyWith(
                            color: theme.colorScheme.onPrimaryContainer,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      if (hasName) ...[
                        Text(
                          'Welcome back,',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: CashierColors.onSurfaceVariant,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          name,
                          style: theme.textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ] else ...[
                        Text(
                          'Employee sign in',
                          style: theme.textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Device is enrolled. Sign in to continue.',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: CashierColors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),

              if (_isPasswordMode)
                SliverToBoxAdapter(
                  child: TextField(
                    controller: _passwordCtrl,
                    decoration: const InputDecoration(labelText: 'Password'),
                    obscureText: true,
                    autofocus: true,
                  ),
                )
              else
                SliverToBoxAdapter(
                  child: Column(
                    children: [
                      // PIN dot indicators
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: List.generate(4, (i) {
                          final filled = i < _pin.length;
                          return Container(
                            margin: const EdgeInsets.symmetric(horizontal: 8),
                            width: 14,
                            height: 14,
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
                      // PIN pad
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        alignment: WrapAlignment.center,
                        children: [
                          for (final n in ['1', '2', '3', '4', '5', '6', '7', '8', '9'])
                            _PinButton(label: n, onTap: () => _appendPin(n)),
                          _PinButton(label: '0', onTap: () => _appendPin('0')),
                          _PinButton(label: '⌫', onTap: _backspacePin),
                        ],
                      ),
                    ],
                  ),
                ),

              if (_error != null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.only(top: CashierSpacing.md),
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.errorContainer.withValues(alpha: 0.3),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        _error!,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: theme.colorScheme.error),
                      ),
                    ),
                  ),
                ),

              if (_showReEnrollPrompt)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.only(top: CashierSpacing.md),
                    child: FilledButton.icon(
                      onPressed: _busy ? null : _reEnroll,
                      icon: const Icon(Icons.qr_code_scanner_rounded),
                      label: const Text('Re-enroll this device'),
                    ),
                  ),
                )
              else ...[
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.only(top: CashierSpacing.lg),
                    child: CashierGradientButton(
                      label: _busy ? 'Signing in...' : 'Sign in',
                      onPressed: _busy ? null : _submit,
                      icon: Icons.lock_open_rounded,
                    ),
                  ),
                ),

                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.only(top: CashierSpacing.md, bottom: 32),
                    child: Center(
                      child: TextButton(
                        onPressed: _busy ? null : _reEnroll,
                        child: Text(
                          'Not you? Re-enroll this device',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: CashierColors.onSurfaceVariant,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _PinButton extends StatelessWidget {
  const _PinButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 86,
      height: 56,
      child: FilledButton.tonal(
        onPressed: onTap,
        child: Text(label, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
      ),
    );
  }
}
