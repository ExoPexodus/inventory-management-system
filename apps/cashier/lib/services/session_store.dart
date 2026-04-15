import 'activity_store.dart';
import 'device_session_store.dart';
import 'employee_session_store.dart';
import 'policy_store.dart';

export 'activity_store.dart';
export 'device_session_store.dart' show DeviceSessionStore;
export 'employee_session_store.dart' show EmployeeSessionStore;
export 'policy_store.dart';

/// Merged view of the device + employee sessions. Retained as a shared value
/// object so API call sites can read enrollment + employee identity in one
/// fetch. For single-concern reads, prefer the focused stores directly.
class SessionData {
  const SessionData({
    required this.baseUrl,
    required this.accessToken,
    required this.refreshToken,
    required this.tenantId,
    required this.shopIds,
    this.pendingEmployeeId,
    this.pendingEmployeeName,
    this.pendingEmployeeCredentialType,
    this.employeeId,
    this.employeeName,
    this.employeeEmail,
    this.employeePosition,
    this.employeeCredentialType,
  });

  final String baseUrl;
  final String accessToken;
  final String refreshToken;
  final String tenantId;
  final List<String> shopIds;
  final String? pendingEmployeeId;
  final String? pendingEmployeeName;
  final String? pendingEmployeeCredentialType;
  final String? employeeId;
  final String? employeeName;
  final String? employeeEmail;
  final String? employeePosition;
  final String? employeeCredentialType;

  String get defaultShopId => shopIds.isNotEmpty ? shopIds.first : '';
  bool get hasEmployeeSession => employeeId != null && employeeId!.isNotEmpty;
}

/// Facade over the four focused stores (device, employee, policy, activity).
/// New code should prefer importing the focused store directly; this class is
/// retained so existing call sites continue to compile.
class SessionStore {
  const SessionStore._();

  // ── Device ────────────────────────────────────────────────────────────────

  static Future<void> save({
    required String baseUrl,
    required String accessToken,
    required String refreshToken,
    required String tenantId,
    required List<String> shopIds,
    String? pendingEmployeeId,
    String? pendingEmployeeName,
    String? pendingEmployeeCredentialType,
  }) {
    return DeviceSessionStore.save(
      baseUrl: baseUrl,
      accessToken: accessToken,
      refreshToken: refreshToken,
      tenantId: tenantId,
      shopIds: shopIds,
      pendingEmployeeId: pendingEmployeeId,
      pendingEmployeeName: pendingEmployeeName,
      pendingEmployeeCredentialType: pendingEmployeeCredentialType,
    );
  }

  static Future<SessionData?> load() async {
    final device = await DeviceSessionStore.load();
    if (device == null) return null;
    final employee = await EmployeeSessionStore.load();
    return SessionData(
      baseUrl: device.baseUrl,
      accessToken: device.accessToken,
      refreshToken: device.refreshToken,
      tenantId: device.tenantId,
      shopIds: device.shopIds,
      pendingEmployeeId: device.pendingEmployeeId,
      pendingEmployeeName: device.pendingEmployeeName,
      pendingEmployeeCredentialType: device.pendingEmployeeCredentialType,
      employeeId: employee?.employeeId,
      employeeName: employee?.name,
      employeeEmail: employee?.email,
      employeePosition: employee?.position,
      employeeCredentialType: employee?.credentialType,
    );
  }

  // ── Employee ──────────────────────────────────────────────────────────────

  static Future<void> saveEmployeeSession({
    required String employeeId,
    required String name,
    required String email,
    required String position,
    required String credentialType,
  }) async {
    await EmployeeSessionStore.save(
      employeeId: employeeId,
      name: name,
      email: email,
      position: position,
      credentialType: credentialType,
    );
    // Seed activity so the fresh session doesn't instantly appear timed-out.
    await ActivityStore.saveLastActivityNow();
  }

  /// Signs the employee out while keeping device enrollment intact.
  static Future<void> clearEmployeeSession() async {
    await EmployeeSessionStore.clear();
    await ActivityStore.clearLastActivity();
  }

  // ── Full wipe ─────────────────────────────────────────────────────────────

  /// Wipes every store. Forces full re-enrollment on next launch.
  static Future<void> clear() {
    return Future.wait([
      DeviceSessionStore.clear(),
      EmployeeSessionStore.clear(),
      PolicyStore.clear(),
      ActivityStore.clear(),
    ]);
  }

  // ── Activity / Policy delegation (kept for existing callers) ──────────────

  static Future<void> setLastSyncNow() => ActivityStore.setLastSyncNow();
  static Future<String?> getLastSyncIso() => ActivityStore.getLastSyncIso();
  static Future<void> saveLastActivityNow() => ActivityStore.saveLastActivityNow();
  static Future<String?> getLastActivityAt() => ActivityStore.getLastActivityAt();
  static Future<bool> isEmployeeSessionTimedOut() => ActivityStore.isEmployeeSessionTimedOut();

  static Future<void> saveMaxOfflineMinutes(int minutes) =>
      PolicyStore.saveMaxOfflineMinutes(minutes);
  static Future<int> getMaxOfflineMinutes() => PolicyStore.getMaxOfflineMinutes();
  static Future<void> saveSessionTimeoutMinutes(int minutes) =>
      PolicyStore.saveSessionTimeoutMinutes(minutes);
  static Future<int> getSessionTimeoutMinutes() => PolicyStore.getSessionTimeoutMinutes();

  static Future<void> setCurrency({
    required String code,
    required int exponent,
    String? symbolOverride,
  }) =>
      PolicyStore.setCurrency(code: code, exponent: exponent, symbolOverride: symbolOverride);
  static Future<String> getCurrencyCode() => PolicyStore.getCurrencyCode();
  static Future<int> getCurrencyExponent() => PolicyStore.getCurrencyExponent();
  static Future<String?> getCurrencySymbolOverride() => PolicyStore.getCurrencySymbolOverride();
}
