import 'dart:math';

import 'package:flutter/material.dart';

import '../cashier_tokens.dart';
import '../services/inventory_api.dart';
import '../services/session_store.dart';
import '../widgets/gradient_primary_button.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, required this.onSuccess});

  final VoidCallback onSuccess;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _urlCtrl = TextEditingController(text: 'http://localhost:8001');
  final _tokenCtrl = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _urlCtrl.dispose();
    _tokenCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final url = _urlCtrl.text.trim();
      final api = InventoryApi(url);
      final fingerprint =
          'fp-${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(1 << 20)}';
      final body = await api.enroll(
        enrollmentToken: _tokenCtrl.text.trim(),
        deviceFingerprint: fingerprint,
        platform: Theme.of(context).platform == TargetPlatform.iOS ? 'ios' : 'android',
      );
      final shopIds = (body['shop_ids'] as List<dynamic>).map((e) => e.toString()).toList();
      await SessionStore.save(
        baseUrl: url,
        accessToken: body['access_token'] as String,
        refreshToken: body['refresh_token'] as String,
        tenantId: body['tenant_id'] as String,
        shopIds: shopIds,
      );
      if (mounted) widget.onSuccess();
    } on ApiException catch (e) {
      setState(() => _error = 'Server error (${e.statusCode})');
    } catch (e) {
      setState(() => _error = e.toString());
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
          padding: const EdgeInsets.symmetric(horizontal: CashierSpacing.gutter),
          child: CustomScrollView(
            slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: 32, bottom: 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Device onboarding',
                      style: theme.textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Connect this register with a one-time enrollment token from your admin or seed script.',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: CashierColors.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Material(
                color: CashierColors.surfaceContainer,
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: const EdgeInsets.all(CashierSpacing.md),
                  child: Text(
                    'Android emulator: http://10.0.2.2:8001 · Physical device: your PC LAN IP.',
                    style: theme.textTheme.labelMedium,
                  ),
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: CashierSpacing.lg),
                child: TextField(
                  controller: _urlCtrl,
                  decoration: const InputDecoration(
                    labelText: 'API base URL',
                  ),
                  keyboardType: TextInputType.url,
                  autocorrect: false,
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: CashierSpacing.md),
                child: TextField(
                  controller: _tokenCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Enrollment token',
                  ),
                  autocorrect: false,
                ),
              ),
            ),
            if (_error != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.only(top: CashierSpacing.md),
                  child: Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ),
              ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: CashierSpacing.lg, bottom: 32),
                child: CashierGradientButton(
                  label: 'Enroll device',
                  onPressed: _busy ? null : _submit,
                  icon: Icons.login_rounded,
                ),
              ),
            ),
            if (_busy)
              const SliverToBoxAdapter(
                child: Center(
                  child: Padding(
                    padding: EdgeInsets.all(16),
                    child: SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
