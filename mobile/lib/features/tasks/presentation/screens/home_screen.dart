import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../shared/themes/app_colors.dart';
import '../../../../core/constants/app_constants.dart';
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
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.backgroundDark,
      body: SafeArea(
        child: Column(
          children: [
            _buildTopBar(),
            Expanded(
              child: SingleChildScrollView(
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
                      _buildRecentTasks(),
                      const SizedBox(height: 40),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar() {
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
              // TODO: Open drawer
            },
            icon: const Icon(
              Icons.menu,
              color: AppColors.textPrimary,
            ),
          ),
          // Profile
          GestureDetector(
            onTap: () {
              // TODO: Navigate to profile
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
    );
  }

  Widget _buildRecentTasks() {
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
            TextButton(
              onPressed: () {
                // TODO: View all tasks
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
        // Task cards
        ListView.separated(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: 3, // TODO: Use actual task count
          separatorBuilder: (context, index) => const SizedBox(height: 16),
          itemBuilder: (context, index) {
            return TaskCard(
              title: '샘플 작업 ${index + 1}',
              description: 'AI가 생성한 문서입니다',
              status: index == 0
                  ? AppConstants.taskStatusCompleted
                  : index == 1
                      ? AppConstants.taskStatusInProgress
                      : AppConstants.taskStatusPending,
              agentType: index == 0
                  ? AppConstants.agentDocs
                  : index == 1
                      ? AppConstants.agentSheets
                      : AppConstants.agentSlides,
              createdAt: DateTime.now().subtract(Duration(hours: index + 1)),
              onTap: () {
                // TODO: Navigate to task detail
              },
            );
          },
        ),
      ],
    );
  }
}
