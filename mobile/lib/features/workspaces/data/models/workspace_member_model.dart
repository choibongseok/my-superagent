import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:hive/hive.dart';

part 'workspace_member_model.g.dart';

/// Member role enum matching backend
enum MemberRole {
  @JsonValue('owner')
  owner,
  @JsonValue('admin')
  admin,
  @JsonValue('member')
  member,
  @JsonValue('viewer')
  viewer;

  /// Get role display name
  String get displayName {
    switch (this) {
      case MemberRole.owner:
        return 'Owner';
      case MemberRole.admin:
        return 'Admin';
      case MemberRole.member:
        return 'Member';
      case MemberRole.viewer:
        return 'Viewer';
    }
  }

  /// Get role description
  String get description {
    switch (this) {
      case MemberRole.owner:
        return 'Full control of workspace';
      case MemberRole.admin:
        return 'Manage members and settings';
      case MemberRole.member:
        return 'Access workspace resources';
      case MemberRole.viewer:
        return 'View-only access';
    }
  }

  /// Get role level for comparison
  int get level {
    switch (this) {
      case MemberRole.owner:
        return 4;
      case MemberRole.admin:
        return 3;
      case MemberRole.member:
        return 2;
      case MemberRole.viewer:
        return 1;
    }
  }

  /// Check if this role has permission level of required role
  bool hasPermission(MemberRole required) {
    return level >= required.level;
  }

  /// Parse from string
  static MemberRole fromString(String role) {
    switch (role.toLowerCase()) {
      case 'owner':
        return MemberRole.owner;
      case 'admin':
        return MemberRole.admin;
      case 'member':
        return MemberRole.member;
      case 'viewer':
        return MemberRole.viewer;
      default:
        return MemberRole.viewer;
    }
  }
}

@JsonSerializable()
@HiveType(typeId: 3)
class WorkspaceMemberModel extends HiveObject {
  @HiveField(0)
  final String id;
  
  @HiveField(1)
  @JsonKey(name: 'workspace_id')
  final String workspaceId;
  
  @HiveField(2)
  @JsonKey(name: 'user_id')
  final String userId;
  
  @HiveField(3)
  final String role;
  
  @HiveField(4)
  @JsonKey(name: 'joined_at')
  final DateTime joinedAt;
  
  @HiveField(5)
  @JsonKey(name: 'updated_at')
  final DateTime updatedAt;
  
  @HiveField(6)
  @JsonKey(name: 'user_email')
  final String? userEmail;
  
  @HiveField(7)
  @JsonKey(name: 'user_name')
  final String? userName;

  const WorkspaceMemberModel({
    required this.id,
    required this.workspaceId,
    required this.userId,
    required this.role,
    required this.joinedAt,
    required this.updatedAt,
    this.userEmail,
    this.userName,
  });

  /// Create from JSON
  factory WorkspaceMemberModel.fromJson(Map<String, dynamic> json) => 
      _$WorkspaceMemberModelFromJson(json);

  /// Convert to JSON
  Map<String, dynamic> toJson() => _$WorkspaceMemberModelToJson(this);

  /// Get member role enum
  MemberRole get memberRole => MemberRole.fromString(role);

  /// Check if member has permission
  bool hasPermission(MemberRole required) {
    return memberRole.hasPermission(required);
  }

  /// Check if member is owner
  bool get isOwner => memberRole == MemberRole.owner;

  /// Check if member is admin or above
  bool get isAdmin => hasPermission(MemberRole.admin);

  /// Get display name (user name or email)
  String get displayName => userName ?? userEmail ?? 'Unknown User';

  /// Create a copy with updated fields
  WorkspaceMemberModel copyWith({
    String? id,
    String? workspaceId,
    String? userId,
    String? role,
    DateTime? joinedAt,
    DateTime? updatedAt,
    String? userEmail,
    String? userName,
  }) {
    return WorkspaceMemberModel(
      id: id ?? this.id,
      workspaceId: workspaceId ?? this.workspaceId,
      userId: userId ?? this.userId,
      role: role ?? this.role,
      joinedAt: joinedAt ?? this.joinedAt,
      updatedAt: updatedAt ?? this.updatedAt,
      userEmail: userEmail ?? this.userEmail,
      userName: userName ?? this.userName,
    );
  }

  @override
  String toString() {
    return 'WorkspaceMemberModel(id: $id, userId: $userId, role: $role, name: $displayName)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is WorkspaceMemberModel &&
        other.id == id &&
        other.workspaceId == workspaceId &&
        other.userId == userId &&
        other.role == role &&
        other.joinedAt == joinedAt &&
        other.updatedAt == updatedAt &&
        other.userEmail == userEmail &&
        other.userName == userName;
  }

  @override
  int get hashCode {
    return Object.hash(
      id,
      workspaceId,
      userId,
      role,
      joinedAt,
      updatedAt,
      userEmail,
      userName,
    );
  }
}
