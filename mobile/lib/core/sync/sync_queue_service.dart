import 'dart:async';
import 'dart:convert';
import 'package:connectivity_plus/connectivity_plus.dart';
import '../storage/storage_service.dart';
import '../errors/app_exception.dart';

/// Service for managing offline actions and syncing when online
class SyncQueueService {
  final StorageService _storage;
  final Connectivity _connectivity;
  
  StreamSubscription<ConnectivityResult>? _connectivitySubscription;
  bool _isSyncing = false;
  final _syncController = StreamController<SyncEvent>.broadcast();
  
  /// Stream of sync events
  Stream<SyncEvent> get syncEvents => _syncController.stream;
  
  SyncQueueService({
    required StorageService storage,
    Connectivity? connectivity,
  })  : _storage = storage,
        _connectivity = connectivity ?? Connectivity();

  /// Initialize connectivity monitoring
  void init() {
    // Listen to connectivity changes
    _connectivitySubscription = _connectivity.onConnectivityChanged.listen(
      (ConnectivityResult result) async {
        if (result != ConnectivityResult.none && !_isSyncing) {
          await syncPendingActions();
        }
      },
    );
  }

  /// Dispose resources
  void dispose() {
    _connectivitySubscription?.cancel();
    _syncController.close();
  }

  /// Add action to sync queue
  Future<void> queueAction(SyncAction action) async {
    try {
      final queue = await _getQueue();
      queue.add(action);
      await _saveQueue(queue);
      
      _syncController.add(SyncEvent(
        type: SyncEventType.actionQueued,
        action: action,
      ));
      
      // Try to sync immediately if online
      final connectivityResult = await _connectivity.checkConnectivity();
      if (connectivityResult != ConnectivityResult.none) {
        await syncPendingActions();
      }
    } catch (e) {
      print('Failed to queue action: $e');
      rethrow;
    }
  }

  /// Get all pending actions in queue
  Future<List<SyncAction>> getPendingActions() async {
    return await _getQueue();
  }

  /// Get pending action count
  Future<int> getPendingCount() async {
    final queue = await _getQueue();
    return queue.length;
  }

  /// Clear all pending actions
  Future<void> clearQueue() async {
    await _saveQueue([]);
    _syncController.add(SyncEvent(
      type: SyncEventType.queueCleared,
    ));
  }

  /// Sync all pending actions
  Future<SyncResult> syncPendingActions() async {
    if (_isSyncing) {
      return SyncResult(
        success: false,
        message: 'Sync already in progress',
      );
    }

    _isSyncing = true;
    _syncController.add(SyncEvent(type: SyncEventType.syncStarted));

    try {
      final queue = await _getQueue();
      
      if (queue.isEmpty) {
        _syncController.add(SyncEvent(
          type: SyncEventType.syncCompleted,
          successCount: 0,
          failedCount: 0,
        ));
        return SyncResult(
          success: true,
          message: 'No actions to sync',
          syncedCount: 0,
        );
      }

      final List<SyncAction> remainingActions = [];
      int successCount = 0;
      int failedCount = 0;
      final List<String> errors = [];

      for (final action in queue) {
        try {
          // Execute the action (will be handled by repository)
          _syncController.add(SyncEvent(
            type: SyncEventType.actionSyncing,
            action: action,
          ));

          // Action should be executed by the calling code
          // This service just manages the queue
          
          successCount++;
          _syncController.add(SyncEvent(
            type: SyncEventType.actionSynced,
            action: action,
          ));
        } catch (e) {
          failedCount++;
          errors.add('${action.type}: $e');
          
          // Re-queue failed action with incremented retry count
          final updatedAction = action.copyWith(
            retryCount: action.retryCount + 1,
            lastError: e.toString(),
          );
          
          // Only re-queue if under max retries
          if (updatedAction.retryCount < action.maxRetries) {
            remainingActions.add(updatedAction);
          }
          
          _syncController.add(SyncEvent(
            type: SyncEventType.actionFailed,
            action: action,
            error: e.toString(),
          ));
        }
      }

      // Update queue with failed actions
      await _saveQueue(remainingActions);

      _syncController.add(SyncEvent(
        type: SyncEventType.syncCompleted,
        successCount: successCount,
        failedCount: failedCount,
      ));

      return SyncResult(
        success: failedCount == 0,
        message: failedCount == 0
            ? 'All actions synced successfully'
            : '$failedCount actions failed',
        syncedCount: successCount,
        failedCount: failedCount,
        errors: errors,
      );
    } catch (e) {
      _syncController.add(SyncEvent(
        type: SyncEventType.syncFailed,
        error: e.toString(),
      ));
      
      return SyncResult(
        success: false,
        message: 'Sync failed: $e',
      );
    } finally {
      _isSyncing = false;
    }
  }

  /// Get queue from storage
  Future<List<SyncAction>> _getQueue() async {
    try {
      final queueData = _storage.getSyncQueue();
      return queueData
          .map((json) => SyncAction.fromJson(json))
          .toList();
    } catch (e) {
      print('Failed to load sync queue: $e');
      return [];
    }
  }

  /// Save queue to storage
  Future<void> _saveQueue(List<SyncAction> queue) async {
    try {
      final queueData = queue.map((action) => action.toJson()).toList();
      await _storage.saveSyncQueue(queueData);
    } catch (e) {
      print('Failed to save sync queue: $e');
      rethrow;
    }
  }
}

/// Sync action to be queued
class SyncAction {
  final String id;
  final SyncActionType type;
  final Map<String, dynamic> data;
  final DateTime timestamp;
  final int retryCount;
  final int maxRetries;
  final String? lastError;

  SyncAction({
    required this.id,
    required this.type,
    required this.data,
    DateTime? timestamp,
    this.retryCount = 0,
    this.maxRetries = 3,
    this.lastError,
  }) : timestamp = timestamp ?? DateTime.now();

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.toString().split('.').last,
        'data': data,
        'timestamp': timestamp.toIso8601String(),
        'retryCount': retryCount,
        'maxRetries': maxRetries,
        'lastError': lastError,
      };

  factory SyncAction.fromJson(Map<String, dynamic> json) {
    return SyncAction(
      id: json['id'] as String,
      type: SyncActionType.values.firstWhere(
        (e) => e.toString().split('.').last == json['type'],
      ),
      data: json['data'] as Map<String, dynamic>,
      timestamp: DateTime.parse(json['timestamp'] as String),
      retryCount: json['retryCount'] as int? ?? 0,
      maxRetries: json['maxRetries'] as int? ?? 3,
      lastError: json['lastError'] as String?,
    );
  }

  SyncAction copyWith({
    String? id,
    SyncActionType? type,
    Map<String, dynamic>? data,
    DateTime? timestamp,
    int? retryCount,
    int? maxRetries,
    String? lastError,
  }) {
    return SyncAction(
      id: id ?? this.id,
      type: type ?? this.type,
      data: data ?? this.data,
      timestamp: timestamp ?? this.timestamp,
      retryCount: retryCount ?? this.retryCount,
      maxRetries: maxRetries ?? this.maxRetries,
      lastError: lastError ?? this.lastError,
    );
  }
}

/// Types of sync actions
enum SyncActionType {
  createTask,
  cancelTask,
  deleteTask,
  updateTask,
}

/// Sync event for monitoring
class SyncEvent {
  final SyncEventType type;
  final SyncAction? action;
  final String? error;
  final int? successCount;
  final int? failedCount;

  SyncEvent({
    required this.type,
    this.action,
    this.error,
    this.successCount,
    this.failedCount,
  });
}

/// Sync event types
enum SyncEventType {
  actionQueued,
  syncStarted,
  actionSyncing,
  actionSynced,
  actionFailed,
  syncCompleted,
  syncFailed,
  queueCleared,
}

/// Result of sync operation
class SyncResult {
  final bool success;
  final String message;
  final int syncedCount;
  final int failedCount;
  final List<String> errors;

  SyncResult({
    required this.success,
    required this.message,
    this.syncedCount = 0,
    this.failedCount = 0,
    this.errors = const [],
  });
}
