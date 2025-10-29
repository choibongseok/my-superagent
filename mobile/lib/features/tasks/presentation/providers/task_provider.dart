import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../auth/presentation/providers/auth_provider.dart';
import '../../data/models/task_model.dart';
import '../../data/repositories/task_repository.dart';

// Task Repository Provider
final taskRepositoryProvider = Provider<TaskRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return TaskRepository(apiClient);
});

// Tasks State
class TasksState {
  final List<TaskModel> tasks;
  final bool isLoading;
  final String? error;
  final bool hasMore;

  const TasksState({
    this.tasks = const [],
    this.isLoading = false,
    this.error,
    this.hasMore = true,
  });

  TasksState copyWith({
    List<TaskModel>? tasks,
    bool? isLoading,
    String? error,
    bool? hasMore,
    bool clearError = false,
  }) {
    return TasksState(
      tasks: tasks ?? this.tasks,
      isLoading: isLoading ?? this.isLoading,
      error: clearError ? null : (error ?? this.error),
      hasMore: hasMore ?? this.hasMore,
    );
  }
}

// Tasks State Notifier
class TasksNotifier extends StateNotifier<TasksState> {
  final TaskRepository _taskRepository;

  TasksNotifier(this._taskRepository) : super(const TasksState());

  /// Load tasks
  Future<void> loadTasks({bool refresh = false}) async {
    if (state.isLoading) return;

    if (refresh) {
      state = const TasksState(isLoading: true);
    } else {
      state = state.copyWith(isLoading: true, clearError: true);
    }

    try {
      final tasks = await _taskRepository.getTasks();

      state = state.copyWith(
        tasks: tasks,
        isLoading: false,
        hasMore: false, // Simple pagination for now
        clearError: true,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: 'Failed to load tasks: $e',
      );
    }
  }

  /// Create a new task
  Future<TaskModel?> createTask({
    required String prompt,
    required String taskType,
  }) async {
    try {
      final task = await _taskRepository.createTask(
        prompt: prompt,
        taskType: taskType,
      );

      // Add to list
      state = state.copyWith(
        tasks: [task, ...state.tasks],
        clearError: true,
      );

      // Start polling for updates
      _pollTaskStatus(task.id);

      return task;
    } catch (e) {
      state = state.copyWith(error: 'Failed to create task: $e');
      return null;
    }
  }

  /// Poll task status in background
  Future<void> _pollTaskStatus(String taskId) async {
    try {
      final updatedTask = await _taskRepository.pollTaskStatus(taskId);

      // Update task in list
      final updatedTasks = state.tasks.map((task) {
        return task.id == taskId ? updatedTask : task;
      }).toList();

      state = state.copyWith(tasks: updatedTasks);
    } catch (e) {
      print('Task polling error: $e');
    }
  }

  /// Cancel task
  Future<bool> cancelTask(String taskId) async {
    try {
      final success = await _taskRepository.cancelTask(taskId);

      if (success) {
        // Remove from list
        final updatedTasks = state.tasks
            .where((task) => task.id != taskId)
            .toList();

        state = state.copyWith(tasks: updatedTasks);
      }

      return success;
    } catch (e) {
      state = state.copyWith(error: 'Failed to cancel task: $e');
      return false;
    }
  }

  /// Clear error
  void clearError() {
    state = state.copyWith(clearError: true);
  }
}

// Tasks State Provider
final tasksProvider = StateNotifierProvider<TasksNotifier, TasksState>((ref) {
  final taskRepository = ref.watch(taskRepositoryProvider);
  return TasksNotifier(taskRepository);
});

// Individual Task Provider
final taskProvider = FutureProvider.family<TaskModel?, String>((ref, taskId) async {
  final taskRepository = ref.watch(taskRepositoryProvider);
  return await taskRepository.getTaskById(taskId);
});

// Task Result Provider
final taskResultProvider = FutureProvider.family<Map<String, dynamic>?, String>((ref, taskId) async {
  final taskRepository = ref.watch(taskRepositoryProvider);
  return await taskRepository.getTaskResult(taskId);
});
