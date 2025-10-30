import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../storage/storage_provider.dart';
import '../connectivity/connectivity_provider.dart';
import '../../features/tasks/data/repositories/task_repository_provider.dart';
import 'sync_service.dart';

/// Provider for SyncService
final syncServiceProvider = Provider<SyncService>((ref) {
  final localStorage = ref.watch(localStorageServiceProvider);
  final connectivity = ref.watch(connectivityServiceProvider);
  final taskRepository = ref.watch(taskRepositoryProvider);

  return SyncService(
    localStorage: localStorage,
    connectivity: connectivity,
    taskRepository: taskRepository,
  );
});

/// Provider for sync status
final isSyncingProvider = StateProvider<bool>((ref) => false);

/// Provider for last sync time
final lastSyncTimeProvider = StateProvider<DateTime?>((ref) => null);
