import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'local_storage_service.dart';

/// Provider for LocalStorageService singleton
final localStorageServiceProvider = Provider<LocalStorageService>((ref) {
  final service = LocalStorageService();
  // Initialize will be called in main.dart
  return service;
});

/// Provider for checking if storage is initialized
final isStorageInitializedProvider = StateProvider<bool>((ref) => false);
