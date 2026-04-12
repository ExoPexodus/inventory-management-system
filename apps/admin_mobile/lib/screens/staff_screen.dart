import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../admin_tokens.dart';
import '../models/employee.dart';
import '../services/admin_api.dart';
import '../services/session_store.dart';
import '../widgets/staff_card.dart';
import 'app_shell.dart';

const _positions = ['All', 'Manager', 'Cashier', 'Curator', 'Specialist'];

class StaffScreen extends StatefulWidget {
  const StaffScreen({super.key, required this.onLogout});

  final VoidCallback onLogout;

  @override
  State<StaffScreen> createState() => _StaffScreenState();
}

class _StaffScreenState extends State<StaffScreen> {
  bool _loading = true;
  String? _error;
  List<Employee> _employees = [];
  bool _showInactive = false;
  String _filterPosition = 'All';
  AdminApi? _api;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final session = await SessionStore.load();
      if (session == null) { widget.onLogout(); return; }
      _api = AdminApi(session.baseUrl, session.token);
      final list = await _api!.getEmployees(includeInactive: _showInactive);
      if (!mounted) return;
      setState(() { _employees = list; _loading = false; });
    } on ApiException catch (e) {
      if (e.statusCode == 401) { await SessionStore.clear(); if (mounted) widget.onLogout(); return; }
      if (mounted) setState(() { _error = 'Failed to load (${e.statusCode})'; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = 'Connection error'; _loading = false; });
    }
  }

  List<Employee> get _filtered {
    return _employees.where((e) {
      if (_filterPosition != 'All' && !e.position.toLowerCase().contains(_filterPosition.toLowerCase())) {
        return false;
      }
      return true;
    }).toList();
  }

  Future<void> _deactivate(Employee emp) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Deactivate employee'),
        content: Text('Deactivate ${emp.name}? They will no longer be able to sign in.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(
              backgroundColor: AdminColors.error,
              minimumSize: const Size(0, 44),
            ),
            child: const Text('Deactivate'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _api!.deactivateEmployee(emp.id);
      _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed (${e.statusCode})')),
      );
    }
  }

  Future<void> _reactivate(Employee emp) async {
    try {
      await _api!.reactivateEmployee(emp.id);
      _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed (${e.statusCode})')),
      );
    }
  }

  Future<void> _reEnroll(Employee emp) async {
    try {
      final data = await _api!.reEnrollEmployee(emp.id);
      final token = data['enrollment_token'] as String? ?? data['token'] as String? ?? '';
      if (!mounted) return;
      await showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text('Re-enroll ${emp.name}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Scan this QR code on the cashier device to re-enroll.'),
              const SizedBox(height: 16),
              if (token.isNotEmpty)
                QrImageView(data: token, size: 200)
              else
                const Text('No enrollment token received.'),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done')),
          ],
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to re-enroll (${e.statusCode})')),
      );
    }
  }

  Future<void> _resetCredentials(Employee emp) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reset credentials'),
        content: Text('Reset PIN/password for ${emp.name}? They will need to set new credentials on next login.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Reset')),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _api!.resetEmployeeCredentials(emp.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Credentials reset for ${emp.name}')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed (${e.statusCode})')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final filtered = _filtered;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Staff'),
        actions: [
          IconButton(
            onPressed: () => showLogoutDialog(context, widget.onLogout),
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Sign out',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          slivers: [
            // Filter row
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(
                AdminSpacing.gutter, AdminSpacing.md, AdminSpacing.gutter, 0,
              ),
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      height: 36,
                      child: ListView(
                        scrollDirection: Axis.horizontal,
                        children: _positions.map((pos) {
                          final selected = _filterPosition == pos;
                          return Padding(
                            padding: const EdgeInsets.only(right: AdminSpacing.xs),
                            child: FilterChip(
                              label: Text(pos),
                              selected: selected,
                              onSelected: (_) => setState(() => _filterPosition = pos),
                              selectedColor: AdminColors.primary.withValues(alpha: 0.14),
                              labelStyle: theme.textTheme.labelMedium?.copyWith(
                                color: selected ? AdminColors.primary : AdminColors.onSurfaceVariant,
                                fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                    ),
                    const SizedBox(height: AdminSpacing.sm),
                    Row(
                      children: [
                        Text(
                          'Show inactive',
                          style: theme.textTheme.bodySmall?.copyWith(color: AdminColors.onSurfaceVariant),
                        ),
                        const SizedBox(width: AdminSpacing.xs),
                        Switch.adaptive(
                          value: _showInactive,
                          onChanged: (v) {
                            setState(() => _showInactive = v);
                            _load();
                          },
                          activeColor: AdminColors.primary,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),

            if (_loading)
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.all(48),
                  child: Center(child: CircularProgressIndicator()),
                ),
              )
            else if (_error != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(AdminSpacing.gutter),
                  child: Column(
                    children: [
                      const SizedBox(height: 24),
                      Icon(Icons.cloud_off_rounded, size: 48, color: AdminColors.onSurfaceVariant),
                      const SizedBox(height: 12),
                      Text(_error!, textAlign: TextAlign.center),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        onPressed: _load,
                        icon: const Icon(Icons.refresh_rounded),
                        label: const Text('Retry'),
                      ),
                    ],
                  ),
                ),
              )
            else if (filtered.isEmpty)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(AdminSpacing.gutter),
                  child: Column(
                    children: [
                      const SizedBox(height: 48),
                      Icon(Icons.people_outline_rounded, size: 48, color: AdminColors.onSurfaceVariant),
                      const SizedBox(height: 12),
                      Text(
                        'No employees found',
                        style: theme.textTheme.bodyMedium?.copyWith(color: AdminColors.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(
                  AdminSpacing.gutter, AdminSpacing.md, AdminSpacing.gutter, 100,
                ),
                sliver: SliverList.separated(
                  itemCount: filtered.length,
                  separatorBuilder: (_, __) => const SizedBox(height: AdminSpacing.sm),
                  itemBuilder: (_, i) {
                    final emp = filtered[i];
                    return StaffCard(
                      employee: emp,
                      onDeactivate: () => _deactivate(emp),
                      onReactivate: () => _reactivate(emp),
                      onReEnroll: () => _reEnroll(emp),
                      onResetCredentials: () => _resetCredentials(emp),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

