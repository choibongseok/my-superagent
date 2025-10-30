import '../../../../core/network/api_client.dart';
import '../../../../core/storage/local_storage_service.dart';
import '../../../../core/connectivity/connectivity_service.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/task_model.dart';
import 'task_repository.dart';

/// Task repository with offline-first caching strategy
class CachedTaskRepository extends TaskRepository {
  final LocalStorageService _localStorage;
  final ConnectivityService _connectivity;

  CachedTaskRepository({
    required ApiClient apiClient,
    required LocalStorageService localStorage,
    required ConnectivityService connectivity,
  })  : _localStorage = localStorage,
        _connectivity = connectivity,
        super(apiClient: apiClient);

  /// Get all tasks (cache-first strategy)
  @override
  Future<List<TaskModel>> getTasks({
    int? limit,
    int? offset,
    String? status,
  }) async {
    try {
      // Always try to get from network first if online
      if (_connectivity.isOnline) {
        try {
          final tasks = await super.getTasks(
            limit: limit,
            offset: offset,
            status: status,
          );
          
          // Cache the results
          await _localStorage.saveTasks(tasks);
          print('📦 Cached ${tasks.length} tasks');
          
          return tasks;
        } catch (e) {
          print('⚠️ Network fetch failed, falling back to cache: $e');
          // Fall through to cache
        }
      }

      // If offline or network failed, use cache
      print('💾 Using cached tasks (offline)');
      return _localStorage.getAllTasks();
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to get tasks: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Get a single task by ID (cache-first)
  @override
  Future<TaskModel> getTaskById(String taskId) async {
    try {
      // Try network first if online
      if (_connectivity.isOnline) {
        try {
          final task = await super.getTaskById(taskId);
          
          // Cache the result
          await _localStorage.saveTask(task);
          print('📦 Cached task: $taskId');
          
          return task;
        } catch (e) {
          print('⚠️ Network fetch failed for task $taskId, using cache: $e');
          // Fall through to cache
        }
      }

      // Use cache
      final cachedTask = _localStorage.getTask(taskId);
      if (cachedTask != null) {
        print('💾 Using cached task: $taskId');
        return cachedTask;
      }

      throw NotFoundException(
        message: 'Task not found: $taskId',
      );
    } catch (e, stackTrace) {
      if (e is NotFoundException) rethrow;
      
      throw AppException(
        message: 'Failed to get task: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Create a new task (offline-capable)
  @override
  Future<TaskModel> createTask({
    required String prompt,
    required String taskType,
    Map<String, dynamic>? metadata,
  }) async {
    if (_connectivity.isOnline) {
      try {
        // Create on server
        final task = await super.createTask(
          prompt: prompt,
          taskType: taskType,
          metadata: metadata,
        );
        
        // Cache the result
        await _localStorage.saveTask(task);
        print('📦 Task created and cached: ${task.id}');
        
        return task;
      } catch (e) {
        print('⚠️ Network creation failed, queueing for later: $e');
        // Fall through to offline queue
      }
    }

    // If offline, create pending action
    print('📝 Queueing task creation for sync');
    
    // Create temporary local task
    final tempTask = TaskModel(
      id: 'temp_${DateTime.now().millisecondsSinceEpoch}',
      userId: 'local',
      prompt: prompt,
      taskType: taskType,
      status: 'pending',
      createdAt: DateTime.now(),
    );

    // Save to local storage
    await _localStorage.saveTask(tempTask);

    // Queue for sync
    await _localStorage.addPendingAction({
      'id': tempTask.id,
      'type': 'create_task',
      'data': {
        'prompt': prompt,
        'task_type': taskType,
        if (metadata != null) 'metadata': metadata,
      },
      'created_at': DateTime.now().toIso8601String(),
    });

    return tempTask;
  }

  /// Cancel a task (offline-capable)
  @override
  Future<void> cancelTask(String taskId) async {
    if (_connectivity.isOnline) {
      try {
        await super.cancelTask(taskId);
        
        // Update cache
        final task = _localStorage.getTask(taskId);
        if (task != null) {
          final updatedTask = task.copyWith(status: 'cancelled');
          await _localStorage.saveTask(updatedTask);
        }
        
        return;
      } catch (e) {
        print('⚠️ Network cancel failed, queueing: $e');
        // Fall through to offline queue
      }
    }

    // Queue for sync
    await _localStorage.addPendingAction({
      'id': DateTime.now().millisecondsSinceEpoch.toString(),
      'type': 'cancel_task',
      'data': {
        'task_id': taskId,
      },
      'created_at': DateTime.now().toIso8601String(),
    });

    // Update local cache
    final task = _localStorage.getTask(taskId);
    if (task != null) {
      final updatedTask = task.copyWith(status: 'cancelled');
      await _localStorage.saveTask(updatedTask);
    }
  }

  /// Delete a task (offline-capable)
  @override
  Future<void> deleteTask(String taskId) async {
    if (_connectivity.isOnline) {
      try {
        await super.deleteTask(taskId);
        
        // Remove from cache
        await _localStorage.deleteTask(taskId);
        
        return;
      } catch (e) {
        print('⚠️ Network delete failed, queueing: $e');
        // Fall through to offline queue
      }
    }

    // Queue for sync
    await _localStorage.addPendingAction({
      'id': DateTime.now().millisecondsSinceEpoch.toString(),
      'type': 'delete_task',
      'data': {
        'task_id': taskId,
      },
      'created_at': DateTime.now().toIso8601String(),
    });

    // Remove from local cache
    await _localStorage.deleteTask(taskId);
  }

  /// Get pending sync count
  int getPendingSyncCount() {
    return _localStorage.getPendingActions().length;
  }

  /// Check if task is local-only (not synced)
  bool isLocalOnly(String taskId) {
    return taskId.startsWith('temp_');
  }
}
