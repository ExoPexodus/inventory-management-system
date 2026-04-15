import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../admin_tokens.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';

class EnrollmentScreen extends StatefulWidget {
  const EnrollmentScreen({super.key, required this.onSuccess});

  final VoidCallback onSuccess;

  @override
  State<EnrollmentScreen> createState() => _EnrollmentScreenState();
}

class _EnrollmentScreenState extends State<EnrollmentScreen> {
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
      if (apiUrl == null || apiUrl.isEmpty || token == null || token.isEmpty) {
        throw Exception('Invalid QR code — missing API URL or enrollment token');
      }

      final fingerprint =
          'fp-${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(1 << 20)}';
      final body = await AdminApi.enroll(
        baseUrl: apiUrl,
        enrollmentToken: token,
        deviceFingerprint: fingerprint,
        platform: Theme.of(context).platform == TargetPlatform.iOS
            ? 'ios'
            : 'android',
      );

      await SessionStore.saveEnrollment(
        baseUrl: apiUrl,
        deviceToken: body['access_token'] as String,
        refreshToken: body['refresh_token'] as String,
        tenantId: body['tenant_id'] as String,
      );

      _handled = true;
      if (mounted) widget.onSuccess();
    } on ApiException catch (e) {
      setState(() => _error = 'Enrollment failed (${e.statusCode})');
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
          padding:
              const EdgeInsets.symmetric(horizontal: AdminSpacing.gutter),
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.only(top: 32, bottom: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 56,
                        height: 56,
                        decoration: BoxDecoration(
                          color: AdminColors.primary,
                          borderRadius:
                              BorderRadius.circular(AdminRadius.quickTile),
                        ),
                        child: const Icon(Icons.store_rounded,
                            color: Colors.white, size: 28),
                      ),
                      const SizedBox(height: 20),
                      Text(
                        'Device enrollment',
                        style: theme.textTheme.headlineSmall
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Scan the enrollment QR code from the admin dashboard to set up this device.',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: AdminColors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 16)),
              SliverToBoxAdapter(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: SizedBox(
                    height: 340,
                    child: MobileScanner(
                      controller: _scanner,
                      onDetect: (capture) {
                        final code = capture.barcodes.isNotEmpty
                            ? capture.barcodes.first.rawValue
                            : null;
                        if (code != null && code.isNotEmpty) {
                          _handleQr(code);
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
                    'Point camera at the enrollment QR code. Setup runs automatically after scan.',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: AdminColors.onSurfaceVariant),
                  ),
                ),
              ),
              if (_error != null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.only(top: AdminSpacing.md),
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AdminColors.errorContainer.withValues(alpha: 0.4),
                        borderRadius:
                            BorderRadius.circular(AdminRadius.chip),
                      ),
                      child: Text(
                        _error!,
                        style:
                            TextStyle(color: AdminColors.onErrorContainer),
                      ),
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
