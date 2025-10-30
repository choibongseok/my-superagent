import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'connectivity_service.dart';

/// Provider for ConnectivityService
final connectivityServiceProvider = Provider<ConnectivityService>((ref) {
  final service = ConnectivityService();
  // Will be initialized in main.dart
  return service;
});

/// Provider for current connectivity status
final isOnlineProvider = StateProvider<bool>((ref) => true);

/// Stream provider for connectivity changes
final connectivityStreamProvider = StreamProvider<bool>((ref) {
  final service = ref.watch(connectivityServiceProvider);
  return service.connectionStream;
});
