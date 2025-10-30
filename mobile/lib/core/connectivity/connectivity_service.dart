import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';

/// Service for monitoring network connectivity
class ConnectivityService {
  final Connectivity _connectivity = Connectivity();
  
  StreamController<bool>? _connectionStatusController;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  
  bool _isOnline = true;
  bool get isOnline => _isOnline;

  /// Initialize connectivity monitoring
  Future<void> initialize() async {
    _connectionStatusController = StreamController<bool>.broadcast();
    
    // Check initial connectivity
    final result = await _connectivity.checkConnectivity();
    _isOnline = _isConnected(result);
    
    // Listen to connectivity changes
    _connectivitySubscription = _connectivity.onConnectivityChanged.listen(
      (List<ConnectivityResult> results) {
        final connected = _isConnected(results);
        if (connected != _isOnline) {
          _isOnline = connected;
          _connectionStatusController?.add(_isOnline);
          print('🌐 Connectivity changed: ${_isOnline ? "Online" : "Offline"}');
        }
      },
    );
  }

  /// Check if connected based on connectivity result
  bool _isConnected(List<ConnectivityResult> results) {
    return results.any((result) => 
      result == ConnectivityResult.mobile ||
      result == ConnectivityResult.wifi ||
      result == ConnectivityResult.ethernet
    );
  }

  /// Stream of connectivity status changes
  Stream<bool> get connectionStream {
    if (_connectionStatusController == null) {
      throw StateError('ConnectivityService not initialized');
    }
    return _connectionStatusController!.stream;
  }

  /// Dispose resources
  void dispose() {
    _connectivitySubscription?.cancel();
    _connectionStatusController?.close();
  }
}
