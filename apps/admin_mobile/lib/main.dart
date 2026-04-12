import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'models/session.dart';
import 'screens/app_shell.dart';
import 'screens/login_screen.dart';
import 'services/session_store.dart';
import 'theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
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

class _StartupGate extends StatefulWidget {
  const _StartupGate();

  @override
  State<_StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<_StartupGate> {
  bool _loading = true;
  AdminSession? _session;

  @override
  void initState() {
    super.initState();
    _checkSession();
  }

  Future<void> _checkSession() async {
    final session = await SessionStore.load();
    if (mounted) {
      setState(() {
        _session = session;
        _loading = false;
      });
    }
  }

  Future<void> _onLogin() async {
    final session = await SessionStore.load();
    if (mounted) setState(() => _session = session);
  }

  void _onLogout() {
    setState(() => _session = null);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (_session == null) {
      return LoginScreen(onSuccess: _onLogin);
    }
    return ChangeNotifierProvider(
      create: (_) => AppShellModel(),
      child: AppShell(session: _session!, onLogout: _onLogout),
    );
  }
}
