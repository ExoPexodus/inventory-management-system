import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'models/currency.dart';
import 'models/session.dart';
import 'screens/app_shell.dart';
import 'screens/enrollment_screen.dart';
import 'screens/login_screen.dart';
import 'services/admin_api.dart';
import 'services/session_store.dart';
import 'services/update_service.dart';
import 'theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await UpdateService.initialize();
  runApp(const AdminApp());
}

class AdminApp extends StatelessWidget {
  const AdminApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Admin',
      debugShowCheckedModeBanner: false,
      theme: adminTheme(),
      home: const _StartupGate(),
    );
  }
}

/// Three states: unenrolled → enrolled (login) → logged in (app shell).
class _StartupGate extends StatefulWidget {
  const _StartupGate();

  @override
  State<_StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<_StartupGate> {
  bool _loading = true;
  bool _enrolled = false;
  String? _baseUrl;
  AdminSession? _session;
  final _currency = CurrencyModel();

  @override
  void initState() {
    super.initState();
    _checkState();
  }

  Future<void> _checkState() async {
    final enrolled = await SessionStore.isEnrolled();
    final baseUrl = await SessionStore.getBaseUrl();
    final session = await SessionStore.load();
    if (session != null) {
      unawaited(_currency.load(AdminApi(session.baseUrl, session.token)));
    }
    if (mounted) {
      setState(() {
        _enrolled = enrolled;
        _baseUrl = baseUrl;
        _session = session;
        _loading = false;
      });
    }
    // Fire OTA update check. Prefer the operator token (long-lived) so device
    // token expiry (24h) doesn't silently kill the update prompt.
    if (enrolled && baseUrl != null) {
      final operatorToken = session?.token;
      final deviceToken = await SessionStore.getDeviceToken();
      final token = operatorToken ?? deviceToken;
      if (token != null) {
        unawaited(_checkForUpdate(baseUrl, token, useAdminEndpoint: operatorToken != null));
      }
    }
  }

  Future<void> _checkForUpdate(String baseUrl, String token, {bool useAdminEndpoint = false}) async {
    await Future<void>.delayed(const Duration(seconds: 2));
    final update = await UpdateService.checkForUpdate(
      baseUrl: baseUrl,
      accessToken: token,
      appName: 'admin_mobile',
      useAdminEndpoint: useAdminEndpoint,
    );
    if (update == null || !mounted) return;
    await UpdateService.startBackgroundDownload(
      info: update,
      accessToken: token,
      context: mounted ? context : null,
    );
  }

  void _onEnrolled() {
    _checkState();
  }

  Future<void> _onLogin() async {
    final session = await SessionStore.load();
    if (session != null) {
      unawaited(_currency.load(AdminApi(session.baseUrl, session.token)));
    }
    if (mounted) setState(() => _session = session);
  }

  void _onLogout() async {
    await SessionStore.clearLogin();
    _currency.reset();
    if (mounted) setState(() => _session = null);
  }

  void _onResetDevice() async {
    await SessionStore.clearEnrollment();
    if (mounted) {
      setState(() {
        _enrolled = false;
        _baseUrl = null;
        _session = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    // State 1: Not enrolled → show QR scanner
    if (!_enrolled || _baseUrl == null) {
      return EnrollmentScreen(onSuccess: _onEnrolled);
    }

    // State 2: Enrolled but not logged in → show login
    if (_session == null) {
      return LoginScreen(
        baseUrl: _baseUrl!,
        onSuccess: _onLogin,
        onResetDevice: _onResetDevice,
      );
    }

    // State 3: Logged in → show app
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppShellModel()),
        ChangeNotifierProvider.value(value: _currency),
      ],
      child: AppShell(session: _session!, onLogout: _onLogout),
    );
  }
}
