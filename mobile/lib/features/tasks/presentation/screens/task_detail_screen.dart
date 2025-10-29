import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../shared/themes/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import '../providers/task_provider.dart';
import '../widgets/task_status_chip.dart';

class TaskDetailScreen extends ConsumerWidget {
  final String taskId;

  const TaskDetailScreen({
    Key? key,
    required this.taskId,
  }) : super(key: key);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final taskAsync = ref.watch(taskProvider(taskId));

    return Scaffold(
      backgroundColor: AppColors.backgroundDark,
      appBar: AppBar(
        backgroundColor: AppColors.backgroundDark,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
        title: const Text('작업 상세'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ref.invalidate(taskProvider(taskId));
            },
          ),
        ],
      ),
      body: taskAsync.when(
        loading: () => const Center(
          child: CircularProgressIndicator(color: AppColors.primary),
        ),
        error: (error, stack) => Center(
          child: Padding(
            padding: const EdgeInsets.all(32.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.error_outline, size: 64, color: AppColors.error),
                const SizedBox(height: 16),
                Text(
                  '작업을 불러올 수 없습니다',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                Text(
                  error.toString(),
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppColors.textSecondary,
                      ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
        data: (task) {
          if (task == null) {
            return Center(
              child: Text(
                '작업을 찾을 수 없습니다',
                style: Theme.of(context).textTheme.titleLarge,
              ),
            );
          }

          return SingleChildScrollView(
            padding: const EdgeInsets.all(AppConstants.paddingLarge),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Status chip
                TaskStatusChip(status: task.status),
                
                const SizedBox(height: 24),
                
                // Task type
                _buildSection(
                  context,
                  '작업 유형',
                  AppConstants.agentLabels[task.taskType] ?? task.taskType,
                ),
                
                const SizedBox(height: 24),
                
                // Prompt
                _buildSection(
                  context,
                  '요청 내용',
                  task.prompt,
                ),
                
                const SizedBox(height: 24),
                
                // Created at
                _buildSection(
                  context,
                  '생성 시간',
                  _formatDateTime(task.createdAt),
                ),
                
                if (task.completedAt != null) ...[
                  const SizedBox(height: 24),
                  _buildSection(
                    context,
                    '완료 시간',
                    _formatDateTime(task.completedAt!),
                  ),
                ],
                
                if (task.documentUrl != null) ...[
                  const SizedBox(height: 24),
                  _buildSection(
                    context,
                    '문서 링크',
                    task.documentUrl!,
                    isLink: true,
                  ),
                ],
                
                if (task.errorMessage != null) ...[
                  const SizedBox(height: 24),
                  _buildSection(
                    context,
                    '오류 메시지',
                    task.errorMessage!,
                    isError: true,
                  ),
                ],
                
                if (task.result != null) ...[
                  const SizedBox(height: 24),
                  _buildSection(
                    context,
                    '결과',
                    task.result.toString(),
                  ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildSection(
    BuildContext context,
    String title,
    String content, {
    bool isLink = false,
    bool isError = false,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: AppColors.textSecondary,
              ),
        ),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: isError ? AppColors.error.withOpacity(0.1) : AppColors.backgroundCard,
            borderRadius: BorderRadius.circular(12),
            border: isError
                ? Border.all(color: AppColors.error.withOpacity(0.3))
                : null,
          ),
          child: Text(
            content,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: isLink
                      ? AppColors.primary
                      : isError
                          ? AppColors.error
                          : AppColors.textPrimary,
                  decoration: isLink ? TextDecoration.underline : null,
                ),
          ),
        ),
      ],
    );
  }

  String _formatDateTime(DateTime dateTime) {
    return '${dateTime.year}-${dateTime.month.toString().padLeft(2, '0')}-${dateTime.day.toString().padLeft(2, '0')} '
        '${dateTime.hour.toString().padLeft(2, '0')}:${dateTime.minute.toString().padLeft(2, '0')}';
  }
}
