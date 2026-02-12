import 'package:hive_flutter/hive_flutter.dart';
import '../models/task_model.dart';

/// Service for managing local cache using Hive
class LocalCacheService {
  static const String _tasksBoxName = 'tasks_cache';
  static const String _syncQueueBoxName = 'sync_queue';

  Box<Map>? _tasksBox;
  Box<Map>? _syncQueueBox;

  /// Initialize Hive and open boxes
  Future<void> init() async {
    await Hive.initFlutter();
    
    // Register adapters if needed
    // Note: For simplicity, we're using Map instead of custom adapters
    
    _tasksBox = await Hive.openBox<Map>(_tasksBoxName);
    _syncQueueBox = await Hive.openBox<Map>(_syncQueueBoxName);
  }

  /// Cache a task locally
  Future<void> cacheTask(TaskModel task) async {
    await _tasksBox?.put(task.id, task.toJson());
  }

  /// Get a cached task by ID
  TaskModel? getCachedTask(String taskId) {
    final data = _tasksBox?.get(taskId);
    if (data == null) return null;
    return TaskModel.fromJson(Map<String, dynamic>.from(data));
  }

  /// Get all cached tasks
  List<TaskModel> getAllCachedTasks() {
    final tasks = <TaskModel>[];
    for (var data in _tasksBox?.values ?? []) {
      try {
        tasks.add(TaskModel.fromJson(Map<String, dynamic>.from(data)));
      } catch (e) {
        // Skip invalid entries
        continue;
      }
    }
    return tasks;
  }

  /// Remove a task from cache
  Future<void> removeCachedTask(String taskId) async {
    await _tasksBox?.delete(taskId);
  }

  /// Add an operation to sync queue (for offline mode)
  Future<void> addToSyncQueue({
    required String operation, // 'create', 'update', 'delete', 'cancel'
    required Map<String, dynamic> data,
  }) async {
    final id = DateTime.now().millisecondsSinceEpoch.toString();
    await _syncQueueBox?.put(id, {
      'operation': operation,
      'data': data,
      'timestamp': DateTime.now().toIso8601String(),
    });
  }

  /// Get all pending sync operations
  List<Map<String, dynamic>> getSyncQueue() {
    final operations = <Map<String, dynamic>>[];
    for (var entry in _syncQueueBox?.toMap().entries ?? []) {
      operations.add({
        'id': entry.key,
        ...Map<String, dynamic>.from(entry.value),
      });
    }
    return operations;
  }

  /// Remove a sync operation from queue
  Future<void> removeSyncOperation(String id) async {
    await _syncQueueBox?.delete(id);
  }

  /// Clear all sync operations
  Future<void> clearSyncQueue() async {
    await _syncQueueBox?.clear();
  }

  /// Clear all caches
  Future<void> clearAll() async {
    await _tasksBox?.clear();
    await _syncQueueBox?.clear();
  }

  /// Close all boxes
  Future<void> close() async {
    await _tasksBox?.close();
    await _syncQueueBox?.close();
  }
}
