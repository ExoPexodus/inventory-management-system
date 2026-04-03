import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../cashier_tokens.dart';
import '../services/inventory_api.dart';
import '../services/session_store.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, required this.onSuccess});

  final VoidCallback onSuccess;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final MobileScannerController _scanner = MobileScannerController();
  bool _busy = false;
  bool _handled = false;
  String? _error;

  @override
  void dispose() {
    _scanner.dispose();
    super.dispose();
  }

  Future<void> _handleQr(String rawValue) async {
    if (_busy || _handled) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final payload = jsonDecode(rawValue) as Map<String, dynamic>;
      final apiUrl = (payload['api'] ?? payload['api_url']) as String?;
      final token = (payload['tok'] ?? payload['enrollment_token']) as String?;
      final qrEmployeeId = (payload['eid'] ?? payload['employee_id']) as String?;
      if (apiUrl == null || apiUrl.isEmpty || token == null || token.isEmpty) {
        throw Exception('Invalid QR payload');
      }

      final api = InventoryApi(apiUrl);
      final fingerprint = 'fp-${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(1 << 20)}';
      final body = await api.enroll(
        enrollmentToken: token,
        deviceFingerprint: fingerprint,
        platform: Theme.of(context).platform == TargetPlatform.iOS ? 'ios' : 'android',
      );
      final shopIds = (body['shop_ids'] as List<dynamic>).map((e) => e.toString()).toList();
      final employeeName = body['employee_name'] as String?;
      final employeeCredentialType = body['employee_credential_type'] as String?;
      await SessionStore.save(
        baseUrl: apiUrl,
        accessToken: body['access_token'] as String,
        refreshToken: body['refresh_token'] as String,
        tenantId: body['tenant_id'] as String,
        shopIds: shopIds,
        pendingEmployeeId: (body['employee_id'] as String?) ?? qrEmployeeId,
        pendingEmployeeName: employeeName,
        pendingEmployeeCredentialType: employeeCredentialType,
      );
      _handled = true;
      if (mounted) widget.onSuccess();
    } on ApiException catch (e) {
      setState(() => _error = 'Server error (${e.statusCode})');
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
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
                  padding: const EdgeInsets.only(top: 32, bottom: 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Device onboarding',
                        style: theme.textTheme.headlineSmall,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Scan the staff invite QR from admin dashboard to enroll this device.',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: CashierColors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: SizedBox(
                    height: 360,
                    child: MobileScanner(
                      controller: _scanner,
                      onDetect: (capture) {
                        final code = capture.barcodes.isNotEmpty ? capture.barcodes.first.rawValue : null;
                        if (code != null && code.isNotEmpty) {
                          void _ = _handleQr(code);
                        }
                      },
                    ),
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    'Point camera at onboarding QR. Enrollment runs automatically after scan.',
                    style: theme.textTheme.bodySmall?.copyWith(color: CashierColors.onSurfaceVariant),
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
