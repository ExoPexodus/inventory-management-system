import 'package:shared_preferences/shared_preferences.dart';

class EmployeeSession {
  const EmployeeSession({
    required this.employeeId,
    required this.name,
    required this.email,
    required this.position,
    required this.credentialType,
  });

  final String employeeId;
  final String name;
  final String email;
  final String position;
  final String credentialType;
}

/// Employee-scoped identity data. Clearing this store signs the current
/// employee out while preserving device enrollment (base URL, tokens).
class EmployeeSessionStore {
  const EmployeeSessionStore._();

  static const _employeeId = 'ims_employee_id';
  static const _employeeName = 'ims_employee_name';
  static const _employeeEmail = 'ims_employee_email';
  static const _employeePosition = 'ims_employee_position';
  static const _employeeCredentialType = 'ims_employee_credential_type';
  static const _pendingEmployeeId = 'ims_pending_employee_id';

  static Future<void> save({
    required String employeeId,
    required String name,
    required String email,
    required String position,
    required String credentialType,
  }) async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_employeeId, employeeId);
    await p.setString(_employeeName, name);
    await p.setString(_employeeEmail, email);
    await p.setString(_employeePosition, position);
    await p.setString(_employeeCredentialType, credentialType);
    // The employee has now signed in — remove the enrollment pending marker.
    await p.remove(_pendingEmployeeId);
  }

  static Future<EmployeeSession?> load() async {
    final p = await SharedPreferences.getInstance();
    final id = p.getString(_employeeId);
    if (id == null || id.isEmpty) return null;
    return EmployeeSession(
      employeeId: id,
      name: p.getString(_employeeName) ?? '',
      email: p.getString(_employeeEmail) ?? '',
      position: p.getString(_employeePosition) ?? '',
      credentialType: p.getString(_employeeCredentialType) ?? '',
    );
  }

  static Future<void> clear() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_employeeId);
    await p.remove(_employeeName);
    await p.remove(_employeeEmail);
    await p.remove(_employeePosition);
    await p.remove(_employeeCredentialType);
  }
}
