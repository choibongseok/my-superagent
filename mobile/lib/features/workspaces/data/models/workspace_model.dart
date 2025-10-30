import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:hive/hive.dart';

part 'workspace_model.g.dart';

@JsonSerializable()
@HiveType(typeId: 2)
class WorkspaceModel extends HiveObject {
  @HiveField(0)
  final String id;
  
  @HiveField(1)
  final String name;
  
  @HiveField(2)
  final String? description;
  
  @HiveField(3)
  @JsonKey(name: 'owner_id')
  final String ownerId;
  
  @HiveField(4)
  @JsonKey(name: 'is_active')
  final bool isActive;
  
  @HiveField(5)
  @JsonKey(name: 'max_members')
  final int maxMembers;
  
  @HiveField(6)
  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  
  @HiveField(7)
  @JsonKey(name: 'updated_at')
  final DateTime updatedAt;
  
  @HiveField(8)
  @JsonKey(name: 'member_count')
  final int memberCount;

  const WorkspaceModel({
    required this.id,
    required this.name,
    this.description,
    required this.ownerId,
    this.isActive = true,
    this.maxMembers = 10,
    required this.createdAt,
    required this.updatedAt,
    this.memberCount = 0,
  });

  /// Create from JSON
  factory WorkspaceModel.fromJson(Map<String, dynamic> json) => _$WorkspaceModelFromJson(json);

  /// Convert to JSON
  Map<String, dynamic> toJson() => _$WorkspaceModelToJson(this);

  /// Create a copy with updated fields
  WorkspaceModel copyWith({
    String? id,
    String? name,
    String? description,
    String? ownerId,
    bool? isActive,
    int? maxMembers,
    DateTime? createdAt,
    DateTime? updatedAt,
    int? memberCount,
  }) {
    return WorkspaceModel(
      id: id ?? this.id,
      name: name ?? this.name,
      description: description ?? this.description,
      ownerId: ownerId ?? this.ownerId,
      isActive: isActive ?? this.isActive,
      maxMembers: maxMembers ?? this.maxMembers,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      memberCount: memberCount ?? this.memberCount,
    );
  }

  /// Check if workspace is at capacity
  bool get isAtCapacity => memberCount >= maxMembers;

  /// Calculate capacity percentage
  double get capacityPercentage => 
      maxMembers > 0 ? (memberCount / maxMembers) * 100 : 0;

  @override
  String toString() {
    return 'WorkspaceModel(id: $id, name: $name, memberCount: $memberCount/$maxMembers)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is WorkspaceModel &&
        other.id == id &&
        other.name == name &&
        other.description == description &&
        other.ownerId == ownerId &&
        other.isActive == isActive &&
        other.maxMembers == maxMembers &&
        other.createdAt == createdAt &&
        other.updatedAt == updatedAt &&
        other.memberCount == memberCount;
  }

  @override
  int get hashCode {
    return Object.hash(
      id,
      name,
      description,
      ownerId,
      isActive,
      maxMembers,
      createdAt,
      updatedAt,
      memberCount,
    );
  }
}
