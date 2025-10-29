import 'package:google_sign_in/google_sign_in.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../../core/network/api_client.dart';
import '../../../../core/constants/app_constants.dart';
import '../models/user_model.dart';

/// Repository for authentication operations
class AuthRepository {
  final ApiClient _apiClient;
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();
  final GoogleSignIn _googleSignIn = GoogleSignIn(
    scopes: AppConstants.googleScopes,
  );

  AuthRepository(this._apiClient);

  /// Sign in with Google OAuth
  Future<UserModel?> signInWithGoogle() async {
    try {
      // 1. Google Sign-In
      final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
      if (googleUser == null) {
        // User canceled sign-in
        return null;
      }

      // 2. Get authentication tokens
      final GoogleSignInAuthentication googleAuth = await googleUser.authentication;

      // 3. Exchange tokens with backend
      final response = await _apiClient.post(
        '/auth/google/mobile',
        data: {
          'id_token': googleAuth.idToken,
          'access_token': googleAuth.accessToken,
        },
      );

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;

        // 4. Store auth tokens securely
        await _secureStorage.write(
          key: AppConstants.keyAccessToken,
          value: data['access_token'] as String,
        );
        await _secureStorage.write(
          key: AppConstants.keyRefreshToken,
          value: data['refresh_token'] as String,
        );

        // 5. Parse and return user data
        final user = UserModel.fromJson(data['user'] as Map<String, dynamic>);

        // Store user info
        await _secureStorage.write(key: AppConstants.keyUserId, value: user.id);
        await _secureStorage.write(key: AppConstants.keyUserEmail, value: user.email);
        await _secureStorage.write(key: AppConstants.keyUserName, value: user.name);
        if (user.avatarUrl != null) {
          await _secureStorage.write(key: AppConstants.keyUserAvatar, value: user.avatarUrl!);
        }

        return user;
      }

      throw Exception('Authentication failed: ${response.statusCode}');
    } catch (e) {
      print('Sign in error: $e');
      rethrow;
    }
  }

  /// Sign in as guest (no authentication required)
  Future<UserModel> signInAsGuest() async {
    try {
      final response = await _apiClient.post('/auth/guest');

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;

        // Store guest tokens
        await _secureStorage.write(
          key: AppConstants.keyAccessToken,
          value: data['access_token'] as String,
        );

        // Create guest user model
        final user = UserModel.fromJson(data['user'] as Map<String, dynamic>);

        await _secureStorage.write(key: AppConstants.keyUserId, value: user.id);
        await _secureStorage.write(key: AppConstants.keyUserEmail, value: user.email);
        await _secureStorage.write(key: AppConstants.keyUserName, value: user.name);

        return user;
      }

      throw Exception('Guest sign in failed: ${response.statusCode}');
    } catch (e) {
      print('Guest sign in error: $e');
      rethrow;
    }
  }

  /// Sign out
  Future<void> signOut() async {
    try {
      // Sign out from Google
      await _googleSignIn.signOut();

      // Clear local storage
      await _secureStorage.delete(key: AppConstants.keyAccessToken);
      await _secureStorage.delete(key: AppConstants.keyRefreshToken);
      await _secureStorage.delete(key: AppConstants.keyUserId);
      await _secureStorage.delete(key: AppConstants.keyUserEmail);
      await _secureStorage.delete(key: AppConstants.keyUserName);
      await _secureStorage.delete(key: AppConstants.keyUserAvatar);

      // Notify backend (optional, fire-and-forget)
      try {
        await _apiClient.post('/auth/logout');
      } catch (e) {
        // Ignore logout API errors
        print('Logout API error (ignored): $e');
      }
    } catch (e) {
      print('Sign out error: $e');
      rethrow;
    }
  }

  /// Check if user is signed in
  Future<bool> isSignedIn() async {
    final token = await _secureStorage.read(key: AppConstants.keyAccessToken);
    return token != null && token.isNotEmpty;
  }

  /// Get current user from backend
  Future<UserModel?> getCurrentUser() async {
    try {
      final response = await _apiClient.get('/auth/me');

      if (response.statusCode == 200) {
        return UserModel.fromJson(response.data as Map<String, dynamic>);
      }
    } catch (e) {
      print('Get current user error: $e');
    }
    return null;
  }

  /// Get current user from local storage (offline)
  Future<UserModel?> getCurrentUserLocal() async {
    try {
      final userId = await _secureStorage.read(key: AppConstants.keyUserId);
      final userEmail = await _secureStorage.read(key: AppConstants.keyUserEmail);
      final userName = await _secureStorage.read(key: AppConstants.keyUserName);
      final userAvatar = await _secureStorage.read(key: AppConstants.keyUserAvatar);

      if (userId != null && userEmail != null) {
        return UserModel(
          id: userId,
          email: userEmail,
          name: userName ?? userEmail,
          avatarUrl: userAvatar,
          createdAt: DateTime.now(),
        );
      }
    } catch (e) {
      print('Get local user error: $e');
    }
    return null;
  }

  /// Check if user is guest
  Future<bool> isGuest() async {
    final email = await _secureStorage.read(key: AppConstants.keyUserEmail);
    return email != null && email.contains('guest');
  }
}
