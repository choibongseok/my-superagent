import 'dart:async';
import '../storage/local_storage_service.dart';
import '../connectivity/connectivity_service.dart';
import '../../features/tasks/data/repositories/task_repository.dart';
import '../../features/tasks/data/models/task_model.dart';

/// Sync strategy for offline/online synchronization
enum SyncStrategy {
  /// Server data always wins
  serverWins,
  
  /// Client data always wins
  clientWins,
  
  /// Most recent modification wins
  lastWriteWins,
  
  /// Manual merge required
  manual,
}

/// Sync service for managing offline/online data synchronization
class SyncService {
  final LocalStorageService _localStorage;
  final ConnectivityService _connectivity;
  final TaskRepository _taskRepository;

  Timer? _syncTimer;
  bool _isSyncing = false;

  SyncService({
    required LocalStorageService localStorage,
    required ConnectivityService connectivity,
    required TaskRepository taskRepository,
  })  : _localStorage = localStorage,
        _connectivity = connectivity,
        _taskRepository = taskRepository;

  /// Start automatic sync (when online)
  void startAutoSync({Duration interval = const Duration(minutes: 5)}) {
    _syncTimer?.cancel();
    _syncTimer = Timer.periodic(interval, (timer) {
      if (_connectivity.isOnline && !_isSyncing) {
        syncAll();
      }
    });
  }

  /// Stop automatic sync
  void stopAutoSync() {
    _syncTimer?.cancel();
    _syncTimer = null;
  }

  /// Sync all data
  Future<SyncResult> syncAll() async {
    if (_isSyncing) {
      return SyncResult(
        success: false,
        message: 'Sync already in progress',
      );
    }

    if (!_connectivity.isOnline) {
      return SyncResult(
        success: false,
        message: 'Cannot sync: Device is offline',
      );
    }

    _isSyncing = true;

    try {
      print('🔄 Starting sync...');

      // 1. Sync pending actions (offline queue)
      await _syncPendingActions();

      // 2. Sync tasks
      final taskSyncResult = await _syncTasks();

      print('✅ Sync completed successfully');

      return SyncResult(
        success: true,
        message: 'Sync completed',
        tasksSynced: taskSyncResult.synced,
        tasksConflicted: taskSyncResult.conflicts,
      );
    } catch (e, stackTrace) {
      print('❌ Sync failed: $e');
      print(stackTrace);
      return SyncResult(
        success: false,
        message: 'Sync failed: $e',
      );
    } finally {
      _isSyncing = false;
    }
  }

  /// Sync pending actions (offline operations)
  Future<void> _syncPendingActions() async {
    final pendingActions = _localStorage.getPendingActions();

    if (pendingActions.isEmpty) {
      print('  No pending actions to sync');
      return;
    }

    print('  Syncing ${pendingActions.length} pending actions...');

    for (var action in List.from(pendingActions)) {
      try {
        await _processPendingAction(action);
        await _localStorage.removePendingAction(action);
        print('    ✓ Processed action: ${action['type']}');
      } catch (e) {
        print('    ✗ Failed to process action: ${action['type']} - $e');
        // Keep in queue for retry
      }
    }
  }

  /// Process a single pending action
  Future<void> _processPendingAction(Map<String, dynamic> action) async {
    final type = action['type'] as String;
    final data = action['data'] as Map<String, dynamic>;

    switch (type) {
      case 'create_task':
        await _taskRepository.createTask(
          prompt: data['prompt'] as String,
          taskType: data['task_type'] as String,
        );
        break;

      case 'delete_task':
        await _taskRepository.deleteTask(data['task_id'] as String);
        break;

      case 'cancel_task':
        await _taskRepository.cancelTask(data['task_id'] as String);
        break;

      default:
        print('    Unknown action type: $type');
    }
  }

  /// Sync tasks with server
  Future<_SyncTasksResult> _syncTasks() async {
    print('  Syncing tasks...');

    int synced = 0;
    int conflicts = 0;

    try {
      // Fetch tasks from server
      final serverTasks = await _taskRepository.getTasks();
      print('    Fetched ${serverTasks.length} tasks from server');

      // Get local tasks
      final localTasks = _localStorage.getAllTasks();
      print('    Found ${localTasks.length} local tasks');

      // Build maps for comparison
      final serverTaskMap = {for (var task in serverTasks) task.id: task};
      final localTaskMap = {for (var task in localTasks) task.id: task};

      // Detect conflicts and merge
      final mergedTasks = <String, TaskModel>{};

      // Process server tasks
      for (var serverTask in serverTasks) {
        final localTask = localTaskMap[serverTask.id];

        if (localTask == null) {
          // New task from server - just add it
          mergedTasks[serverTask.id] = serverTask;
          synced++;
        } else {
          // Task exists locally - check for conflicts
          final resolved = await _resolveTaskConflict(
            local: localTask,
            server: serverTask,
            strategy: SyncStrategy.serverWins, // Default strategy
          );

          mergedTasks[serverTask.id] = resolved;

          if (resolved.id == serverTask.id && 
              resolved.status != localTask.status) {
            conflicts++;
          } else {
            synced++;
          }
        }
      }

      // Process local-only tasks (might be new or deleted on server)
      for (var localTask in localTasks) {
        if (!serverTaskMap.containsKey(localTask.id)) {
          // Task exists locally but not on server
          // Could be a new offline task or deleted on server
          // For now, keep local version
          mergedTasks[localTask.id] = localTask;
        }
      }

      // Save merged tasks to local storage
      await _localStorage.saveTasks(mergedTasks.values.toList());
      print('    Saved ${mergedTasks.length} merged tasks locally');

      return _SyncTasksResult(
        synced: synced,
        conflicts: conflicts,
      );
    } catch (e) {
      print('    Task sync failed: $e');
      rethrow;
    }
  }

  /// Resolve conflict between local and server task
  Future<TaskModel> _resolveTaskConflict({
    required TaskModel local,
    required TaskModel server,
    required SyncStrategy strategy,
  }) async {
    switch (strategy) {
      case SyncStrategy.serverWins:
        return server;

      case SyncStrategy.clientWins:
        return local;

      case SyncStrategy.lastWriteWins:
        // Compare timestamps
        final localTime = local.completedAt ?? local.createdAt;
        final serverTime = server.completedAt ?? server.createdAt;
        
        if (serverTime.isAfter(localTime)) {
          return server;
        } else {
          return local;
        }

      case SyncStrategy.manual:
        // For manual strategy, prefer server for now
        // In a real app, you would show a UI for user to resolve
        print('    ⚠️ Manual conflict resolution required for task: ${local.id}');
        return server;
    }
  }

  /// Force sync now (manual trigger)
  Future<SyncResult> forceSyncNow() async {
    return await syncAll();
  }

  /// Check if sync is needed
  bool needsSync() {
    // Check if there are pending actions
    final pendingActions = _localStorage.getPendingActions();
    if (pendingActions.isNotEmpty) return true;

    // Check if tasks data is stale
    if (_localStorage.isDataStale('tasks', const Duration(minutes: 10))) {
      return true;
    }

    return false;
  }

  /// Dispose resources
  void dispose() {
    stopAutoSync();
  }
}

/// Sync result
class SyncResult {
  final bool success;
  final String message;
  final int tasksSynced;
  final int tasksConflicted;

  SyncResult({
    required this.success,
    required this.message,
    this.tasksSynced = 0,
    this.tasksConflicted = 0,
  });

  @override
  String toString() {
    return 'SyncResult(success: $success, message: $message, '
        'synced: $tasksSynced, conflicts: $tasksConflicted)';
  }
}

/// Internal result for task sync
class _SyncTasksResult {
  final int synced;
  final int conflicts;

  _SyncTasksResult({
    required this.synced,
    required this.conflicts,
  });
}
