import '../../../../core/network/api_client.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/workspace_model.dart';
import '../models/workspace_member_model.dart';
import '../models/workspace_invitation_model.dart';

/// Repository for workspace operations
class WorkspaceRepository {
  final ApiClient _apiClient;

  WorkspaceRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  // ============================================================================
  // Workspace Management
  // ============================================================================

  /// Get all workspaces for current user
  Future<List<WorkspaceModel>> getWorkspaces({
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final response = await _apiClient.get(
        '/workspaces',
        queryParameters: {
          'page': page,
          'page_size': pageSize,
        },
      );

      final data = response.data;
      if (data is Map && data['workspaces'] != null) {
        final workspaces = data['workspaces'] as List;
        return workspaces
            .map((json) => WorkspaceModel.fromJson(json))
            .toList();
      }

      return [];
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to get workspaces: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Get a single workspace by ID
  Future<WorkspaceModel> getWorkspaceById(String workspaceId) async {
    try {
      final response = await _apiClient.get('/workspaces/$workspaceId');
      return WorkspaceModel.fromJson(response.data);
    } on NotFoundException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to get workspace: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Create a new workspace
  Future<WorkspaceModel> createWorkspace({
    required String name,
    String? description,
    int maxMembers = 10,
  }) async {
    try {
      final response = await _apiClient.post(
        '/workspaces',
        data: {
          'name': name,
          if (description != null) 'description': description,
          'max_members': maxMembers,
        },
      );

      return WorkspaceModel.fromJson(response.data);
    } on ValidationException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to create workspace: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Update workspace
  Future<WorkspaceModel> updateWorkspace(
    String workspaceId, {
    String? name,
    String? description,
    bool? isActive,
    int? maxMembers,
  }) async {
    try {
      final response = await _apiClient.patch(
        '/workspaces/$workspaceId',
        data: {
          if (name != null) 'name': name,
          if (description != null) 'description': description,
          if (isActive != null) 'is_active': isActive,
          if (maxMembers != null) 'max_members': maxMembers,
        },
      );

      return WorkspaceModel.fromJson(response.data);
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to update workspace: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Delete workspace
  Future<void> deleteWorkspace(String workspaceId) async {
    try {
      await _apiClient.delete('/workspaces/$workspaceId');
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to delete workspace: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  // ============================================================================
  // Member Management
  // ============================================================================

  /// Get workspace members
  Future<List<WorkspaceMemberModel>> getWorkspaceMembers(
    String workspaceId, {
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final response = await _apiClient.get(
        '/workspaces/$workspaceId/members',
        queryParameters: {
          'page': page,
          'page_size': pageSize,
        },
      );

      final data = response.data;
      if (data is Map && data['members'] != null) {
        final members = data['members'] as List;
        return members
            .map((json) => WorkspaceMemberModel.fromJson(json))
            .toList();
      }

      return [];
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to get workspace members: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Add member to workspace (direct add, requires ADMIN)
  Future<WorkspaceMemberModel> addWorkspaceMember(
    String workspaceId, {
    required String userId,
    required MemberRole role,
  }) async {
    try {
      final response = await _apiClient.post(
        '/workspaces/$workspaceId/members',
        data: {
          'user_id': userId,
          'role': role.name,
        },
      );

      return WorkspaceMemberModel.fromJson(response.data);
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } on ValidationException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to add workspace member: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Update member role
  Future<WorkspaceMemberModel> updateMemberRole(
    String workspaceId,
    String userId, {
    required MemberRole role,
  }) async {
    try {
      final response = await _apiClient.patch(
        '/workspaces/$workspaceId/members/$userId',
        data: {
          'role': role.name,
        },
      );

      return WorkspaceMemberModel.fromJson(response.data);
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } on ValidationException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to update member role: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Remove member from workspace
  Future<void> removeMember(
    String workspaceId,
    String userId,
  ) async {
    try {
      await _apiClient.delete('/workspaces/$workspaceId/members/$userId');
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to remove member: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  // ============================================================================
  // Invitation Management
  // ============================================================================

  /// Create workspace invitation
  Future<WorkspaceInvitationModel> createInvitation(
    String workspaceId, {
    required String inviteeEmail,
    required MemberRole role,
  }) async {
    try {
      final response = await _apiClient.post(
        '/workspaces/$workspaceId/invitations',
        data: {
          'invitee_email': inviteeEmail,
          'role': role.name,
        },
      );

      return WorkspaceInvitationModel.fromJson(response.data);
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } on ValidationException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to create invitation: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Get workspace invitations
  Future<List<WorkspaceInvitationModel>> getWorkspaceInvitations(
    String workspaceId, {
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final response = await _apiClient.get(
        '/workspaces/$workspaceId/invitations',
        queryParameters: {
          'page': page,
          'page_size': pageSize,
        },
      );

      final data = response.data;
      if (data is Map && data['invitations'] != null) {
        final invitations = data['invitations'] as List;
        return invitations
            .map((json) => WorkspaceInvitationModel.fromJson(json))
            .toList();
      }

      return [];
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to get invitations: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Accept workspace invitation
  Future<WorkspaceMemberModel> acceptInvitation(String token) async {
    try {
      final response = await _apiClient.post(
        '/workspaces/invitations/accept',
        data: {
          'token': token,
        },
      );

      final data = response.data;
      if (data is Map && data['member'] != null) {
        return WorkspaceMemberModel.fromJson(data['member']);
      }

      throw AppException(
        message: 'Invalid invitation response',
      );
    } on NotFoundException {
      rethrow;
    } on ForbiddenException {
      rethrow;
    } on ValidationException {
      rethrow;
    } catch (e, stackTrace) {
      throw AppException(
        message: 'Failed to accept invitation: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }
}
