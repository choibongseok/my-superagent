import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/network/api_provider.dart';
import '../../../../core/storage/storage_provider.dart';
import '../../../../core/connectivity/connectivity_provider.dart';
import 'task_repository.dart';
import 'cached_task_repository.dart';

/// Provider for basic TaskRepository (no caching)
final basicTaskRepositoryProvider = Provider<TaskRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return TaskRepository(apiClient: apiClient);
});

/// Provider for CachedTaskRepository (with offline support)
final cachedTaskRepositoryProvider = Provider<CachedTaskRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  final localStorage = ref.watch(localStorageServiceProvider);
  final connectivity = ref.watch(connectivityServiceProvider);
  
  return CachedTaskRepository(
    apiClient: apiClient,
    localStorage: localStorage,
    connectivity: connectivity,
  );
});

/// Default provider - uses cached repository
final taskRepositoryProvider = Provider<TaskRepository>((ref) {
  return ref.watch(cachedTaskRepositoryProvider);
});
