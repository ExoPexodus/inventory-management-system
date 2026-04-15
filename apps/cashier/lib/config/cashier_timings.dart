class CashierTimings {
  const CashierTimings._();

  static const outboxFlushInterval = Duration(seconds: 30);
  static const inactivityCheckInterval = Duration(seconds: 60);
  static const offlineCheckInterval = Duration(seconds: 30);

  static const defaultOfflineLimitMinutes = 60;
  static const defaultSessionTimeoutMinutes = 30;
}
