import 'package:flutter/material.dart';

import '../admin_tokens.dart';
import '../models/session.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/pin_setup_sheet.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.baseUrl,
    required this.onSuccess,
    required this.onResetDevice,
  });

  final String baseUrl;
  final Future<void> Function() onSuccess;
  final VoidCallback onResetDevice;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  bool _loading = true;
  bool _pinEnabled = false;
  bool _showPinPad = false; // true when local flag says PIN is set and user hasn't switched to password

  @override
  void initState() {
    super.initState();
    _loadPinState();
  }

  Future<void> _loadPinState() async {
    final enabled = await SessionStore.isPinEnabled();
    if (mounted) {
      setState(() {
        _pinEnabled = enabled;
        _showPinPad = enabled;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_showPinPad) {
      return _PinLoginView(
        baseUrl: widget.baseUrl,
        onSuccess: widget.onSuccess,
        onUsePassword: () => setState(() => _showPinPad = false),
        onForgotPin: () async {
          await SessionStore.setPinEnabled(false);
          if (mounted) {
            setState(() {
              _pinEnabled = false;
              _showPinPad = false;
            });
          }
        },
        onResetDevice: widget.onResetDevice,
      );
    }
    return _PasswordLoginView(
      baseUrl: widget.baseUrl,
      pinPreviouslyEnabled: _pinEnabled,
      onUsePin: _pinEnabled ? () => setState(() => _showPinPad = true) : null,
      onSuccess: widget.onSuccess,
      onResetDevice: widget.onResetDevice,
    );
  }
}

// ──────────────────────────────────────────────────────────────────────
// PIN login view
// ──────────────────────────────────────────────────────────────────────

class _PinLoginView extends StatefulWidget {
  const _PinLoginView({
    required this.baseUrl,
    required this.onSuccess,
    required this.onUsePassword,
    required this.onForgotPin,
    required this.onResetDevice,
  });

  final String baseUrl;
  final Future<void> Function() onSuccess;
  final VoidCallback onUsePassword;
  final Future<void> Function() onForgotPin;
  final VoidCallback onResetDevice;

  @override
  State<_PinLoginView> createState() => _PinLoginViewState();
}

class _PinLoginViewState extends State<_PinLoginView> {
  String _pin = '';
  bool _busy = false;
  String? _error;

  void _append(String d) {
    if (_pin.length >= 8) return;
    setState(() {
      _pin = '$_pin$d';
      _error = null;
    });
    if (_pin.length >= 4) _submit();
  }

  void _backspace() {
    if (_pin.isEmpty) return;
    setState(() => _pin = _pin.substring(0, _pin.length - 1));
  }

  Future<void> _submit() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final deviceToken = await SessionStore.getDeviceToken();
      if (deviceToken == null) {
        throw Exception('Device is not enrolled');
      }
      final data = await AdminApi.pinLogin(
        baseUrl: widget.baseUrl,
        deviceToken: deviceToken,
        pin: _pin,
      );
      final token = data['access_token'] as String;
      // PIN login response returns `name` but not `email` — fall back to
      // the last-known email so the shell can keep displaying it.
      final lastEmail = await SessionStore.getLastEmail();
      final email = (data['email'] as String?) ?? lastEmail ?? (data['name'] as String? ?? '');
      final role = data['role'] as String?;
      final permissions = (data['permissions'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          [];
      await SessionStore.save(AdminSession(
        token: token,
        email: email,
        baseUrl: widget.baseUrl,
        role: role,
        permissions: permissions,
      ));
      await widget.onSuccess();
    } on ApiException catch (e) {
      setState(() {
        _pin = '';
        if (e.statusCode == 401) {
          _error = 'Incorrect PIN.';
        } else if (e.statusCode == 403) {
          _error = 'Your role no longer grants admin mobile access.';
        } else if (e.statusCode == 404) {
          _error = 'No account is linked to this device. Re-enroll to continue.';
        } else {
          _error = 'Server error (${e.statusCode})';
        }
      });
    } catch (e) {
      setState(() {
        _pin = '';
        _error = 'Could not connect to server.';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding:
              const EdgeInsets.symmetric(horizontal: AdminSpacing.gutter),
          child: Column(
            children: [
              const SizedBox(height: 48),
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: AdminColors.primary,
                  borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                ),
                child: const Icon(Icons.lock_outline_rounded,
                    color: Colors.white, size: 32),
              ),
              const SizedBox(height: 24),
              Text(
                'Enter your PIN',
                style: theme.textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              Text(
                'Quick unlock for this device',
                style: theme.textTheme.bodyMedium
                    ?.copyWith(color: AdminColors.onSurfaceVariant),
              ),
              const SizedBox(height: 32),
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
              const SizedBox(height: 24),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                alignment: WrapAlignment.center,
                children: [
                  for (final n in ['1', '2', '3', '4', '5', '6', '7', '8', '9'])
                    _PinKey(label: n, onTap: _busy ? null : () => _append(n)),
                  const SizedBox(width: 86, height: 56),
                  _PinKey(label: '0', onTap: _busy ? null : () => _append('0')),
                  _PinKey(label: '⌫', onTap: _busy ? null : _backspace),
                ],
              ),
              if (_error != null) ...[
                const SizedBox(height: AdminSpacing.md),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AdminColors.errorContainer.withValues(alpha: 0.4),
                    borderRadius: BorderRadius.circular(AdminRadius.chip),
                  ),
                  child: Text(
                    _error!,
                    style: TextStyle(color: AdminColors.onErrorContainer),
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
              if (_busy) ...[
                const SizedBox(height: AdminSpacing.md),
                const SizedBox(
                  height: 20,
                  width: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ],
              const Spacer(),
              TextButton(
                onPressed: _busy ? null : widget.onUsePassword,
                child: const Text('Use password instead'),
              ),
              TextButton(
                onPressed: _busy
                    ? null
                    : () async {
                        final confirm = await showDialog<bool>(
                          context: context,
                          builder: (ctx) => AlertDialog(
                            title: const Text('Forgot PIN?'),
                            content: const Text(
                                'Your PIN will be cleared on this device. Sign in with your password to set a new one.'),
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.of(ctx).pop(false),
                                child: const Text('Cancel'),
                              ),
                              TextButton(
                                onPressed: () => Navigator.of(ctx).pop(true),
                                child: const Text('Clear PIN'),
                              ),
                            ],
                          ),
                        );
                        if (confirm == true) await widget.onForgotPin();
                      },
                child: Text(
                  'Forgot PIN?',
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: AdminColors.onSurfaceVariant),
                ),
              ),
              TextButton(
                onPressed: _busy ? null : widget.onResetDevice,
                child: Text(
                  'Switch device',
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: AdminColors.onSurfaceVariant),
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

class _PinKey extends StatelessWidget {
  const _PinKey({required this.label, required this.onTap});

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

// ──────────────────────────────────────────────────────────────────────
// Password login view
// ──────────────────────────────────────────────────────────────────────

class _PasswordLoginView extends StatefulWidget {
  const _PasswordLoginView({
    required this.baseUrl,
    required this.pinPreviouslyEnabled,
    required this.onUsePin,
    required this.onSuccess,
    required this.onResetDevice,
  });

  final String baseUrl;
  final bool pinPreviouslyEnabled;
  final VoidCallback? onUsePin;
  final Future<void> Function() onSuccess;
  final VoidCallback onResetDevice;

  @override
  State<_PasswordLoginView> createState() => _PasswordLoginViewState();
}

class _PasswordLoginViewState extends State<_PasswordLoginView> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await AdminApi.login(
        baseUrl: widget.baseUrl,
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
      );
      final token = data['access_token'] as String;
      final role = data['role'] as String?;
      final permissions = (data['permissions'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          [];
      final session = AdminSession(
        token: token,
        email: _emailCtrl.text.trim(),
        baseUrl: widget.baseUrl,
        role: role,
        permissions: permissions,
      );
      await SessionStore.save(session);
      if (!mounted) return;
      // Offer PIN setup if the user hasn't already got one configured.
      if (!widget.pinPreviouslyEnabled) {
        await _offerPinSetup(session);
      }
      await widget.onSuccess();
    } on ApiException catch (e) {
      setState(() {
        if (e.statusCode == 401) {
          _error = 'Invalid email or password.';
        } else if (e.statusCode == 403) {
          _error = 'Your role does not grant admin mobile access.';
        } else {
          _error = 'Server error (${e.statusCode})';
        }
      });
    } catch (e) {
      setState(() => _error = 'Could not connect to server.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _offerPinSetup(AdminSession session) async {
    final pin = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      isDismissible: false,
      enableDrag: false,
      builder: (ctx) => const PinSetupSheet(),
    );
    if (pin == null || pin.isEmpty) return;
    try {
      await AdminApi(session.baseUrl, session.token).setPin(pin);
      await SessionStore.setPinEnabled(true);
    } catch (_) {
      // Non-fatal — user can set PIN later from settings.
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: AdminSpacing.gutter),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 48),
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: AdminColors.primary,
                      borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                    ),
                    child: const Icon(Icons.store_rounded,
                        color: Colors.white, size: 32),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    'Admin Dashboard',
                    style: theme.textTheme.headlineSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Sign in to manage your business',
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(color: AdminColors.onSurfaceVariant),
                  ),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _emailCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    keyboardType: TextInputType.emailAddress,
                    autocorrect: false,
                    validator: (v) =>
                        (v == null || v.trim().isEmpty) ? 'Enter your email' : null,
                  ),
                  const SizedBox(height: AdminSpacing.md),
                  TextFormField(
                    controller: _passwordCtrl,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline_rounded),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure
                            ? Icons.visibility_outlined
                            : Icons.visibility_off_outlined),
                        onPressed: () =>
                            setState(() => _obscure = !_obscure),
                      ),
                    ),
                    obscureText: _obscure,
                    validator: (v) =>
                        (v == null || v.isEmpty) ? 'Enter your password' : null,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: AdminSpacing.md),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color:
                            AdminColors.errorContainer.withValues(alpha: 0.4),
                        borderRadius:
                            BorderRadius.circular(AdminRadius.chip),
                      ),
                      child: Text(
                        _error!,
                        style:
                            TextStyle(color: AdminColors.onErrorContainer),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ],
                  const SizedBox(height: AdminSpacing.lg),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Text('Sign in'),
                  ),
                  if (widget.onUsePin != null) ...[
                    const SizedBox(height: AdminSpacing.md),
                    OutlinedButton.icon(
                      onPressed: _busy ? null : widget.onUsePin,
                      icon: const Icon(Icons.pin_outlined),
                      label: const Text('Use PIN instead'),
                    ),
                  ],
                  const SizedBox(height: AdminSpacing.lg),
                  Center(
                    child: TextButton(
                      onPressed: widget.onResetDevice,
                      child: Text(
                        'Switch device',
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: AdminColors.onSurfaceVariant),
                      ),
                    ),
                  ),
                  const SizedBox(height: 48),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

