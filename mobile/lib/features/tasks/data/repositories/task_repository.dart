import '../../../../core/network/api_client.dart';
import '../models/task_model.dart';

/// Repository for task operations
class TaskRepository {
  final ApiClient _apiClient;

  TaskRepository(this._apiClient);

  /// Get all tasks for current user
  Future<List<TaskModel>> getTasks({
    int? limit,
    int? offset,
    String? status,
  }) async {
    try {
      final queryParams = <String, dynamic>{};
      if (limit != null) queryParams['limit'] = limit;
      if (offset != null) queryParams['offset'] = offset;
      if (status != null) queryParams['status'] = status;

      final response = await _apiClient.get(
        '/tasks',
        queryParameters: queryParams,
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = response.data as List<dynamic>;
        return data
            .map((json) => TaskModel.fromJson(json as Map<String, dynamic>))
            .toList();
      }

      throw Exception('Failed to get tasks: ${response.statusCode}');
    } catch (e) {
      print('Get tasks error: $e');
      rethrow;
    }
  }

  /// Create a new task
  Future<TaskModel> createTask({
    required String prompt,
    required String taskType,
  }) async {
    try {
      final response = await _apiClient.post(
        '/tasks',
        data: {
          'prompt': prompt,
          'output_type': taskType,
        },
      );

      if (response.statusCode == 200 || response.statusCode == 201) {
        return TaskModel.fromJson(response.data as Map<String, dynamic>);
      }

      throw Exception('Failed to create task: ${response.statusCode}');
    } catch (e) {
      print('Create task error: $e');
      rethrow;
    }
  }

  /// Get task by ID
  Future<TaskModel?> getTaskById(String taskId) async {
    try {
      final response = await _apiClient.get('/tasks/$taskId');

      if (response.statusCode == 200) {
        return TaskModel.fromJson(response.data as Map<String, dynamic>);
      }

      if (response.statusCode == 404) {
        return null;
      }

      throw Exception('Failed to get task: ${response.statusCode}');
    } catch (e) {
      print('Get task error: $e');
      rethrow;
    }
  }

  /// Get task result
  Future<Map<String, dynamic>?> getTaskResult(String taskId) async {
    try {
      final response = await _apiClient.get('/tasks/$taskId/result');

      if (response.statusCode == 200) {
        return response.data as Map<String, dynamic>;
      }

      if (response.statusCode == 404) {
        return null;
      }

      throw Exception('Failed to get task result: ${response.statusCode}');
    } catch (e) {
      print('Get task result error: $e');
      rethrow;
    }
  }

  /// Cancel a task
  Future<bool> cancelTask(String taskId) async {
    try {
      final response = await _apiClient.delete('/tasks/$taskId');

      return response.statusCode == 200 || response.statusCode == 204;
    } catch (e) {
      print('Cancel task error: $e');
      return false;
    }
  }

  /// Poll task status until completed or failed
  Future<TaskModel> pollTaskStatus(
    String taskId, {
    Duration interval = const Duration(seconds: 2),
    Duration timeout = const Duration(minutes: 5),
  }) async {
    final startTime = DateTime.now();

    while (true) {
      // Check timeout
      if (DateTime.now().difference(startTime) > timeout) {
        throw Exception('Task polling timeout');
      }

      // Get current task status
      final task = await getTaskById(taskId);
      if (task == null) {
        throw Exception('Task not found');
      }

      // Check if task is complete
      if (task.status == 'completed' || task.status == 'failed') {
        return task;
      }

      // Wait before next poll
      await Future.delayed(interval);
    }
  }
}
