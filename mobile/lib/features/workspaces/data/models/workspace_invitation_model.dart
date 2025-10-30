import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:hive/hive.dart';

part 'workspace_invitation_model.g.dart';

/// Invitation status enum matching backend
enum InvitationStatus {
  @JsonValue('pending')
  pending,
  @JsonValue('accepted')
  accepted,
  @JsonValue('declined')
  declined,
  @JsonValue('expired')
  expired;

  /// Get status display name
  String get displayName {
    switch (this) {
      case InvitationStatus.pending:
        return 'Pending';
      case InvitationStatus.accepted:
        return 'Accepted';
      case InvitationStatus.declined:
        return 'Declined';
      case InvitationStatus.expired:
        return 'Expired';
    }
  }

  /// Check if status is actionable
  bool get isActionable => this == InvitationStatus.pending;

  /// Parse from string
  static InvitationStatus fromString(String status) {
    switch (status.toLowerCase()) {
      case 'pending':
        return InvitationStatus.pending;
      case 'accepted':
        return InvitationStatus.accepted;
      case 'declined':
        return InvitationStatus.declined;
      case 'expired':
        return InvitationStatus.expired;
      default:
        return InvitationStatus.expired;
    }
  }
}

@JsonSerializable()
@HiveType(typeId: 4)
class WorkspaceInvitationModel extends HiveObject {
  @HiveField(0)
  final String id;
  
  @HiveField(1)
  @JsonKey(name: 'workspace_id')
  final String workspaceId;
  
  @HiveField(2)
  @JsonKey(name: 'inviter_id')
  final String inviterId;
  
  @HiveField(3)
  @JsonKey(name: 'invitee_email')
  final String inviteeEmail;
  
  @HiveField(4)
  final String role;
  
  @HiveField(5)
  final String status;
  
  @HiveField(6)
  final String token;
  
  @HiveField(7)
  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  
  @HiveField(8)
  @JsonKey(name: 'expires_at')
  final DateTime expiresAt;
  
  @HiveField(9)
  @JsonKey(name: 'is_expired')
  final bool isExpired;
  
  @HiveField(10)
  @JsonKey(name: 'workspace_name')
  final String? workspaceName;
  
  @HiveField(11)
  @JsonKey(name: 'inviter_name')
  final String? inviterName;

  const WorkspaceInvitationModel({
    required this.id,
    required this.workspaceId,
    required this.inviterId,
    required this.inviteeEmail,
    required this.role,
    required this.status,
    required this.token,
    required this.createdAt,
    required this.expiresAt,
    this.isExpired = false,
    this.workspaceName,
    this.inviterName,
  });

  /// Create from JSON
  factory WorkspaceInvitationModel.fromJson(Map<String, dynamic> json) =>
      _$WorkspaceInvitationModelFromJson(json);

  /// Convert to JSON
  Map<String, dynamic> toJson() => _$WorkspaceInvitationModelToJson(this);

  /// Get invitation status enum
  InvitationStatus get invitationStatus => InvitationStatus.fromString(status);

  /// Check if invitation is pending
  bool get isPending => invitationStatus == InvitationStatus.pending;

  /// Check if invitation is accepted
  bool get isAccepted => invitationStatus == InvitationStatus.accepted;

  /// Check if invitation can be accepted
  bool get canAccept => isPending && !isExpired;

  /// Get time until expiration
  Duration get timeUntilExpiration => expiresAt.difference(DateTime.now());

  /// Check if expiring soon (within 24 hours)
  bool get isExpiringSoon {
    if (isExpired) return false;
    return timeUntilExpiration.inHours < 24;
  }

  /// Get formatted expiration text
  String get expirationText {
    if (isExpired) return 'Expired';
    
    final duration = timeUntilExpiration;
    if (duration.inDays > 0) {
      return 'Expires in ${duration.inDays} day${duration.inDays > 1 ? 's' : ''}';
    } else if (duration.inHours > 0) {
      return 'Expires in ${duration.inHours} hour${duration.inHours > 1 ? 's' : ''}';
    } else {
      return 'Expires soon';
    }
  }

  /// Create a copy with updated fields
  WorkspaceInvitationModel copyWith({
    String? id,
    String? workspaceId,
    String? inviterId,
    String? inviteeEmail,
    String? role,
    String? status,
    String? token,
    DateTime? createdAt,
    DateTime? expiresAt,
    bool? isExpired,
    String? workspaceName,
    String? inviterName,
  }) {
    return WorkspaceInvitationModel(
      id: id ?? this.id,
      workspaceId: workspaceId ?? this.workspaceId,
      inviterId: inviterId ?? this.inviterId,
      inviteeEmail: inviteeEmail ?? this.inviteeEmail,
      role: role ?? this.role,
      status: status ?? this.status,
      token: token ?? this.token,
      createdAt: createdAt ?? this.createdAt,
      expiresAt: expiresAt ?? this.expiresAt,
      isExpired: isExpired ?? this.isExpired,
      workspaceName: workspaceName ?? this.workspaceName,
      inviterName: inviterName ?? this.inviterName,
    );
  }

  @override
  String toString() {
    return 'WorkspaceInvitationModel(id: $id, email: $inviteeEmail, status: $status, workspace: $workspaceName)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is WorkspaceInvitationModel &&
        other.id == id &&
        other.workspaceId == workspaceId &&
        other.inviterId == inviterId &&
        other.inviteeEmail == inviteeEmail &&
        other.role == role &&
        other.status == status &&
        other.token == token &&
        other.createdAt == createdAt &&
        other.expiresAt == expiresAt &&
        other.isExpired == isExpired &&
        other.workspaceName == workspaceName &&
        other.inviterName == inviterName;
  }

  @override
  int get hashCode {
    return Object.hash(
      id,
      workspaceId,
      inviterId,
      inviteeEmail,
      role,
      status,
      token,
      createdAt,
      expiresAt,
      isExpired,
      workspaceName,
      inviterName,
    );
  }
}
