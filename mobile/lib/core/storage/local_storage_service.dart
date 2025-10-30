import 'package:hive_flutter/hive_flutter.dart';
import '../../features/auth/data/models/user_model.dart';
import '../../features/auth/data/models/user_model_adapter.dart';
import '../../features/tasks/data/models/task_model.dart';
import '../../features/tasks/data/models/task_model_adapter.dart';

/// Local storage service using Hive
class LocalStorageService {
  static const String _userBoxName = 'users';
  static const String _taskBoxName = 'tasks';
  static const String _metaBoxName = 'meta';
  static const String _pendingActionsBoxName = 'pending_actions';

  Box<UserModel>? _userBox;
  Box<TaskModel>? _taskBox;
  Box<dynamic>? _metaBox;
  Box<dynamic>? _pendingActionsBox;

  bool _isInitialized = false;

  /// Initialize Hive and register adapters
  Future<void> initialize() async {
    if (_isInitialized) return;

    // Initialize Hive
    await Hive.initFlutter();

    // Register adapters
    if (!Hive.isAdapterRegistered(0)) {
      Hive.registerAdapter(UserModelAdapter());
    }
    if (!Hive.isAdapterRegistered(1)) {
      Hive.registerAdapter(TaskModelAdapter());
    }

    // Open boxes
    _userBox = await Hive.openBox<UserModel>(_userBoxName);
    _taskBox = await Hive.openBox<TaskModel>(_taskBoxName);
    _metaBox = await Hive.openBox<dynamic>(_metaBoxName);
    _pendingActionsBox = await Hive.openBox<dynamic>(_pendingActionsBoxName);

    _isInitialized = true;
  }

  /// Ensure service is initialized
  void _ensureInitialized() {
    if (!_isInitialized) {
      throw StateError('LocalStorageService not initialized. Call initialize() first.');
    }
  }

  // ==================== User Operations ====================

  /// Save user to local storage
  Future<void> saveUser(UserModel user) async {
    _ensureInitialized();
    await _userBox!.put('current_user', user);
  }

  /// Get current user from local storage
  UserModel? getCurrentUser() {
    _ensureInitialized();
    return _userBox!.get('current_user');
  }

  /// Delete current user
  Future<void> deleteCurrentUser() async {
    _ensureInitialized();
    await _userBox!.delete('current_user');
  }

  // ==================== Task Operations ====================

  /// Save task to local storage
  Future<void> saveTask(TaskModel task) async {
    _ensureInitialized();
    await _taskBox!.put(task.id, task);
    await _updateLastSyncTime('task_${task.id}');
  }

  /// Get task by ID
  TaskModel? getTask(String taskId) {
    _ensureInitialized();
    return _taskBox!.get(taskId);
  }

  /// Get all tasks
  List<TaskModel> getAllTasks() {
    _ensureInitialized();
    return _taskBox!.values.toList();
  }

  /// Get tasks by user ID
  List<TaskModel> getTasksByUserId(String userId) {
    _ensureInitialized();
    return _taskBox!.values.where((task) => task.userId == userId).toList();
  }

  /// Get tasks by status
  List<TaskModel> getTasksByStatus(String status) {
    _ensureInitialized();
    return _taskBox!.values.where((task) => task.status == status).toList();
  }

  /// Save multiple tasks
  Future<void> saveTasks(List<TaskModel> tasks) async {
    _ensureInitialized();
    final Map<String, TaskModel> taskMap = {
      for (var task in tasks) task.id: task
    };
    await _taskBox!.putAll(taskMap);
    await _updateLastSyncTime('tasks');
  }

  /// Delete task
  Future<void> deleteTask(String taskId) async {
    _ensureInitialized();
    await _taskBox!.delete(taskId);
    await _metaBox!.delete('sync_task_$taskId');
  }

  /// Clear all tasks
  Future<void> clearAllTasks() async {
    _ensureInitialized();
    await _taskBox!.clear();
  }

  // ==================== Pending Actions (Offline Queue) ====================

  /// Add pending action (for offline operations)
  Future<void> addPendingAction(Map<String, dynamic> action) async {
    _ensureInitialized();
    final actions = getPendingActions();
    actions.add(action);
    await _pendingActionsBox!.put('actions', actions);
  }

  /// Get all pending actions
  List<Map<String, dynamic>> getPendingActions() {
    _ensureInitialized();
    final dynamic actions = _pendingActionsBox!.get('actions', defaultValue: <dynamic>[]);
    if (actions is List) {
      return actions.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    }
    return [];
  }

  /// Remove pending action
  Future<void> removePendingAction(Map<String, dynamic> action) async {
    _ensureInitialized();
    final actions = getPendingActions();
    actions.removeWhere((a) => 
      a['id'] == action['id'] && 
      a['type'] == action['type']
    );
    await _pendingActionsBox!.put('actions', actions);
  }

  /// Clear all pending actions
  Future<void> clearPendingActions() async {
    _ensureInitialized();
    await _pendingActionsBox!.delete('actions');
  }

  // ==================== Metadata & Sync Operations ====================

  /// Update last sync time
  Future<void> _updateLastSyncTime(String key) async {
    await _metaBox!.put('sync_$key', DateTime.now().toIso8601String());
  }

  /// Get last sync time
  DateTime? getLastSyncTime(String key) {
    _ensureInitialized();
    final String? timestamp = _metaBox!.get('sync_$key');
    if (timestamp != null) {
      return DateTime.tryParse(timestamp);
    }
    return null;
  }

  /// Check if data is stale (needs refresh)
  bool isDataStale(String key, Duration staleDuration) {
    final lastSync = getLastSyncTime(key);
    if (lastSync == null) return true;
    
    final difference = DateTime.now().difference(lastSync);
    return difference > staleDuration;
  }

  /// Save metadata
  Future<void> saveMeta(String key, dynamic value) async {
    _ensureInitialized();
    await _metaBox!.put(key, value);
  }

  /// Get metadata
  dynamic getMeta(String key, {dynamic defaultValue}) {
    _ensureInitialized();
    return _metaBox!.get(key, defaultValue: defaultValue);
  }

  /// Delete metadata
  Future<void> deleteMeta(String key) async {
    _ensureInitialized();
    await _metaBox!.delete(key);
  }

  // ==================== Cache Management ====================

  /// Get cache size in bytes
  int getCacheSize() {
    _ensureInitialized();
    int size = 0;
    size += _userBox?.length ?? 0;
    size += _taskBox?.length ?? 0;
    size += _metaBox?.length ?? 0;
    size += _pendingActionsBox?.length ?? 0;
    return size;
  }

  /// Clear all cache
  Future<void> clearAllCache() async {
    _ensureInitialized();
    await _userBox!.clear();
    await _taskBox!.clear();
    await _metaBox!.clear();
    await _pendingActionsBox!.clear();
  }

  /// Clear expired cache
  Future<void> clearExpiredCache(Duration expirationDuration) async {
    _ensureInitialized();
    
    // Clear expired tasks
    final tasks = getAllTasks();
    for (var task in tasks) {
      final lastSync = getLastSyncTime('task_${task.id}');
      if (lastSync != null) {
        final age = DateTime.now().difference(lastSync);
        if (age > expirationDuration) {
          await deleteTask(task.id);
        }
      }
    }
  }

  /// Close all boxes
  Future<void> close() async {
    await _userBox?.close();
    await _taskBox?.close();
    await _metaBox?.close();
    await _pendingActionsBox?.close();
    _isInitialized = false;
  }

  /// Delete all data and close
  Future<void> deleteAllData() async {
    await clearAllCache();
    await close();
    await Hive.deleteBoxFromDisk(_userBoxName);
    await Hive.deleteBoxFromDisk(_taskBoxName);
    await Hive.deleteBoxFromDisk(_metaBoxName);
    await Hive.deleteBoxFromDisk(_pendingActionsBoxName);
  }
}
