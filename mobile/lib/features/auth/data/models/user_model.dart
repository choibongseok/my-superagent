import 'package:freezed_annotation/freezed_annotation.dart';

part 'user_model.g.dart';

@JsonSerializable()
class UserModel {
  final String id;
  final String email;
  final String name;
  final String? avatarUrl;
  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  final bool isGuest;

  const UserModel({
    required this.id,
    required this.email,
    required this.name,
    this.avatarUrl,
    required this.createdAt,
    this.isGuest = false,
  });

  /// Create from JSON
  factory UserModel.fromJson(Map<String, dynamic> json) => _$UserModelFromJson(json);

  /// Convert to JSON
  Map<String, dynamic> toJson() => _$UserModelToJson(this);

  /// Create a copy with updated fields
  UserModel copyWith({
    String? id,
    String? email,
    String? name,
    String? avatarUrl,
    DateTime? createdAt,
    bool? isGuest,
  }) {
    return UserModel(
      id: id ?? this.id,
      email: email ?? this.email,
      name: name ?? this.name,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      createdAt: createdAt ?? this.createdAt,
      isGuest: isGuest ?? this.isGuest,
    );
  }

  /// Guest user factory
  factory UserModel.guest() {
    return UserModel(
      id: 'guest_${DateTime.now().millisecondsSinceEpoch}',
      email: 'guest@agenthq.local',
      name: 'Guest',
      createdAt: DateTime.now(),
      isGuest: true,
    );
  }

  @override
  String toString() {
    return 'UserModel(id: $id, email: $email, name: $name, isGuest: $isGuest)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is UserModel &&
        other.id == id &&
        other.email == email &&
        other.name == name &&
        other.avatarUrl == avatarUrl &&
        other.createdAt == createdAt &&
        other.isGuest == isGuest;
  }

  @override
  int get hashCode {
    return Object.hash(
      id,
      email,
      name,
      avatarUrl,
      createdAt,
      isGuest,
    );
  }
}
