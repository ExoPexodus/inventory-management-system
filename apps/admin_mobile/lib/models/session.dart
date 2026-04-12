class AdminSession {
  const AdminSession({
    required this.token,
    required this.email,
    required this.baseUrl,
    this.role,
    this.permissions = const [],
  });

  final String token;
  final String email;
  final String baseUrl;
  final String? role;
  final List<String> permissions;

  bool hasPermission(String codename) => permissions.contains(codename);
}
