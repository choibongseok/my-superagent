import 'package:freezed_annotation/freezed_annotation.dart';

part 'task_model.g.dart';

@JsonSerializable()
class TaskModel {
  final String id;
  @JsonKey(name: 'user_id')
  final String userId;
  final String prompt;
  @JsonKey(name: 'task_type')
  final String taskType;
  final String status;
  final Map<String, dynamic>? result;
  @JsonKey(name: 'error_message')
  final String? errorMessage;
  @JsonKey(name: 'document_url')
  final String? documentUrl;
  @JsonKey(name: 'created_at')
  final DateTime createdAt;
  @JsonKey(name: 'completed_at')
  final DateTime? completedAt;

  const TaskModel({
    required this.id,
    required this.userId,
    required this.prompt,
    required this.taskType,
    required this.status,
    this.result,
    this.errorMessage,
    this.documentUrl,
    required this.createdAt,
    this.completedAt,
  });

  /// Create from JSON
  factory TaskModel.fromJson(Map<String, dynamic> json) => _$TaskModelFromJson(json);

  /// Convert to JSON
  Map<String, dynamic> toJson() => _$TaskModelToJson(this);

  /// Create a copy with updated fields
  TaskModel copyWith({
    String? id,
    String? userId,
    String? prompt,
    String? taskType,
    String? status,
    Map<String, dynamic>? result,
    String? errorMessage,
    String? documentUrl,
    DateTime? createdAt,
    DateTime? completedAt,
  }) {
    return TaskModel(
      id: id ?? this.id,
      userId: userId ?? this.userId,
      prompt: prompt ?? this.prompt,
      taskType: taskType ?? this.taskType,
      status: status ?? this.status,
      result: result ?? this.result,
      errorMessage: errorMessage ?? this.errorMessage,
      documentUrl: documentUrl ?? this.documentUrl,
      createdAt: createdAt ?? this.createdAt,
      completedAt: completedAt ?? this.completedAt,
    );
  }

  /// Check if task is completed (success or failed)
  bool get isCompleted => status == 'completed' || status == 'failed';

  /// Check if task is in progress
  bool get isInProgress => status == 'in_progress';

  /// Check if task is pending
  bool get isPending => status == 'pending';

  /// Check if task failed
  bool get isFailed => status == 'failed';

  /// Get status display text
  String get statusDisplayText {
    switch (status) {
      case 'pending':
        return '대기 중';
      case 'in_progress':
        return '진행 중';
      case 'completed':
        return '완료';
      case 'failed':
        return '실패';
      default:
        return status;
    }
  }

  /// Get task type display text
  String get taskTypeDisplayText {
    switch (taskType) {
      case 'research':
        return '리서치';
      case 'document':
        return '문서 작성';
      case 'code':
        return '코드 생성';
      case 'analysis':
        return '분석';
      case 'translation':
        return '번역';
      default:
        return taskType;
    }
  }

  @override
  String toString() {
    return 'TaskModel(id: $id, prompt: $prompt, status: $status, taskType: $taskType)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is TaskModel &&
        other.id == id &&
        other.userId == userId &&
        other.prompt == prompt &&
        other.taskType == taskType &&
        other.status == status &&
        other.errorMessage == errorMessage &&
        other.documentUrl == documentUrl &&
        other.createdAt == createdAt &&
        other.completedAt == completedAt;
  }

  @override
  int get hashCode {
    return Object.hash(
      id,
      userId,
      prompt,
      taskType,
      status,
      errorMessage,
      documentUrl,
      createdAt,
      completedAt,
    );
  }
}
