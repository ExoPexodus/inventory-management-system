import 'package:flutter/material.dart';

import '../admin_tokens.dart';
import '../models/session.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.onSuccess});

  final Future<void> Function() onSuccess;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _urlCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadSavedUrl();
  }

  Future<void> _loadSavedUrl() async {
    final saved = await SessionStore.getSavedBaseUrl();
    if (saved != null && mounted) {
      _urlCtrl.text = saved;
    }
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
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
        baseUrl: _urlCtrl.text.trim(),
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
      );
      final token = data['access_token'] as String;
      final role = data['role'] as String?;
      final permissions = (data['permissions'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          [];
      await SessionStore.save(AdminSession(
        token: token,
        email: _emailCtrl.text.trim(),
        baseUrl: _urlCtrl.text.trim(),
        role: role,
        permissions: permissions,
      ));
      await widget.onSuccess();
    } on ApiException catch (e) {
      setState(() {
        _error = e.statusCode == 401
            ? 'Invalid email or password.'
            : 'Server error (${e.statusCode})';
      });
    } catch (e) {
      setState(() => _error = 'Could not connect. Check the URL.');
    } finally {
      if (mounted) setState(() => _busy = false);
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
                  // Logo / brand
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: AdminColors.primary,
                      borderRadius: BorderRadius.circular(AdminRadius.quickTile),
                    ),
                    child: const Icon(Icons.store_rounded, color: Colors.white, size: 32),
                  ),
                  const SizedBox(height: 24),
                  Text(
                    'Admin Dashboard',
                    style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Sign in to manage your business',
                    style: theme.textTheme.bodyMedium?.copyWith(color: AdminColors.onSurfaceVariant),
                  ),
                  const SizedBox(height: 32),
                  TextFormField(
                    controller: _urlCtrl,
                    decoration: const InputDecoration(
                      labelText: 'API Base URL',
                      hintText: 'http://192.168.1.x:8001',
                      prefixIcon: Icon(Icons.dns_rounded),
                    ),
                    keyboardType: TextInputType.url,
                    autocorrect: false,
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter the API URL' : null,
                  ),
                  const SizedBox(height: AdminSpacing.md),
                  TextFormField(
                    controller: _emailCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.email_outlined),
                    ),
                    keyboardType: TextInputType.emailAddress,
                    autocorrect: false,
                    validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter your email' : null,
                  ),
                  const SizedBox(height: AdminSpacing.md),
                  TextFormField(
                    controller: _passwordCtrl,
                    decoration: InputDecoration(
                      labelText: 'Password',
                      prefixIcon: const Icon(Icons.lock_outline_rounded),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    obscureText: _obscure,
                    validator: (v) => (v == null || v.isEmpty) ? 'Enter your password' : null,
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
                  const SizedBox(height: AdminSpacing.lg),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: _busy
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                          )
                        : const Text('Sign in'),
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
