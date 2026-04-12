class Employee {
  const Employee({
    required this.id,
    required this.name,
    required this.email,
    required this.position,
    required this.isActive,
    this.phone,
    this.credentialType,
  });

  final String id;
  final String name;
  final String email;
  final String position;
  final bool isActive;
  final String? phone;
  final String? credentialType;

  String get initials {
    final parts = name.trim().split(' ').where((w) => w.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts[0][0].toUpperCase();
    return '${parts[0][0]}${parts[parts.length - 1][0]}'.toUpperCase();
  }

  factory Employee.fromJson(Map<String, dynamic> j) => Employee(
        id: j['id'] as String,
        name: j['name'] as String? ?? '',
        email: j['email'] as String? ?? '',
        position: j['position'] as String? ?? '',
        isActive: j['is_active'] as bool? ?? true,
        phone: j['phone'] as String?,
        credentialType: j['credential_type'] as String?,
      );
}
