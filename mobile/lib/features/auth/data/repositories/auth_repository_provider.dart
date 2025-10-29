import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../../core/network/api_provider.dart';
import 'auth_repository.dart';

/// Provider for AuthRepository
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  
  return AuthRepository(
    apiClient: apiClient,
    secureStorage: const FlutterSecureStorage(),
    googleSignIn: GoogleSignIn(
      scopes: ['email', 'profile'],
    ),
  );
});
