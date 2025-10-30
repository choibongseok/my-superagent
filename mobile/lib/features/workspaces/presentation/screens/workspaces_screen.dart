import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/workspace_provider.dart';
import 'workspace_detail_screen.dart';
import 'create_workspace_screen.dart';

/// Workspaces list screen
class WorkspacesScreen extends ConsumerStatefulWidget {
  const WorkspacesScreen({super.key});

  @override
  ConsumerState<WorkspacesScreen> createState() => _WorkspacesScreenState();
}

class _WorkspacesScreenState extends ConsumerState<WorkspacesScreen> {
  @override
  void initState() {
    super.initState();
    // Load workspaces on init
    Future.microtask(() {
      ref.read(workspacesProvider.notifier).loadWorkspaces();
    });
  }

  @override
  Widget build(BuildContext context) {
    final workspacesState = ref.watch(workspacesProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Workspaces'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ref.read(workspacesProvider.notifier).loadWorkspaces(
                    forceRefresh: true,
                  );
            },
          ),
        ],
      ),
      body: _buildBody(workspacesState),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _navigateToCreateWorkspace(context),
        child: const Icon(Icons.add),
      ),
    );
  }

  Widget _buildBody(WorkspacesState state) {
    if (state.isLoading && state.workspaces.isEmpty) {
      return const Center(
        child: CircularProgressIndicator(),
      );
    }

    if (state.error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 48,
              color: Colors.red[300],
            ),
            const SizedBox(height: 16),
            Text(
              state.error!,
              style: const TextStyle(fontSize: 16),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () {
                ref.read(workspacesProvider.notifier).loadWorkspaces(
                      forceRefresh: true,
                    );
              },
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (state.workspaces.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.workspace_premium,
              size: 64,
              color: Colors.grey[400],
            ),
            const SizedBox(height: 16),
            Text(
              'No workspaces yet',
              style: TextStyle(
                fontSize: 18,
                color: Colors.grey[600],
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Create your first workspace to get started',
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey[500],
              ),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: () async {
        await ref.read(workspacesProvider.notifier).loadWorkspaces(
              forceRefresh: true,
            );
      },
      child: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: state.workspaces.length,
        itemBuilder: (context, index) {
          final workspace = state.workspaces[index];
          return Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: ListTile(
              leading: CircleAvatar(
                child: Text(
                  workspace.name[0].toUpperCase(),
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
              ),
              title: Text(
                workspace.name,
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (workspace.description != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      workspace.description!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(
                        Icons.people,
                        size: 16,
                        color: Colors.grey[600],
                      ),
                      const SizedBox(width: 4),
                      Text(
                        '${workspace.memberCount}/${workspace.maxMembers} members',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.grey[600],
                        ),
                      ),
                      const SizedBox(width: 12),
                      if (!workspace.isActive)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.grey[300],
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Text(
                            'Inactive',
                            style: TextStyle(fontSize: 10),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
              trailing: workspace.isAtCapacity
                  ? Chip(
                      label: const Text(
                        'Full',
                        style: TextStyle(fontSize: 10),
                      ),
                      backgroundColor: Colors.orange[100],
                    )
                  : const Icon(Icons.chevron_right),
              onTap: () => _navigateToWorkspaceDetail(context, workspace.id),
            ),
          );
        },
      ),
    );
  }

  void _navigateToWorkspaceDetail(BuildContext context, String workspaceId) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => WorkspaceDetailScreen(workspaceId: workspaceId),
      ),
    );
  }

  void _navigateToCreateWorkspace(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => const CreateWorkspaceScreen(),
      ),
    );
  }
}
