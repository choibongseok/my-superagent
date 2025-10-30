import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/models/workspace_model.dart';
import '../../data/models/workspace_member_model.dart';
import '../../data/models/workspace_invitation_model.dart';
import '../../data/repositories/workspace_repository.dart';
import '../../../../core/errors/app_exception.dart';

// ============================================================================
// Providers
// ============================================================================

/// Workspace repository provider
final workspaceRepositoryProvider = Provider<WorkspaceRepository>((ref) {
  throw UnimplementedError('WorkspaceRepository must be overridden');
});

/// Workspaces list provider
final workspacesProvider =
    StateNotifierProvider<WorkspacesNotifier, WorkspacesState>((ref) {
  return WorkspacesNotifier(ref);
});

/// Selected workspace provider
final selectedWorkspaceProvider = StateProvider<WorkspaceModel?>((ref) => null);

/// Workspace members provider
final workspaceMembersProvider = StateNotifierProvider.family<
    WorkspaceMembersNotifier, WorkspaceMembersState, String>((ref, workspaceId) {
  return WorkspaceMembersNotifier(ref, workspaceId);
});

/// Workspace invitations provider
final workspaceInvitationsProvider = StateNotifierProvider.family<
    WorkspaceInvitationsNotifier,
    WorkspaceInvitationsState,
    String>((ref, workspaceId) {
  return WorkspaceInvitationsNotifier(ref, workspaceId);
});

// ============================================================================
// Workspaces State & Notifier
// ============================================================================

class WorkspacesState {
  final List<WorkspaceModel> workspaces;
  final bool isLoading;
  final String? error;

  const WorkspacesState({
    this.workspaces = const [],
    this.isLoading = false,
    this.error,
  });

  WorkspacesState copyWith({
    List<WorkspaceModel>? workspaces,
    bool? isLoading,
    String? error,
  }) {
    return WorkspacesState(
      workspaces: workspaces ?? this.workspaces,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  WorkspacesState setLoading(bool loading) {
    return WorkspacesState(
      workspaces: workspaces,
      isLoading: loading,
      error: null,
    );
  }

  WorkspacesState setError(String error) {
    return WorkspacesState(
      workspaces: workspaces,
      isLoading: false,
      error: error,
    );
  }

  WorkspacesState clearError() {
    return copyWith(error: null);
  }
}

class WorkspacesNotifier extends StateNotifier<WorkspacesState> {
  final Ref _ref;

  WorkspacesNotifier(this._ref) : super(const WorkspacesState());

  WorkspaceRepository get _repository =>
      _ref.read(workspaceRepositoryProvider);

  /// Load all workspaces
  Future<void> loadWorkspaces({bool forceRefresh = false}) async {
    if (state.isLoading && !forceRefresh) return;

    state = state.setLoading(true);

    try {
      final workspaces = await _repository.getWorkspaces();
      state = state.copyWith(
        workspaces: workspaces,
        isLoading: false,
        error: null,
      );
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
    } catch (e) {
      state = state.setError('Failed to load workspaces: $e');
    }
  }

  /// Create new workspace
  Future<WorkspaceModel?> createWorkspace({
    required String name,
    String? description,
    int maxMembers = 10,
  }) async {
    try {
      final workspace = await _repository.createWorkspace(
        name: name,
        description: description,
        maxMembers: maxMembers,
      );

      // Add to list
      state = state.copyWith(
        workspaces: [...state.workspaces, workspace],
      );

      return workspace;
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
      return null;
    } catch (e) {
      state = state.setError('Failed to create workspace: $e');
      return null;
    }
  }

  /// Update workspace
  Future<bool> updateWorkspace(
    String workspaceId, {
    String? name,
    String? description,
    bool? isActive,
    int? maxMembers,
  }) async {
    try {
      final updatedWorkspace = await _repository.updateWorkspace(
        workspaceId,
        name: name,
        description: description,
        isActive: isActive,
        maxMembers: maxMembers,
      );

      // Update in list
      state = state.copyWith(
        workspaces: state.workspaces
            .map((w) => w.id == workspaceId ? updatedWorkspace : w)
            .toList(),
      );

      // Update selected if needed
      final selected = _ref.read(selectedWorkspaceProvider);
      if (selected?.id == workspaceId) {
        _ref.read(selectedWorkspaceProvider.notifier).state = updatedWorkspace;
      }

      return true;
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
      return false;
    } catch (e) {
      state = state.setError('Failed to update workspace: $e');
      return false;
    }
  }

  /// Delete workspace
  Future<bool> deleteWorkspace(String workspaceId) async {
    try {
      await _repository.deleteWorkspace(workspaceId);

      // Remove from list
      state = state.copyWith(
        workspaces: state.workspaces.where((w) => w.id != workspaceId).toList(),
      );

      // Clear selected if needed
      final selected = _ref.read(selectedWorkspaceProvider);
      if (selected?.id == workspaceId) {
        _ref.read(selectedWorkspaceProvider.notifier).state = null;
      }

      return true;
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
      return false;
    } catch (e) {
      state = state.setError('Failed to delete workspace: $e');
      return false;
    }
  }

  /// Get workspace by ID
  Future<WorkspaceModel?> getWorkspaceById(String workspaceId) async {
    try {
      return await _repository.getWorkspaceById(workspaceId);
    } catch (e) {
      return null;
    }
  }

  /// Clear error
  void clearError() {
    state = state.clearError();
  }
}

// ============================================================================
// Workspace Members State & Notifier
// ============================================================================

class WorkspaceMembersState {
  final List<WorkspaceMemberModel> members;
  final bool isLoading;
  final String? error;

  const WorkspaceMembersState({
    this.members = const [],
    this.isLoading = false,
    this.error,
  });

  WorkspaceMembersState copyWith({
    List<WorkspaceMemberModel>? members,
    bool? isLoading,
    String? error,
  }) {
    return WorkspaceMembersState(
      members: members ?? this.members,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  WorkspaceMembersState setLoading(bool loading) {
    return WorkspaceMembersState(
      members: members,
      isLoading: loading,
      error: null,
    );
  }

  WorkspaceMembersState setError(String error) {
    return WorkspaceMembersState(
      members: members,
      isLoading: false,
      error: error,
    );
  }
}

class WorkspaceMembersNotifier extends StateNotifier<WorkspaceMembersState> {
  final Ref _ref;
  final String _workspaceId;

  WorkspaceMembersNotifier(this._ref, this._workspaceId)
      : super(const WorkspaceMembersState());

  WorkspaceRepository get _repository =>
      _ref.read(workspaceRepositoryProvider);

  /// Load workspace members
  Future<void> loadMembers({bool forceRefresh = false}) async {
    if (state.isLoading && !forceRefresh) return;

    state = state.setLoading(true);

    try {
      final members = await _repository.getWorkspaceMembers(_workspaceId);
      state = state.copyWith(
        members: members,
        isLoading: false,
        error: null,
      );
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
    } catch (e) {
      state = state.setError('Failed to load members: $e');
    }
  }

  /// Update member role
  Future<bool> updateMemberRole(
    String userId,
    MemberRole role,
  ) async {
    try {
      final updatedMember = await _repository.updateMemberRole(
        _workspaceId,
        userId,
        role: role,
      );

      // Update in list
      state = state.copyWith(
        members: state.members
            .map((m) => m.userId == userId ? updatedMember : m)
            .toList(),
      );

      return true;
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
      return false;
    } catch (e) {
      state = state.setError('Failed to update member role: $e');
      return false;
    }
  }

  /// Remove member
  Future<bool> removeMember(String userId) async {
    try {
      await _repository.removeMember(_workspaceId, userId);

      // Remove from list
      state = state.copyWith(
        members: state.members.where((m) => m.userId != userId).toList(),
      );

      return true;
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
      return false;
    } catch (e) {
      state = state.setError('Failed to remove member: $e');
      return false;
    }
  }

  /// Get member by user ID
  WorkspaceMemberModel? getMemberByUserId(String userId) {
    return state.members.firstWhere(
      (m) => m.userId == userId,
      orElse: () => throw NotFoundException(message: 'Member not found'),
    );
  }
}

// ============================================================================
// Workspace Invitations State & Notifier
// ============================================================================

class WorkspaceInvitationsState {
  final List<WorkspaceInvitationModel> invitations;
  final bool isLoading;
  final String? error;

  const WorkspaceInvitationsState({
    this.invitations = const [],
    this.isLoading = false,
    this.error,
  });

  WorkspaceInvitationsState copyWith({
    List<WorkspaceInvitationModel>? invitations,
    bool? isLoading,
    String? error,
  }) {
    return WorkspaceInvitationsState(
      invitations: invitations ?? this.invitations,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }

  WorkspaceInvitationsState setLoading(bool loading) {
    return WorkspaceInvitationsState(
      invitations: invitations,
      isLoading: loading,
      error: null,
    );
  }

  WorkspaceInvitationsState setError(String error) {
    return WorkspaceInvitationsState(
      invitations: invitations,
      isLoading: false,
      error: error,
    );
  }
}

class WorkspaceInvitationsNotifier
    extends StateNotifier<WorkspaceInvitationsState> {
  final Ref _ref;
  final String _workspaceId;

  WorkspaceInvitationsNotifier(this._ref, this._workspaceId)
      : super(const WorkspaceInvitationsState());

  WorkspaceRepository get _repository =>
      _ref.read(workspaceRepositoryProvider);

  /// Load workspace invitations
  Future<void> loadInvitations({bool forceRefresh = false}) async {
    if (state.isLoading && !forceRefresh) return;

    state = state.setLoading(true);

    try {
      final invitations =
          await _repository.getWorkspaceInvitations(_workspaceId);
      state = state.copyWith(
        invitations: invitations,
        isLoading: false,
        error: null,
      );
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
    } catch (e) {
      state = state.setError('Failed to load invitations: $e');
    }
  }

  /// Create invitation
  Future<WorkspaceInvitationModel?> createInvitation({
    required String inviteeEmail,
    required MemberRole role,
  }) async {
    try {
      final invitation = await _repository.createInvitation(
        _workspaceId,
        inviteeEmail: inviteeEmail,
        role: role,
      );

      // Add to list
      state = state.copyWith(
        invitations: [...state.invitations, invitation],
      );

      return invitation;
    } on AppException catch (e) {
      state = state.setError(e.userMessage);
      return null;
    } catch (e) {
      state = state.setError('Failed to create invitation: $e');
      return null;
    }
  }

  /// Accept invitation (global function)
  static Future<WorkspaceMemberModel?> acceptInvitation(
    Ref ref,
    String token,
  ) async {
    try {
      final repository = ref.read(workspaceRepositoryProvider);
      return await repository.acceptInvitation(token);
    } catch (e) {
      return null;
    }
  }
}
