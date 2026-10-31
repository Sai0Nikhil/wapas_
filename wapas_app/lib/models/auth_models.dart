enum UserRole {
  owner,
  staff;

  static UserRole fromString(String? role) {
    if (role != null && role.toUpperCase() == 'OWNER') {
      return UserRole.owner;
    }
    return UserRole.staff;
  }

  String toApiString() => this == UserRole.owner ? 'OWNER' : 'STAFF';
  bool get isOwner => this == UserRole.owner;
}

class StoreMembership {
  final String id;
  final String storeId;
  final String storeName;
  final String storeSlug;
  final UserRole role;
  final bool isActive;

  StoreMembership({
    required this.id,
    required this.storeId,
    required this.storeName,
    required this.storeSlug,
    required this.role,
    required this.isActive,
  });

  factory StoreMembership.fromJson(Map<String, dynamic> json) {
    return StoreMembership(
      id: (json['id'] ?? '').toString(),
      storeId: (json['store_id'] ?? '').toString(),
      storeName: (json['store_name'] ?? '').toString(),
      storeSlug: (json['store_slug'] ?? '').toString(),
      role: UserRole.fromString(json['role']?.toString()),
      isActive: json['is_active'] == true,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'store_id': storeId,
    'store_name': storeName,
    'store_slug': storeSlug,
    'role': role.toApiString(),
    'is_active': isActive,
  };
}

class AuthSession {
  final bool authenticated;
  final String? userId;
  final String? username;
  final String? membershipId;
  final UserRole role;
  final String? merchantId;
  final String? storeId;
  final String? storeSlug;
  final String? merchantName;
  final String? storeName;
  final String? csrfToken;
  final DateTime? expiresAt;

  AuthSession({
    required this.authenticated,
    this.userId,
    this.username,
    this.membershipId,
    this.role = UserRole.staff,
    this.merchantId,
    this.storeId,
    this.storeSlug,
    this.merchantName,
    this.storeName,
    this.csrfToken,
    this.expiresAt,
  });

  factory AuthSession.unauthenticated() {
    return AuthSession(authenticated: false);
  }

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      authenticated: json['authenticated'] == true,
      userId: json['user_id']?.toString(),
      username: json['username']?.toString(),
      membershipId: json['membership_id']?.toString(),
      role: UserRole.fromString(json['role']?.toString()),
      merchantId: json['merchant_id']?.toString(),
      storeId: json['store_id']?.toString(),
      storeSlug: json['store_slug']?.toString(),
      merchantName: json['merchant_name']?.toString(),
      storeName: json['store_name']?.toString(),
      csrfToken: json['csrf_token']?.toString(),
      expiresAt: json['expires_at'] != null ? DateTime.tryParse(json['expires_at'].toString()) : null,
    );
  }

  Map<String, dynamic> toJson() => {
    'authenticated': authenticated,
    'user_id': userId,
    'username': username,
    'membership_id': membershipId,
    'role': role.toApiString(),
    'merchant_id': merchantId,
    'store_id': storeId,
    'store_slug': storeSlug,
    'merchant_name': merchantName,
    'store_name': storeName,
    'csrf_token': csrfToken,
    'expires_at': expiresAt?.toIso8601String(),
  };

  AuthSession copyWith({
    bool? authenticated,
    String? userId,
    String? username,
    String? membershipId,
    UserRole? role,
    String? merchantId,
    String? storeId,
    String? storeSlug,
    String? merchantName,
    String? storeName,
    String? csrfToken,
    DateTime? expiresAt,
  }) {
    return AuthSession(
      authenticated: authenticated ?? this.authenticated,
      userId: userId ?? this.userId,
      username: username ?? this.username,
      membershipId: membershipId ?? this.membershipId,
      role: role ?? this.role,
      merchantId: merchantId ?? this.merchantId,
      storeId: storeId ?? this.storeId,
      storeSlug: storeSlug ?? this.storeSlug,
      merchantName: merchantName ?? this.merchantName,
      storeName: storeName ?? this.storeName,
      csrfToken: csrfToken ?? this.csrfToken,
      expiresAt: expiresAt ?? this.expiresAt,
    );
  }
}
