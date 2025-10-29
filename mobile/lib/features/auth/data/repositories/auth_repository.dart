import 'package:google_sign_in/google_sign_in.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../../core/network/api_client.dart';
import '../../../../core/errors/app_exception.dart';
import '../models/user_model.dart';

/// Repository for authentication operations
class AuthRepository {
  final ApiClient _apiClient;
  final FlutterSecureStorage _secureStorage;
  final GoogleSignIn _googleSignIn;

  AuthRepository({
    required ApiClient apiClient,
    FlutterSecureStorage? secureStorage,
    GoogleSignIn? googleSignIn,
  })  : _apiClient = apiClient,
        _secureStorage = secureStorage ?? const FlutterSecureStorage(),
        _googleSignIn = googleSignIn ??
            GoogleSignIn(
              scopes: [
                'email',
                'profile',
              ],
            );

  /// Sign in with Google
  Future<UserModel> signInWithGoogle() async {
    try {
      // 1. Trigger Google Sign-In flow
      final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
      
      if (googleUser == null) {
        throw const AuthException(message: 'Google Sign-In cancelled');
      }

      // 2. Get authentication tokens
      final GoogleSignInAuthentication googleAuth = await googleUser.authentication;

      if (googleAuth.idToken == null) {
        throw const AuthException(message: 'Failed to get Google ID token');
      }

      // 3. Send tokens to backend for verification
      final response = await _apiClient.post(
        '/auth/google/mobile',
        data: {
          'id_token': googleAuth.idToken,
          'access_token': googleAuth.accessToken,
        },
      );

      // 4. Store backend tokens securely
      final data = response.data;
      if (data['access_token'] != null) {
        await _secureStorage.write(
          key: 'access_token',
          value: data['access_token'],
        );
      }
      if (data['refresh_token'] != null) {
        await _secureStorage.write(
          key: 'refresh_token',
          value: data['refresh_token'],
        );
      }

      // 5. Parse and return user
      final user = UserModel.fromJson(data['user']);
      await _cacheUser(user);
      return user;
    } on AuthException {
      rethrow;
    } catch (e, stackTrace) {
      throw AuthException(
        message: 'Google Sign-In failed: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Sign in as guest (no authentication)
  Future<UserModel> signInAsGuest() async {
    try {
      // Create guest user
      final guestUser = UserModel.guest();

      // Generate a guest session token from backend
      final response = await _apiClient.post(
        '/auth/guest',
        data: {
          'device_id': guestUser.id,
          'name': guestUser.name,
        },
      );

      final data = response.data;
      
      // Store guest token
      if (data['access_token'] != null) {
        await _secureStorage.write(
          key: 'access_token',
          value: data['access_token'],
        );
      }

      // Parse user from response or use guest user
      final user = data['user'] != null 
          ? UserModel.fromJson(data['user'])
          : guestUser;

      await _cacheUser(user);
      return user;
    } catch (e, stackTrace) {
      throw AuthException(
        message: 'Guest sign-in failed: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Sign out
  Future<void> signOut() async {
    try {
      // Sign out from Google
      if (await _googleSignIn.isSignedIn()) {
        await _googleSignIn.signOut();
      }

      // Notify backend about logout (optional, fire and forget)
      try {
        await _apiClient.post('/auth/logout');
      } catch (e) {
        // Ignore backend logout errors
        print('Backend logout error: $e');
      }

      // Clear local storage
      await _clearLocalData();
    } catch (e, stackTrace) {
      throw AuthException(
        message: 'Sign out failed: $e',
        originalError: e,
        stackTrace: stackTrace,
      );
    }
  }

  /// Check if user is signed in
  Future<bool> isSignedIn() async {
    try {
      final token = await _secureStorage.read(key: 'access_token');
      return token != null && token.isNotEmpty;
    } catch (e) {
      return false;
    }
  }

  /// Get current user
  Future<UserModel?> getCurrentUser() async {
    try {
      // First try to get from cache
      final cachedUser = await _getCachedUser();
      if (cachedUser != null) {
        return cachedUser;
      }

      // If not cached, fetch from backend
      final response = await _apiClient.get('/auth/me');
      final user = UserModel.fromJson(response.data);
      await _cacheUser(user);
      return user;
    } on UnauthorizedException {
      // User is not authenticated
      await _clearLocalData();
      return null;
    } catch (e) {
      print('Get current user error: $e');
      return null;
    }
  }

  /// Refresh access token
  Future<bool> refreshToken() async {
    try {
      final refreshToken = await _secureStorage.read(key: 'refresh_token');
      if (refreshToken == null) return false;

      final response = await _apiClient.post(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );

      final data = response.data;
      if (data['access_token'] != null) {
        await _secureStorage.write(
          key: 'access_token',
          value: data['access_token'],
        );
      }
      if (data['refresh_token'] != null) {
        await _secureStorage.write(
          key: 'refresh_token',
          value: data['refresh_token'],
        );
      }

      return true;
    } catch (e) {
      print('Token refresh error: $e');
      return false;
    }
  }

  /// Cache user data locally
  Future<void> _cacheUser(UserModel user) async {
    try {
      await _secureStorage.write(
        key: 'cached_user',
        value: user.toJson().toString(),
      );
    } catch (e) {
      print('Cache user error: $e');
    }
  }

  /// Get cached user data
  Future<UserModel?> _getCachedUser() async {
    try {
      final userJson = await _secureStorage.read(key: 'cached_user');
      if (userJson == null) return null;

      // Parse JSON string back to Map
      // Note: This is a simplified version. In production, use proper JSON parsing
      return null; // TODO: Implement proper JSON parsing from string
    } catch (e) {
      print('Get cached user error: $e');
      return null;
    }
  }

  /// Clear all local data
  Future<void> _clearLocalData() async {
    await _secureStorage.delete(key: 'access_token');
    await _secureStorage.delete(key: 'refresh_token');
    await _secureStorage.delete(key: 'cached_user');
  }
}
