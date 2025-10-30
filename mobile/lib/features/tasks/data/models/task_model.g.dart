// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'task_model.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

TaskModel _$TaskModelFromJson(Map<String, dynamic> json) => TaskModel(
      id: json['id'] as String,
      userId: json['user_id'] as String,
      prompt: json['prompt'] as String,
      taskType: json['task_type'] as String,
      status: json['status'] as String,
      result: json['result'] as Map<String, dynamic>?,
      errorMessage: json['error_message'] as String?,
      documentUrl: json['document_url'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String),
      completedAt: json['completed_at'] == null
          ? null
          : DateTime.parse(json['completed_at'] as String),
    );

Map<String, dynamic> _$TaskModelToJson(TaskModel instance) => <String, dynamic>{
      'id': instance.id,
      'user_id': instance.userId,
      'prompt': instance.prompt,
      'task_type': instance.taskType,
      'status': instance.status,
      'result': instance.result,
      'error_message': instance.errorMessage,
      'document_url': instance.documentUrl,
      'created_at': instance.createdAt.toIso8601String(),
      'completed_at': instance.completedAt?.toIso8601String(),
    };
