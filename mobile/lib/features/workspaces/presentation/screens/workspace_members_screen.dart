import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/workspace_provider.dart';
import '../../data/models/workspace_member_model.dart';

/// Workspace members management screen
class WorkspaceMembersScreen extends ConsumerStatefulWidget {
  final String workspaceId;

  const WorkspaceMembersScreen({
    super.key,
    required this.workspaceId,
  });

  @override
  ConsumerState<WorkspaceMembersScreen> createState() =>
      _WorkspaceMembersScreenState();
}

class _WorkspaceMembersScreenState
    extends ConsumerState<WorkspaceMembersScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      ref
          .read(workspaceMembersProvider(widget.workspaceId).notifier)
          .loadMembers();
    });
  }

  @override
  Widget build(BuildContext context) {
    final membersState =
        ref.watch(workspaceMembersProvider(widget.workspaceId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Members'),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_add),
            onPressed: () => _showInviteDialog(context),
          ),
        ],
      ),
      body: _buildBody(membersState),
    );
  }

  Widget _buildBody(WorkspaceMembersState state) {
    if (state.isLoading && state.members.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (state.error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(state.error!),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () {
                ref
                    .read(workspaceMembersProvider(widget.workspaceId).notifier)
                    .loadMembers(forceRefresh: true);
              },
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (state.members.isEmpty) {
      return const Center(
        child: Text('No members yet'),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: state.members.length,
      itemBuilder: (context, index) {
        final member = state.members[index];
        return _buildMemberCard(member);
      },
    );
  }

  Widget _buildMemberCard(WorkspaceMemberModel member) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ListTile(
        leading: CircleAvatar(
          child: Text(member.displayName[0].toUpperCase()),
        ),
        title: Text(member.displayName),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (member.userEmail != null) Text(member.userEmail!),
            const SizedBox(height: 4),
            Chip(
              label: Text(
                member.memberRole.displayName,
                style: const TextStyle(fontSize: 10),
              ),
              visualDensity: VisualDensity.compact,
            ),
          ],
        ),
        trailing: member.isOwner
            ? const Icon(Icons.star, color: Colors.amber)
            : PopupMenuButton(
                itemBuilder: (context) => [
                  if (!member.isAdmin)
                    const PopupMenuItem(
                      value: 'promote',
                      child: Text('Promote to Admin'),
                    ),
                  if (member.isAdmin && !member.isOwner)
                    const PopupMenuItem(
                      value: 'demote',
                      child: Text('Demote to Member'),
                    ),
                  const PopupMenuItem(
                    value: 'remove',
                    child: Text('Remove'),
                  ),
                ],
                onSelected: (value) {
                  if (value == 'promote') {
                    _updateMemberRole(member.userId, MemberRole.admin);
                  } else if (value == 'demote') {
                    _updateMemberRole(member.userId, MemberRole.member);
                  } else if (value == 'remove') {
                    _confirmRemoveMember(context, member);
                  }
                },
              ),
      ),
    );
  }

  Future<void> _updateMemberRole(String userId, MemberRole role) async {
    final success = await ref
        .read(workspaceMembersProvider(widget.workspaceId).notifier)
        .updateMemberRole(userId, role);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            success ? 'Member role updated' : 'Failed to update role',
          ),
        ),
      );
    }
  }

  void _confirmRemoveMember(BuildContext context, WorkspaceMemberModel member) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove Member'),
        content: Text(
          'Are you sure you want to remove ${member.displayName} from this workspace?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () async {
              final success = await ref
                  .read(workspaceMembersProvider(widget.workspaceId).notifier)
                  .removeMember(member.userId);
              if (context.mounted) {
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      success ? 'Member removed' : 'Failed to remove member',
                    ),
                  ),
                );
              }
            },
            child: const Text(
              'Remove',
              style: TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );
  }

  void _showInviteDialog(BuildContext context) {
    final emailController = TextEditingController();
    MemberRole selectedRole = MemberRole.member;

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Invite Member'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: emailController,
                decoration: const InputDecoration(
                  labelText: 'Email',
                  hintText: 'user@example.com',
                ),
                keyboardType: TextInputType.emailAddress,
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<MemberRole>(
                value: selectedRole,
                decoration: const InputDecoration(labelText: 'Role'),
                items: [
                  MemberRole.member,
                  MemberRole.admin,
                  MemberRole.viewer,
                ].map((role) {
                  return DropdownMenuItem(
                    value: role,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(role.displayName),
                        Text(
                          role.description,
                          style: const TextStyle(fontSize: 10),
                        ),
                      ],
                    ),
                  );
                }).toList(),
                onChanged: (value) {
                  if (value != null) {
                    setState(() {
                      selectedRole = value;
                    });
                  }
                },
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
                final invitation = await ref
                    .read(workspaceInvitationsProvider(widget.workspaceId)
                        .notifier)
                    .createInvitation(
                      inviteeEmail: emailController.text.trim(),
                      role: selectedRole,
                    );

                if (context.mounted) {
                  Navigator.pop(context);
                  if (invitation != null) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Invitation sent')),
                    );
                  } else {
                    final error = ref
                        .read(workspaceInvitationsProvider(widget.workspaceId))
                        .error;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(error ?? 'Failed to send invitation'),
                      ),
                    );
                  }
                }
              },
              child: const Text('Send Invitation'),
            ),
          ],
        ),
      ),
    );
  }
}
