class Supplier {
  const Supplier({
    required this.id,
    required this.name,
    required this.status,
    this.contactEmail,
    this.contactPhone,
  });

  final String id;
  final String name;
  final String status; // active | inactive
  final String? contactEmail;
  final String? contactPhone;

  factory Supplier.fromJson(Map<String, dynamic> j) => Supplier(
        id: j['id'] as String,
        name: j['name'] as String? ?? '',
        status: j['status'] as String? ?? 'active',
        contactEmail: j['contact_email'] as String?,
        contactPhone: j['contact_phone'] as String?,
      );
}
