import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:uuid/uuid.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/errors/app_exception.dart';
import '../../../../core/storage/storage_service.dart';
import '../../../../core/sync/sync_queue_service.dart';
import '../models/task_model.dart';

/// Repository for task operations with offline support and sync queue
class TaskRepository {
  final ApiClient _apiClient;
  final StorageService _storage;
  final SyncQueueService _syncQueue;
  final Connectivity _connectivity;
  final _uuid = const Uuid();

  TaskRepository({
    required ApiClient apiClient,
    required StorageService storage,
    required SyncQueueService syncQueue,
    Connectivity? connectivity,
  })  : _apiClient = apiClient,
        _storage = storage,
        _syncQueue = syncQueue,
        _connectivity = connectivity ?? Connectivity();

  /// Get all tasks for current user (with offline support)
  Future<List<TaskModel>> getTasks({
    int? limit,
    int? offset,
    String? status,
    bool useCache = true,
  }) async {
    try {
      // Try to fetch from API
      final queryParams = <String, dynamic>{};
      if (limit != null) queryParams['limit'] = limit;
      if (offset != null) queryParams['offset'] = offset;
      if (status != null) queryParams['status'] = status;

      final response = await _apiClient.get(
        '/tasks',
        queryParameters: queryParams.isNotEmpty ? queryParams : null,
      );

      final data = response.data;
      List<TaskModel> tasks = [];
      
      if (data is List) {
        tasks = data.map((json) => TaskModel.fromJson(json)).toList();
      } else if (data is Map && data['tasks'] != null) {
        final tasksList = data['tasks'] as List;
        tasks = tasksList.map((json) => TaskModel.fromJson(json)).toList();
      }

      // Cache the tasks for offline use
      await _cacheTasks(tasks);

      return tasks;
    } catch (e, stackTrace) {
      // If network error and cache is enabled, try to load from cache
      if (useCache) {
        final cachedTasks = await _getCachedTasks();
        if (cachedTasks.isNotEmpty) {
          return cachedTasks;
        }
      }
      
      throw AppException(
        message: 'Failed to get tasks: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Cache tasks locally
  Future<void> _cacheTasks(List<TaskModel> tasks) async {
    try {
      await _storage.clearTasks();
      for (final task in tasks) {
        await _storage.saveTask(task.id, task.toJson());
      }
    } catch (e) {
      // Silently fail if caching fails
      print('Failed to cache tasks: $e');
    }
  }

  /// Get cached tasks
  Future<List<TaskModel>> _getCachedTasks() async {
    try {
      final cached = _storage.getAllTasks();
      return cached.map((json) => TaskModel.fromJson(json)).toList();
    } catch (e) {
      print('Failed to load cached tasks: $e');
      return [];
    }
  }

  /// Get a single task by ID
  Future<TaskModel> getTaskById(String taskId) async {
    try {
      final response = await _apiClient.get('/tasks/$taskId');
      return TaskModel.fromJson(response.data);
    } on NotFoundException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to get task: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Create a new task (with offline queue support)
  Future<TaskModel> createTask({
    required String prompt,
    required String taskType,
    Map<String, dynamic>? metadata,
  }) async {
    // Check connectivity
    final connectivityResult = await _connectivity.checkConnectivity();
    final isOnline = connectivityResult != ConnectivityResult.none;

    if (!isOnline) {
      // Create optimistic task (offline)
      final tempId = _uuid.v4();
      final optimisticTask = TaskModel(
        id: tempId,
        userId: 'offline', // Will be updated when synced
        prompt: prompt,
        taskType: taskType,
        status: 'pending',
        metadata: metadata,
        result: null,
        errorMessage: null,
        documentUrl: null,
        createdAt: DateTime.now(),
        completedAt: null,
      );

      // Cache optimistic task
      await _storage.saveTask(tempId, optimisticTask.toJson());

      // Queue action for sync
      await _syncQueue.queueAction(SyncAction(
        id: _uuid.v4(),
        type: SyncActionType.createTask,
        data: {
          'tempId': tempId,
          'prompt': prompt,
          'task_type': taskType,
          if (metadata != null) 'metadata': metadata,
        },
      ));

      return optimisticTask;
    }

    // Online - create immediately
    try {
      final response = await _apiClient.post(
        '/tasks',
        data: {
          'prompt': prompt,
          'task_type': taskType,
          if (metadata != null) 'metadata': metadata,
        },
      );

      final task = TaskModel.fromJson(response.data);
      
      // Cache the newly created task
      await _storage.saveTask(task.id, task.toJson());
      
      return task;
    } on ValidationException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to create task: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Cancel a task (with offline queue support)
  Future<void> cancelTask(String taskId) async {
    // Check connectivity
    final connectivityResult = await _connectivity.checkConnectivity();
    final isOnline = connectivityResult != ConnectivityResult.none;

    if (!isOnline) {
      // Queue action for sync
      await _syncQueue.queueAction(SyncAction(
        id: _uuid.v4(),
        type: SyncActionType.cancelTask,
        data: {'taskId': taskId},
      ));
      return;
    }

    // Online - cancel immediately
    try {
      await _apiClient.post('/tasks/$taskId/cancel');
    } on NotFoundException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to cancel task: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Delete a task (with offline queue support)
  Future<void> deleteTask(String taskId) async {
    // Check connectivity
    final connectivityResult = await _connectivity.checkConnectivity();
    final isOnline = connectivityResult != ConnectivityResult.none;

    if (!isOnline) {
      // Queue action for sync
      await _syncQueue.queueAction(SyncAction(
        id: _uuid.v4(),
        type: SyncActionType.deleteTask,
        data: {'taskId': taskId},
      ));
      
      // Delete from cache immediately
      await _storage.deleteTask(taskId);
      return;
    }

    // Online - delete immediately
    try {
      await _apiClient.delete('/tasks/$taskId');
      await _storage.deleteTask(taskId);
    } on NotFoundException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to delete task: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Poll task status until completion
  /// Returns the completed task or throws TimeoutException
  Future<TaskModel> pollTaskStatus(
    String taskId, {
    Duration interval = const Duration(seconds: 2),
    Duration timeout = const Duration(minutes: 5),
  }) async {
    final startTime = DateTime.now();
    
    while (true) {
      // Check timeout
      if (DateTime.now().difference(startTime) > timeout) {
        throw const TimeoutException(
          message: 'Task polling timeout',
        );
      }

      try {
        // Get task status
        final task = await getTaskById(taskId);

        // Check if completed (success or failed)
        if (task.isCompleted) {
          return task;
        }

        // Wait before next poll
        await Future.delayed(interval);
      } catch (e) {
        // If task not found or other error, wait and retry
        await Future.delayed(interval);
      }
    }
  }

  /// Poll task status with callback for status updates
  Future<TaskModel> pollTaskStatusWithCallback(
    String taskId, {
    Duration interval = const Duration(seconds: 2),
    Duration timeout = const Duration(minutes: 5),
    void Function(TaskModel task)? onStatusUpdate,
  }) async {
    final startTime = DateTime.now();
    String? lastStatus;

    while (true) {
      // Check timeout
      if (DateTime.now().difference(startTime) > timeout) {
        throw const TimeoutException(
          message: 'Task polling timeout',
        );
      }

      try {
        // Get task status
        final task = await getTaskById(taskId);

        // Notify if status changed
        if (task.status != lastStatus) {
          lastStatus = task.status;
          onStatusUpdate?.call(task);
        }

        // Check if completed (success or failed)
        if (task.isCompleted) {
          return task;
        }

        // Wait before next poll
        await Future.delayed(interval);
      } catch (e) {
        // If task not found or other error, wait and retry
        await Future.delayed(interval);
      }
    }
  }

  /// Stream task status updates
  Stream<TaskModel> watchTaskStatus(
    String taskId, {
    Duration interval = const Duration(seconds: 2),
    Duration? timeout,
  }) async* {
    final startTime = DateTime.now();

    while (true) {
      // Check timeout if specified
      if (timeout != null && DateTime.now().difference(startTime) > timeout) {
        throw const TimeoutException(
          message: 'Task polling timeout',
        );
      }

      try {
        // Get task status
        final task = await getTaskById(taskId);
        yield task;

        // Stop if completed
        if (task.isCompleted) {
          break;
        }

        // Wait before next poll
        await Future.delayed(interval);
      } catch (e) {
        // If error, wait and retry
        await Future.delayed(interval);
      }
    }
  }

  /// Get task statistics
  Future<Map<String, dynamic>> getTaskStatistics() async {
    try {
      final response = await _apiClient.get('/tasks/statistics');
      return response.data as Map<String, dynamic>;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to get task statistics: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Check if offline mode (has cached tasks)
  Future<bool> hasOfflineData() async {
    final cached = await _getCachedTasks();
    return cached.isNotEmpty;
  }

  /// Clear all cached tasks
  Future<void> clearCache() async {
    await _storage.clearTasks();
  }

  /// Execute queued sync action
  Future<void> executeSyncAction(SyncAction action) async {
    switch (action.type) {
      case SyncActionType.createTask:
        final data = action.data;
        final tempId = data['tempId'] as String;
        
        // Create task on server
        final response = await _apiClient.post(
          '/tasks',
          data: {
            'prompt': data['prompt'],
            'task_type': data['task_type'],
            if (data['metadata'] != null) 'metadata': data['metadata'],
          },
        );
        
        final task = TaskModel.fromJson(response.data);
        
        // Update cache: remove temp task, add real task
        await _storage.deleteTask(tempId);
        await _storage.saveTask(task.id, task.toJson());
        break;

      case SyncActionType.cancelTask:
        final taskId = action.data['taskId'] as String;
        await _apiClient.post('/tasks/$taskId/cancel');
        break;

      case SyncActionType.deleteTask:
        final taskId = action.data['taskId'] as String;
        await _apiClient.delete('/tasks/$taskId');
        break;

      case SyncActionType.updateTask:
        final taskId = action.data['taskId'] as String;
        final updates = action.data['updates'] as Map<String, dynamic>;
        await _apiClient.put('/tasks/$taskId', data: updates);
        break;
    }
  }

  /// Sync all queued actions
  Future<SyncResult> syncQueuedActions() async {
    final result = await _syncQueue.syncPendingActions();
    
    // Execute each action from the queue
    final actions = await _syncQueue.getPendingActions();
    for (final action in actions) {
      try {
        await executeSyncAction(action);
      } catch (e) {
        // Error will be handled by sync queue service
        print('Failed to execute sync action: $e');
      }
    }
    
    return result;
  }

  /// Get pending sync actions count
  Future<int> getPendingSyncCount() async {
    return await _syncQueue.getPendingCount();
  }

  /// Listen to sync events
  Stream<SyncEvent> get syncEvents => _syncQueue.syncEvents;
}
