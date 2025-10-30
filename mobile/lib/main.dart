import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';
import 'core/storage/local_storage_service.dart';
import 'core/storage/storage_provider.dart';
import 'core/connectivity/connectivity_service.dart';
import 'core/connectivity/connectivity_provider.dart';
import 'core/sync/sync_service.dart';
import 'core/sync/sync_provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Set system UI overlay style
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: Color(0xFF0F0F0F),
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );

  // Create ProviderContainer for initialization
  final container = ProviderContainer();

  // Initialize local storage
  print('🔧 Initializing local storage...');
  final localStorage = container.read(localStorageServiceProvider);
  await localStorage.initialize();
  container.read(isStorageInitializedProvider.notifier).state = true;
  print('✅ Local storage initialized');

  // Initialize connectivity monitoring
  print('🔧 Initializing connectivity monitoring...');
  final connectivity = container.read(connectivityServiceProvider);
  await connectivity.initialize();
  container.read(isOnlineProvider.notifier).state = connectivity.isOnline;
  print('✅ Connectivity monitoring initialized (${connectivity.isOnline ? "Online" : "Offline"})');

  // Listen to connectivity changes
  connectivity.connectionStream.listen((isOnline) {
    container.read(isOnlineProvider.notifier).state = isOnline;
    print('🌐 Connectivity changed: ${isOnline ? "Online" : "Offline"}');
    
    // Trigger sync when coming online
    if (isOnline) {
      print('🔄 Device is online, triggering sync...');
      final syncService = container.read(syncServiceProvider);
      syncService.syncAll().then((result) {
        print('Sync result: $result');
      });
    }
  });

  // Initialize sync service
  print('🔧 Initializing sync service...');
  final syncService = container.read(syncServiceProvider);
  syncService.startAutoSync(interval: const Duration(minutes: 5));
  print('✅ Sync service initialized (auto-sync every 5 minutes)');

  // Run app with the container
  runApp(
    UncontrolledProviderScope(
      container: container,
      child: const AgentHQApp(),
    ),
  );
}
