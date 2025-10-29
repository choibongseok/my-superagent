import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../../data/models/user_model.dart';
import '../../data/repositories/auth_repository.dart';

// API Client Provider
final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient();
});

// Auth Repository Provider
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return AuthRepository(apiClient);
});

// Auth State
class AuthState {
  final UserModel? user;
  final bool isLoading;
  final String? error;
  final bool isGuest;

  const AuthState({
    this.user,
    this.isLoading = false,
    this.error,
    this.isGuest = false,
  });

  bool get isAuthenticated => user != null;

  AuthState copyWith({
    UserModel? user,
    bool? isLoading,
    String? error,
    bool? isGuest,
    bool clearUser = false,
    bool clearError = false,
  }) {
    return AuthState(
      user: clearUser ? null : (user ?? this.user),
      isLoading: isLoading ?? this.isLoading,
      error: clearError ? null : (error ?? this.error),
      isGuest: isGuest ?? this.isGuest,
    );
  }
}

// Auth State Notifier
class AuthNotifier extends StateNotifier<AuthState> {
  final AuthRepository _authRepository;

  AuthNotifier(this._authRepository) : super(const AuthState()) {
    _init();
  }

  Future<void> _init() async {
    state = state.copyWith(isLoading: true);

    try {
      // Check if user is already signed in
      final isSignedIn = await _authRepository.isSignedIn();

      if (isSignedIn) {
        // Try to get user from backend
        UserModel? user = await _authRepository.getCurrentUser();

        // If backend fails, try local storage
        user ??= await _authRepository.getCurrentUserLocal();

        if (user != null) {
          final isGuest = await _authRepository.isGuest();
          state = state.copyWith(
            user: user,
            isLoading: false,
            isGuest: isGuest,
            clearError: true,
          );
          return;
        }
      }

      state = state.copyWith(isLoading: false, clearError: true);
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: 'Failed to initialize auth: $e',
      );
    }
  }

  /// Sign in with Google OAuth
  Future<bool> signInWithGoogle() async {
    state = state.copyWith(isLoading: true, clearError: true);

    try {
      final user = await _authRepository.signInWithGoogle();

      if (user != null) {
        state = state.copyWith(
          user: user,
          isLoading: false,
          isGuest: false,
          clearError: true,
        );
        return true;
      }

      state = state.copyWith(isLoading: false);
      return false;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: 'Google sign in failed: $e',
      );
      return false;
    }
  }

  /// Sign in as guest
  Future<bool> signInAsGuest() async {
    state = state.copyWith(isLoading: true, clearError: true);

    try {
      final user = await _authRepository.signInAsGuest();

      state = state.copyWith(
        user: user,
        isLoading: false,
        isGuest: true,
        clearError: true,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: 'Guest sign in failed: $e',
      );
      return false;
    }
  }

  /// Sign out
  Future<void> signOut() async {
    state = state.copyWith(isLoading: true, clearError: true);

    try {
      await _authRepository.signOut();

      state = state.copyWith(
        clearUser: true,
        isLoading: false,
        isGuest: false,
        clearError: true,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: 'Sign out failed: $e',
      );
    }
  }

  /// Clear error
  void clearError() {
    state = state.copyWith(clearError: true);
  }
}

// Auth State Provider
final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final authRepository = ref.watch(authRepositoryProvider);
  return AuthNotifier(authRepository);
});
