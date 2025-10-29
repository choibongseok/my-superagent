/// Task data model
class TaskModel {
  final String id;
  final String userId;
  final String prompt;
  final String taskType;
  final String status;
  final Map<String, dynamic>? result;
  final String? errorMessage;
  final String? documentUrl;
  final String? documentId;
  final DateTime createdAt;
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
    this.documentId,
    required this.createdAt,
    this.completedAt,
  });

  factory TaskModel.fromJson(Map<String, dynamic> json) {
    return TaskModel(
      id: json['id'] as String,
      userId: json['user_id'] as String,
      prompt: json['prompt'] as String,
      taskType: json['task_type'] as String? ?? json['output_type'] as String? ?? 'research',
      status: json['status'] as String,
      result: json['result'] as Map<String, dynamic>?,
      errorMessage: json['error_message'] as String?,
      documentUrl: json['document_url'] as String?,
      documentId: json['document_id'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      completedAt: json['completed_at'] != null
          ? DateTime.parse(json['completed_at'] as String)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'user_id': userId,
      'prompt': prompt,
      'task_type': taskType,
      'status': status,
      'result': result,
      'error_message': errorMessage,
      'document_url': documentUrl,
      'document_id': documentId,
      'created_at': createdAt.toIso8601String(),
      'completed_at': completedAt?.toIso8601String(),
    };
  }

  TaskModel copyWith({
    String? id,
    String? userId,
    String? prompt,
    String? taskType,
    String? status,
    Map<String, dynamic>? result,
    String? errorMessage,
    String? documentUrl,
    String? documentId,
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
      documentId: documentId ?? this.documentId,
      createdAt: createdAt ?? this.createdAt,
      completedAt: completedAt ?? this.completedAt,
    );
  }

  @override
  String toString() {
    return 'TaskModel(id: $id, taskType: $taskType, status: $status)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;

    return other is TaskModel &&
        other.id == id &&
        other.userId == userId &&
        other.taskType == taskType &&
        other.status == status;
  }

  @override
  int get hashCode {
    return id.hashCode ^
        userId.hashCode ^
        taskType.hashCode ^
        status.hashCode;
  }
}
