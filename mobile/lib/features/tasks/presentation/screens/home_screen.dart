import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../shared/themes/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../auth/presentation/providers/auth_provider.dart';
import '../providers/task_provider.dart';
import '../widgets/search_input.dart';
import '../widgets/agent_grid.dart';
import '../widgets/task_card.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  @override
  void initState() {
    super.initState();
    // Load tasks on mount
    Future.microtask(() {
      ref.read(tasksProvider.notifier).loadTasks();
    });
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final tasksState = ref.watch(tasksProvider);

    return Scaffold(
      backgroundColor: AppColors.backgroundDark,
      body: SafeArea(
        child: Column(
          children: [
            _buildTopBar(authState.user?.name ?? 'Guest'),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async {
                  await ref.read(tasksProvider.notifier).loadTasks(refresh: true);
                },
                backgroundColor: AppColors.backgroundCard,
                color: AppColors.primary,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppConstants.paddingLarge,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 60),
                        // Hero title
                        Text(
                          'AgentHQ 슈퍼 에이전트',
                          style: Theme.of(context).textTheme.displayLarge,
                        ),
                        const SizedBox(height: 40),
                        // Search input
                        const SearchInput(),
                        const SizedBox(height: 60),
                        // Agent grid
                        const AgentGrid(),
                        const SizedBox(height: 60),
                        // Recent tasks
                        _buildRecentTasks(tasksState),
                        const SizedBox(height: 40),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar(String userName) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppConstants.paddingLarge,
        vertical: AppConstants.paddingDefault,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Menu button
          IconButton(
            onPressed: () {
              _showDrawer();
            },
            icon: const Icon(
              Icons.menu,
              color: AppColors.textPrimary,
            ),
          ),
          // User info
          Row(
            children: [
              Text(
                userName,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: AppColors.textSecondary,
                    ),
              ),
              const SizedBox(width: 12),
              GestureDetector(
                onTap: () {
                  context.push('/profile');
                },
                child: CircleAvatar(
                  radius: 20,
                  backgroundColor: AppColors.primary,
                  child: const Icon(
                    Icons.person,
                    color: Colors.white,
                    size: 24,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRecentTasks(TasksState tasksState) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Section header
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '최근 작업',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            if (tasksState.tasks.isNotEmpty)
              TextButton(
                onPressed: () {
                  // TODO: Navigate to all tasks screen
                },
                child: Text(
                  '전체보기',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        color: AppColors.primary,
                      ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 16),
        
        // Loading state
        if (tasksState.isLoading)
          const Center(
            child: Padding(
              padding: EdgeInsets.all(32.0),
              child: CircularProgressIndicator(
                color: AppColors.primary,
              ),
            ),
          )
        
        // Error state
        else if (tasksState.error != null)
          Center(
            child: Padding(
              padding: const EdgeInsets.all(32.0),
              child: Column(
                children: [
                  Icon(
                    Icons.error_outline,
                    size: 48,
                    color: AppColors.error,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    tasksState.error!,
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: AppColors.textSecondary,
                        ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: () {
                      ref.read(tasksProvider.notifier).loadTasks(refresh: true);
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.primary,
                    ),
                    child: const Text('다시 시도'),
                  ),
                ],
              ),
            ),
          )
        
        // Empty state
        else if (tasksState.tasks.isEmpty)
          Center(
            child: Padding(
              padding: const EdgeInsets.all(32.0),
              child: Column(
                children: [
                  Icon(
                    Icons.inbox_outlined,
                    size: 64,
                    color: AppColors.textTertiary,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    '아직 작업이 없습니다',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          color: AppColors.textSecondary,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '위에서 AI 에이전트를 선택하고\n새 작업을 시작해보세요',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: AppColors.textTertiary,
                        ),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          )
        
        // Task list
        else
          ListView.separated(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: tasksState.tasks.length > 5 ? 5 : tasksState.tasks.length,
            separatorBuilder: (context, index) => const SizedBox(height: 16),
            itemBuilder: (context, index) {
              final task = tasksState.tasks[index];
              return TaskCard(
                title: task.prompt,
                description: _getTaskDescription(task.status),
                status: task.status,
                agentType: task.taskType,
                createdAt: task.createdAt,
                onTap: () {
                  context.push('/tasks/${task.id}');
                },
              );
            },
          ),
      ],
    );
  }

  String _getTaskDescription(String status) {
    switch (status) {
      case AppConstants.taskStatusCompleted:
        return 'AI가 작업을 완료했습니다';
      case AppConstants.taskStatusInProgress:
        return 'AI가 작업 중입니다...';
      case AppConstants.taskStatusPending:
        return '대기 중입니다...';
      case AppConstants.taskStatusFailed:
        return '작업이 실패했습니다';
      default:
        return '알 수 없는 상태';
    }
  }

  void _showDrawer() {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.backgroundCard,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => Container(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.person, color: AppColors.primary),
              title: const Text('프로필'),
              onTap: () {
                Navigator.pop(context);
                context.push('/profile');
              },
            ),
            ListTile(
              leading: const Icon(Icons.logout, color: AppColors.error),
              title: const Text('로그아웃'),
              onTap: () async {
                Navigator.pop(context);
                await ref.read(authProvider.notifier).signOut();
                if (mounted) {
                  context.go('/login');
                }
              },
            ),
          ],
        ),
      ),
    );
  }
}
