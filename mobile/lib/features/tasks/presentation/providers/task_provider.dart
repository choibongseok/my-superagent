import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/models/task_model.dart';
import '../../data/repositories/task_repository_provider.dart';
import '../../../../core/errors/app_exception.dart';

/// Tasks state
class TasksState {
  final List<TaskModel> tasks;
  final bool isLoading;
  final String? error;

  const TasksState({
    this.tasks = const [],
    this.isLoading = false,
    this.error,
  });

  TasksState copyWith({
    List<TaskModel>? tasks,
    bool? isLoading,
    String? error,
  }) {
    return TasksState(
      tasks: tasks ?? this.tasks,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  TasksState clearError() {
    return TasksState(
      tasks: tasks,
      isLoading: isLoading,
      error: null,
    );
  }

  TasksState setLoading(bool loading) {
    return TasksState(
      tasks: tasks,
      isLoading: loading,
      error: null,
    );
  }
}

/// Tasks notifier
class TasksNotifier extends StateNotifier<TasksState> {
  final Ref _ref;
  final Map<String, bool> _pollingTasks = {};

  TasksNotifier(this._ref) : super(const TasksState());

  /// Load all tasks
  Future<void> loadTasks({bool refresh = false}) async {
    // Don't set loading if refreshing (to avoid UI flicker)
    if (!refresh) {
      state = state.setLoading(true);
    }

    try {
      final taskRepo = _ref.read(taskRepositoryProvider);
      final tasks = await taskRepo.getTasks();

      state = TasksState(
        tasks: tasks,
        isLoading: false,
        error: null,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: '작업 목록을 불러오는데 실패했습니다: $e',
      );
    }
  }

  /// Create a new task and start polling
  Future<TaskModel?> createTask({
    required String prompt,
    required String taskType,
  }) async {
    try {
      final taskRepo = _ref.read(taskRepositoryProvider);
      final task = await taskRepo.createTask(
        prompt: prompt,
        taskType: taskType,
      );

      // Add task to list
      state = state.copyWith(
        tasks: [task, ...state.tasks],
      );

      // Start background polling for this task
      _pollTaskStatus(task.id);

      return task;
    } on ValidationException catch (e) {
      state = state.copyWith(
        error: e.message,
      );
      return null;
    } catch (e) {
      state = state.copyWith(
        error: '작업 생성에 실패했습니다: $e',
      );
      return null;
    }
  }

  /// Cancel a task
  Future<bool> cancelTask(String taskId) async {
    try {
      final taskRepo = _ref.read(taskRepositoryProvider);
      await taskRepo.cancelTask(taskId);

      // Stop polling
      _pollingTasks[taskId] = false;

      // Reload tasks
      await loadTasks(refresh: true);

      return true;
    } catch (e) {
      state = state.copyWith(
        error: '작업 취소에 실패했습니다: $e',
      );
      return false;
    }
  }

  /// Delete a task
  Future<bool> deleteTask(String taskId) async {
    try {
      final taskRepo = _ref.read(taskRepositoryProvider);
      await taskRepo.deleteTask(taskId);

      // Stop polling
      _pollingTasks[taskId] = false;

      // Remove from list
      state = state.copyWith(
        tasks: state.tasks.where((t) => t.id != taskId).toList(),
      );

      return true;
    } catch (e) {
      state = state.copyWith(
        error: '작업 삭제에 실패했습니다: $e',
      );
      return false;
    }
  }

  /// Background polling for task status
  Future<void> _pollTaskStatus(String taskId) async {
    // Mark as polling
    _pollingTasks[taskId] = true;

    try {
      final taskRepo = _ref.read(taskRepositoryProvider);

      await taskRepo.pollTaskStatusWithCallback(
        taskId,
        interval: const Duration(seconds: 2),
        timeout: const Duration(minutes: 10),
        onStatusUpdate: (task) {
          // Update task in list
          _updateTaskInList(task);
        },
      );
    } catch (e) {
      print('Polling error for task $taskId: $e');
    } finally {
      // Mark as not polling
      _pollingTasks[taskId] = false;
    }
  }

  /// Update a specific task in the list
  void _updateTaskInList(TaskModel updatedTask) {
    final updatedTasks = state.tasks.map((task) {
      return task.id == updatedTask.id ? updatedTask : task;
    }).toList();

    state = state.copyWith(tasks: updatedTasks);
  }

  /// Refresh a specific task
  Future<void> refreshTask(String taskId) async {
    try {
      final taskRepo = _ref.read(taskRepositoryProvider);
      final task = await taskRepo.getTaskById(taskId);
      _updateTaskInList(task);
    } catch (e) {
      print('Refresh task error: $e');
    }
  }

  /// Clear error
  void clearError() {
    state = state.clearError();
  }
}

/// Tasks provider
final tasksProvider = StateNotifierProvider<TasksNotifier, TasksState>((ref) {
  return TasksNotifier(ref);
});

/// Single task provider (by ID)
final taskProvider = FutureProvider.family<TaskModel?, String>((ref, taskId) async {
  try {
    final taskRepo = ref.watch(taskRepositoryProvider);
    return await taskRepo.getTaskById(taskId);
  } catch (e) {
    print('Get task error: $e');
    return null;
  }
});

/// Task stream provider (for real-time updates)
final taskStreamProvider = StreamProvider.family<TaskModel, String>((ref, taskId) {
  final taskRepo = ref.watch(taskRepositoryProvider);
  return taskRepo.watchTaskStatus(
    taskId,
    interval: const Duration(seconds: 2),
    timeout: const Duration(minutes: 10),
  );
});

/// Task statistics provider
final taskStatisticsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  try {
    final taskRepo = ref.watch(taskRepositoryProvider);
    return await taskRepo.getTaskStatistics();
  } catch (e) {
    print('Get task statistics error: $e');
    return {};
  }
});
