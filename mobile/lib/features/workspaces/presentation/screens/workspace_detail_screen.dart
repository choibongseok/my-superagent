import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/workspace_provider.dart';
import 'workspace_members_screen.dart';

/// Workspace detail screen
class WorkspaceDetailScreen extends ConsumerStatefulWidget {
  final String workspaceId;

  const WorkspaceDetailScreen({
    super.key,
    required this.workspaceId,
  });

  @override
  ConsumerState<WorkspaceDetailScreen> createState() =>
      _WorkspaceDetailScreenState();
}

class _WorkspaceDetailScreenState
    extends ConsumerState<WorkspaceDetailScreen> {
  @override
  void initState() {
    super.initState();
    _loadWorkspace();
  }

  Future<void> _loadWorkspace() async {
    final workspace = await ref
        .read(workspacesProvider.notifier)
        .getWorkspaceById(widget.workspaceId);
    if (workspace != null) {
      ref.read(selectedWorkspaceProvider.notifier).state = workspace;
    }
  }

  @override
  Widget build(BuildContext context) {
    final workspace = ref.watch(selectedWorkspaceProvider);

    if (workspace == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Workspace')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(workspace.name),
        actions: [
          IconButton(
            icon: const Icon(Icons.edit),
            onPressed: () => _showEditDialog(context, workspace),
          ),
          PopupMenuButton(
            itemBuilder: (context) => [
              const PopupMenuItem(
                value: 'delete',
                child: Text('Delete Workspace'),
              ),
            ],
            onSelected: (value) {
              if (value == 'delete') {
                _confirmDelete(context);
              }
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildInfoCard(workspace),
            const SizedBox(height: 16),
            _buildMembersSection(workspace),
            const SizedBox(height: 16),
            _buildActionsSection(workspace),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoCard(workspace) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              workspace.name,
              style: const TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            if (workspace.description != null) ...[
              const SizedBox(height: 8),
              Text(
                workspace.description,
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey[600],
                ),
              ),
            ],
            const SizedBox(height: 16),
            Row(
              children: [
                _buildInfoChip(
                  Icons.people,
                  '${workspace.memberCount}/${workspace.maxMembers} Members',
                ),
                const SizedBox(width: 8),
                if (!workspace.isActive)
                  _buildInfoChip(
                    Icons.cancel,
                    'Inactive',
                    color: Colors.red,
                  ),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(
              value: workspace.capacityPercentage / 100,
              backgroundColor: Colors.grey[200],
              valueColor: AlwaysStoppedAnimation<Color>(
                workspace.isAtCapacity ? Colors.red : Colors.blue,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '${workspace.capacityPercentage.toStringAsFixed(0)}% capacity',
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey[600],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoChip(IconData icon, String label, {Color? color}) {
    return Chip(
      avatar: Icon(icon, size: 16),
      label: Text(
        label,
        style: const TextStyle(fontSize: 12),
      ),
      backgroundColor: color?.withOpacity(0.1),
    );
  }

  Widget _buildMembersSection(workspace) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.people),
        title: const Text('Members'),
        subtitle: Text('${workspace.memberCount} members'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => _navigateToMembers(context),
      ),
    );
  }

  Widget _buildActionsSection(workspace) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ElevatedButton.icon(
          onPressed: () => _navigateToMembers(context),
          icon: const Icon(Icons.person_add),
          label: const Text('Manage Members'),
        ),
      ],
    );
  }

  void _navigateToMembers(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) =>
            WorkspaceMembersScreen(workspaceId: widget.workspaceId),
      ),
    );
  }

  void _showEditDialog(BuildContext context, workspace) {
    final nameController = TextEditingController(text: workspace.name);
    final descController =
        TextEditingController(text: workspace.description ?? '');
    final maxMembersController =
        TextEditingController(text: workspace.maxMembers.toString());

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Edit Workspace'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            TextField(
              controller: descController,
              decoration: const InputDecoration(labelText: 'Description'),
              maxLines: 3,
            ),
            TextField(
              controller: maxMembersController,
              decoration: const InputDecoration(labelText: 'Max Members'),
              keyboardType: TextInputType.number,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () async {
              final success =
                  await ref.read(workspacesProvider.notifier).updateWorkspace(
                        widget.workspaceId,
                        name: nameController.text,
                        description: descController.text,
                        maxMembers: int.parse(maxMembersController.text),
                      );
              if (context.mounted) {
                Navigator.pop(context);
                if (success) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Workspace updated')),
                  );
                  _loadWorkspace();
                }
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  void _confirmDelete(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Workspace'),
        content: const Text(
          'Are you sure you want to delete this workspace? This action cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () async {
              final success = await ref
                  .read(workspacesProvider.notifier)
                  .deleteWorkspace(widget.workspaceId);
              if (context.mounted) {
                Navigator.pop(context); // Close dialog
                Navigator.pop(context); // Close detail screen
                if (success) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Workspace deleted')),
                  );
                }
              }
            },
            child: const Text(
              'Delete',
              style: TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );
  }
}
