import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/models/user_model.dart';
import '../../data/repositories/auth_repository_provider.dart';
import '../../../../core/errors/app_exception.dart';

/// Auth state
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
  }) {
    return AuthState(
      user: user ?? this.user,
      isLoading: isLoading ?? this.isLoading,
      error: error,
      isGuest: isGuest ?? this.isGuest,
    );
  }

  AuthState clearError() {
    return AuthState(
      user: user,
      isLoading: isLoading,
      error: null,
      isGuest: isGuest,
    );
  }

  AuthState setLoading(bool loading) {
    return AuthState(
      user: user,
      isLoading: loading,
      error: null,
      isGuest: isGuest,
    );
  }
}

/// Auth state notifier
class AuthNotifier extends StateNotifier<AuthState> {
  final Ref _ref;

  AuthNotifier(this._ref) : super(const AuthState()) {
    // Auto-initialize on creation
    _initialize();
  }

  /// Initialize auth state (check if user is already signed in)
  Future<void> _initialize() async {
    state = state.setLoading(true);

    try {
      final authRepo = _ref.read(authRepositoryProvider);
      final isSignedIn = await authRepo.isSignedIn();

      if (isSignedIn) {
        final user = await authRepo.getCurrentUser();
        if (user != null) {
          state = AuthState(
            user: user,
            isLoading: false,
            isGuest: user.isGuest,
          );
          return;
        }
      }

      state = const AuthState(isLoading: false);
    } catch (e) {
      print('Auth initialization error: $e');
      state = const AuthState(isLoading: false);
    }
  }

  /// Sign in with Google
  Future<bool> signInWithGoogle() async {
    state = state.setLoading(true);

    try {
      final authRepo = _ref.read(authRepositoryProvider);
      final user = await authRepo.signInWithGoogle();

      state = AuthState(
        user: user,
        isLoading: false,
        isGuest: false,
      );

      return true;
    } on AuthException catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.message,
      );
      return false;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: 'Google 로그인에 실패했습니다: $e',
      );
      return false;
    }
  }

  /// Sign in as guest
  Future<bool> signInAsGuest() async {
    state = state.setLoading(true);

    try {
      final authRepo = _ref.read(authRepositoryProvider);
      final user = await authRepo.signInAsGuest();

      state = AuthState(
        user: user,
        isLoading: false,
        isGuest: true,
      );

      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: '게스트 로그인에 실패했습니다: $e',
      );
      return false;
    }
  }

  /// Sign out
  Future<void> signOut() async {
    state = state.setLoading(true);

    try {
      final authRepo = _ref.read(authRepositoryProvider);
      await authRepo.signOut();

      state = const AuthState(isLoading: false);
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: '로그아웃에 실패했습니다: $e',
      );
    }
  }

  /// Clear error
  void clearError() {
    state = state.clearError();
  }

  /// Refresh current user
  Future<void> refreshUser() async {
    try {
      final authRepo = _ref.read(authRepositoryProvider);
      final user = await authRepo.getCurrentUser();

      if (user != null) {
        state = AuthState(
          user: user,
          isLoading: false,
          isGuest: user.isGuest,
        );
      }
    } catch (e) {
      print('Refresh user error: $e');
    }
  }
}

/// Auth provider
final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(ref);
});

/// Current user provider (convenience)
final currentUserProvider = Provider<UserModel?>((ref) {
  return ref.watch(authProvider).user;
});

/// Is authenticated provider (convenience)
final isAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(authProvider).isAuthenticated;
});

/// Is guest provider (convenience)
final isGuestProvider = Provider<bool>((ref) {
  return ref.watch(authProvider).isGuest;
});
