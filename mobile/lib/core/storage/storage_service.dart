import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/app_constants.dart';

/// Unified storage service for secure, local, and cached data
class StorageService {
  // Secure Storage (for tokens, sensitive data)
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage(
    aOptions: AndroidOptions(
      encryptedSharedPreferences: true,
    ),
    iOptions: IOSOptions(
      accessibility: KeychainAccessibility.first_unlock,
    ),
  );

  // Hive (for structured data)
  late Box _authBox;
  late Box _tasksBox;
  late Box _settingsBox;
  late Box _cacheBox;

  // SharedPreferences (for simple key-value)
  late SharedPreferences _prefs;

  /// Initialize storage
  Future<void> init() async {
    // Initialize Hive
    await Hive.initFlutter();

    // Open boxes
    _authBox = await Hive.openBox(AppConstants.boxAuth);
    _tasksBox = await Hive.openBox(AppConstants.boxTasks);
    _settingsBox = await Hive.openBox(AppConstants.boxSettings);
    _cacheBox = await Hive.openBox(AppConstants.boxCache);

    // Initialize SharedPreferences
    _prefs = await SharedPreferences.getInstance();
  }

  // ============ Secure Storage Methods ============

  /// Save secure data
  Future<void> saveSecure(String key, String value) async {
    await _secureStorage.write(key: key, value: value);
  }

  /// Read secure data
  Future<String?> readSecure(String key) async {
    return await _secureStorage.read(key: key);
  }

  /// Delete secure data
  Future<void> deleteSecure(String key) async {
    await _secureStorage.delete(key: key);
  }

  /// Clear all secure data
  Future<void> clearSecure() async {
    await _secureStorage.deleteAll();
  }

  // ============ Hive Methods ============

  /// Save to auth box
  Future<void> saveAuth(String key, dynamic value) async {
    await _authBox.put(key, value);
  }

  /// Read from auth box
  dynamic readAuth(String key) {
    return _authBox.get(key);
  }

  /// Delete from auth box
  Future<void> deleteAuth(String key) async {
    await _authBox.delete(key);
  }

  /// Clear auth box
  Future<void> clearAuth() async {
    await _authBox.clear();
  }

  /// Save task
  Future<void> saveTask(String taskId, Map<String, dynamic> task) async {
    await _tasksBox.put(taskId, task);
  }

  /// Read task
  Map<String, dynamic>? readTask(String taskId) {
    return _tasksBox.get(taskId);
  }

  /// Get all tasks
  List<Map<String, dynamic>> getAllTasks() {
    return _tasksBox.values.cast<Map<String, dynamic>>().toList();
  }

  /// Delete task
  Future<void> deleteTask(String taskId) async {
    await _tasksBox.delete(taskId);
  }

  /// Clear all tasks
  Future<void> clearTasks() async {
    await _tasksBox.clear();
  }

  /// Save setting
  Future<void> saveSetting(String key, dynamic value) async {
    await _settingsBox.put(key, value);
  }

  /// Read setting
  dynamic readSetting(String key, {dynamic defaultValue}) {
    return _settingsBox.get(key, defaultValue: defaultValue);
  }

  /// Save to cache
  Future<void> saveCache(String key, dynamic value) async {
    await _cacheBox.put(key, {
      'value': value,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
    });

    // Clean old cache entries
    await _cleanCache();
  }

  /// Read from cache
  dynamic readCache(String key) {
    final cached = _cacheBox.get(key);
    if (cached == null) return null;

    // Check expiration
    final timestamp = cached['timestamp'] as int;
    final age = DateTime.now().millisecondsSinceEpoch - timestamp;
    final maxAge = AppConstants.cacheExpiration.inMilliseconds;

    if (age > maxAge) {
      _cacheBox.delete(key);
      return null;
    }

    return cached['value'];
  }

  /// Clean expired cache entries
  Future<void> _cleanCache() async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final maxAge = AppConstants.cacheExpiration.inMilliseconds;
    final keysToDelete = <dynamic>[];

    for (var key in _cacheBox.keys) {
      final cached = _cacheBox.get(key);
      if (cached != null) {
        final timestamp = cached['timestamp'] as int;
        final age = now - timestamp;
        if (age > maxAge) {
          keysToDelete.add(key);
        }
      }
    }

    for (var key in keysToDelete) {
      await _cacheBox.delete(key);
    }

    // Limit cache size
    if (_cacheBox.length > AppConstants.maxCacheSize) {
      final entriesToDelete = _cacheBox.length - AppConstants.maxCacheSize;
      final keys = _cacheBox.keys.take(entriesToDelete);
      for (var key in keys) {
        await _cacheBox.delete(key);
      }
    }
  }

  /// Clear cache
  Future<void> clearCache() async {
    await _cacheBox.clear();
  }

  // ============ SharedPreferences Methods ============

  /// Save string
  Future<bool> saveString(String key, String value) async {
    return await _prefs.setString(key, value);
  }

  /// Read string
  String? readString(String key) {
    return _prefs.getString(key);
  }

  /// Save int
  Future<bool> saveInt(String key, int value) async {
    return await _prefs.setInt(key, value);
  }

  /// Read int
  int? readInt(String key) {
    return _prefs.getInt(key);
  }

  /// Save bool
  Future<bool> saveBool(String key, bool value) async {
    return await _prefs.setBool(key, value);
  }

  /// Read bool
  bool? readBool(String key) {
    return _prefs.getBool(key);
  }

  /// Save double
  Future<bool> saveDouble(String key, double value) async {
    return await _prefs.setDouble(key, value);
  }

  /// Read double
  double? readDouble(String key) {
    return _prefs.getDouble(key);
  }

  /// Save string list
  Future<bool> saveStringList(String key, List<String> value) async {
    return await _prefs.setStringList(key, value);
  }

  /// Read string list
  List<String>? readStringList(String key) {
    return _prefs.getStringList(key);
  }

  /// Remove key
  Future<bool> remove(String key) async {
    return await _prefs.remove(key);
  }

  /// Clear all SharedPreferences
  Future<bool> clearPrefs() async {
    return await _prefs.clear();
  }

  /// Clear all storage
  Future<void> clearAll() async {
    await clearSecure();
    await clearAuth();
    await clearTasks();
    await clearCache();
    await clearPrefs();
  }
}
