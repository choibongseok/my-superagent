# Phase 3 Implementation Guide: Mobile Client (Flutter)

> **목표**: iOS/Android 네이티브 앱 완성 및 배포
> **기간**: 3주
> **우선순위**: P1 (High Priority)

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Implementation](#implementation)
5. [UI/UX Design](#uiux-design)
6. [Testing](#testing)
7. [Deployment](#deployment)
8. [Success Criteria](#success-criteria)

---

## Overview

Phase 3는 AgentHQ의 모바일 클라이언트를 Flutter로 구현합니다.

### Key Features
- ✅ **Cross-Platform**: iOS & Android 동시 지원
- ✅ **Native Performance**: Flutter Engine 기반 60fps 렌더링
- ✅ **Google OAuth**: Mobile-optimized 인증 흐름
- ✅ **Offline Mode**: 로컬 캐싱 및 동기화
- ✅ **Push Notifications**: 실시간 Task 상태 알림
- ✅ **Responsive UI**: 다양한 화면 크기 지원

### Target Platforms
- **iOS**: 14.0+
- **Android**: API 21+ (Android 5.0 Lollipop)

---

## Prerequisites

### Development Environment

```bash
# 1. Install Flutter SDK
# Visit https://docs.flutter.dev/get-started/install

# 2. Verify installation
flutter doctor -v

# 3. Required tools
# - Xcode 14+ (iOS development)
# - Android Studio (Android development)
# - CocoaPods (iOS dependencies)
```

### Backend Requirements
- Phase 0, 1, 2 completed
- Backend API running
- Google OAuth configured

---

## Architecture

### App Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Flutter Application                       │
├─────────────────────────────────────────────────────────────┤
│                    Presentation Layer                        │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │   Screens  │   Widgets    │  Dialogs    │ Bottom Sheets│ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                         │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │  Riverpod  │   Use Cases  │   Models    │  Validators  │ │
│  │  Providers │   (Business  │   (DTOs)    │              │ │
│  │  (State)   │    Logic)    │             │              │ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                      Data Layer                              │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │    API     │    Local     │   Secure    │    Cache     │ │
│  │  Client    │   Storage    │   Storage   │   Manager    │ │
│  │  (HTTP)    │   (SQLite)   │  (Keychain) │   (Hive)     │ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    External Services                         │
│  ┌──────────────┬──────────────┬───────────────┐            │
│  │ Backend API  │  Google OAuth│ Push Notifs   │            │
│  │ (FastAPI)    │  (Firebase)  │ (FCM/APNs)    │            │
│  └──────────────┴──────────────┴───────────────┘            │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
mobile/
├── lib/
│   ├── main.dart                    # Entry point
│   ├── app.dart                     # App configuration
│   │
│   ├── core/                        # Core utilities
│   │   ├── constants/
│   │   │   ├── app_constants.dart   # App-wide constants
│   │   │   ├── api_constants.dart   # API endpoints
│   │   │   └── theme_constants.dart # Theme values
│   │   ├── network/
│   │   │   ├── api_client.dart      # HTTP client
│   │   │   ├── interceptors.dart    # Auth interceptor
│   │   │   └── error_handler.dart   # Error handling
│   │   ├── storage/
│   │   │   ├── local_storage.dart   # SQLite wrapper
│   │   │   ├── secure_storage.dart  # Keychain/Keystore
│   │   │   └── cache_manager.dart   # Hive cache
│   │   └── utils/
│   │       ├── validators.dart
│   │       ├── formatters.dart
│   │       └── extensions.dart
│   │
│   ├── features/                    # Feature modules
│   │   ├── auth/
│   │   │   ├── data/
│   │   │   │   ├── models/
│   │   │   │   │   └── user_model.dart
│   │   │   │   ├── repositories/
│   │   │   │   │   └── auth_repository.dart
│   │   │   │   └── data_sources/
│   │   │   │       └── auth_remote_data_source.dart
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   └── user.dart
│   │   │   │   ├── usecases/
│   │   │   │   │   ├── sign_in_usecase.dart
│   │   │   │   │   └── sign_out_usecase.dart
│   │   │   │   └── repositories/
│   │   │   │       └── auth_repository_interface.dart
│   │   │   └── presentation/
│   │   │       ├── screens/
│   │   │       │   ├── login_screen.dart
│   │   │       │   └── splash_screen.dart
│   │   │       ├── widgets/
│   │   │       │   └── google_sign_in_button.dart
│   │   │       └── providers/
│   │   │           └── auth_provider.dart
│   │   │
│   │   ├── tasks/
│   │   │   ├── data/
│   │   │   │   ├── models/
│   │   │   │   │   └── task_model.dart
│   │   │   │   └── repositories/
│   │   │   │       └── task_repository.dart
│   │   │   ├── domain/
│   │   │   │   ├── entities/
│   │   │   │   │   └── task.dart
│   │   │   │   └── usecases/
│   │   │   │       ├── create_task_usecase.dart
│   │   │   │       ├── get_tasks_usecase.dart
│   │   │   │       └── get_task_result_usecase.dart
│   │   │   └── presentation/
│   │   │       ├── screens/
│   │   │       │   ├── home_screen.dart
│   │   │       │   ├── task_create_screen.dart
│   │   │       │   ├── task_detail_screen.dart
│   │   │       │   └── task_result_screen.dart
│   │   │       ├── widgets/
│   │   │       │   ├── task_card.dart
│   │   │       │   ├── task_status_chip.dart
│   │   │       │   └── task_progress_indicator.dart
│   │   │       └── providers/
│   │   │           └── task_provider.dart
│   │   │
│   │   ├── profile/
│   │   │   └── presentation/
│   │   │       └── screens/
│   │   │           └── profile_screen.dart
│   │   │
│   │   └── settings/
│   │       └── presentation/
│   │           └── screens/
│   │               └── settings_screen.dart
│   │
│   └── shared/                      # Shared components
│       ├── widgets/
│       │   ├── custom_button.dart
│       │   ├── custom_text_field.dart
│       │   ├── loading_indicator.dart
│       │   └── error_widget.dart
│       └── themes/
│           ├── app_theme.dart
│           ├── light_theme.dart
│           └── dark_theme.dart
│
├── test/                            # Unit & widget tests
├── integration_test/                # Integration tests
├── android/                         # Android native
├── ios/                             # iOS native
├── pubspec.yaml                     # Dependencies
└── README.md
```

---

## Implementation

### 1. Project Setup

```bash
# Create Flutter project
flutter create mobile --org com.agenthq --platforms=ios,android

cd mobile

# Install dependencies
flutter pub add dio
flutter pub add flutter_riverpod
flutter pub add google_sign_in
flutter pub add flutter_secure_storage
flutter pub add hive
flutter pub add hive_flutter
flutter pub add firebase_messaging
flutter pub add sqflite
flutter pub add shared_preferences
flutter pub add cached_network_image
flutter pub add intl
flutter pub add go_router

# Dev dependencies
flutter pub add --dev build_runner
flutter pub add --dev flutter_launcher_icons
flutter pub add --dev flutter_native_splash
```

### 2. Core Implementation

#### 2.1 API Client

**File**: `lib/core/network/api_client.dart`

```dart
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiClient {
  late final Dio _dio;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  static const String baseUrl = 'http://localhost:8000/api/v1';

  ApiClient() {
    _dio = Dio(
      BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    // Add auth interceptor
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          // Inject auth token
          final token = await _storage.read(key: 'auth_token');
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          return handler.next(options);
        },
        onError: (error, handler) async {
          // Handle 401 Unauthorized
          if (error.response?.statusCode == 401) {
            // Attempt token refresh
            final refreshed = await _refreshToken();
            if (refreshed) {
              // Retry request
              return handler.resolve(await _dio.fetch(error.requestOptions));
            }
          }
          return handler.next(error);
        },
      ),
    );
  }

  Future<bool> _refreshToken() async {
    try {
      final refreshToken = await _storage.read(key: 'refresh_token');
      if (refreshToken == null) return false;

      final response = await _dio.post(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );

      if (response.statusCode == 200) {
        final newToken = response.data['access_token'];
        await _storage.write(key: 'auth_token', value: newToken);
        return true;
      }
    } catch (e) {
      print('Token refresh failed: $e');
    }
    return false;
  }

  // HTTP Methods
  Future<Response> get(String path, {Map<String, dynamic>? queryParameters}) {
    return _dio.get(path, queryParameters: queryParameters);
  }

  Future<Response> post(String path, {dynamic data}) {
    return _dio.post(path, data: data);
  }

  Future<Response> put(String path, {dynamic data}) {
    return _dio.put(path, data: data);
  }

  Future<Response> delete(String path) {
    return _dio.delete(path);
  }
}
```

#### 2.2 Auth Implementation

**File**: `lib/features/auth/data/repositories/auth_repository.dart`

```dart
import 'package:google_sign_in/google_sign_in.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../../core/network/api_client.dart';
import '../models/user_model.dart';

class AuthRepository {
  final ApiClient _apiClient;
  final FlutterSecureStorage _storage = const FlutterSecureStorage();
  final GoogleSignIn _googleSignIn = GoogleSignIn(
    scopes: [
      'email',
      'https://www.googleapis.com/auth/documents',
      'https://www.googleapis.com/auth/spreadsheets',
      'https://www.googleapis.com/auth/presentations',
      'https://www.googleapis.com/auth/drive.file',
    ],
  );

  AuthRepository(this._apiClient);

  Future<UserModel?> signInWithGoogle() async {
    try {
      // Google Sign-In
      final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
      if (googleUser == null) return null;

      final GoogleSignInAuthentication googleAuth =
          await googleUser.authentication;

      // Exchange with backend
      final response = await _apiClient.post(
        '/auth/google/mobile',
        data: {
          'id_token': googleAuth.idToken,
          'access_token': googleAuth.accessToken,
        },
      );

      if (response.statusCode == 200) {
        final data = response.data;

        // Store tokens
        await _storage.write(key: 'auth_token', value: data['access_token']);
        await _storage.write(key: 'refresh_token', value: data['refresh_token']);

        return UserModel.fromJson(data['user']);
      }
    } catch (e) {
      print('Sign in error: $e');
      rethrow;
    }
    return null;
  }

  Future<void> signOut() async {
    await _googleSignIn.signOut();
    await _storage.delete(key: 'auth_token');
    await _storage.delete(key: 'refresh_token');
  }

  Future<bool> isSignedIn() async {
    final token = await _storage.read(key: 'auth_token');
    return token != null;
  }

  Future<UserModel?> getCurrentUser() async {
    try {
      final response = await _apiClient.get('/auth/me');
      if (response.statusCode == 200) {
        return UserModel.fromJson(response.data);
      }
    } catch (e) {
      print('Get user error: $e');
    }
    return null;
  }
}
```

#### 2.3 Task Management

**File**: `lib/features/tasks/data/repositories/task_repository.dart`

```dart
import '../../../../core/network/api_client.dart';
import '../models/task_model.dart';

class TaskRepository {
  final ApiClient _apiClient;

  TaskRepository(this._apiClient);

  Future<List<TaskModel>> getTasks() async {
    try {
      final response = await _apiClient.get('/tasks');
      if (response.statusCode == 200) {
        final List<dynamic> data = response.data;
        return data.map((json) => TaskModel.fromJson(json)).toList();
      }
    } catch (e) {
      print('Get tasks error: $e');
      rethrow;
    }
    return [];
  }

  Future<TaskModel?> createTask({
    required String prompt,
    required String outputType,
  }) async {
    try {
      final response = await _apiClient.post(
        '/tasks',
        data: {
          'prompt': prompt,
          'output_type': outputType,
        },
      );

      if (response.statusCode == 200) {
        return TaskModel.fromJson(response.data);
      }
    } catch (e) {
      print('Create task error: $e');
      rethrow;
    }
    return null;
  }

  Future<TaskModel?> getTaskById(String taskId) async {
    try {
      final response = await _apiClient.get('/tasks/$taskId');
      if (response.statusCode == 200) {
        return TaskModel.fromJson(response.data);
      }
    } catch (e) {
      print('Get task error: $e');
      rethrow;
    }
    return null;
  }

  Future<Map<String, dynamic>?> getTaskResult(String taskId) async {
    try {
      final response = await _apiClient.get('/tasks/$taskId/result');
      if (response.statusCode == 200) {
        return response.data;
      }
    } catch (e) {
      print('Get task result error: $e');
      rethrow;
    }
    return null;
  }
}
```

### 3. State Management (Riverpod)

**File**: `lib/features/tasks/presentation/providers/task_provider.dart`

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/repositories/task_repository.dart';
import '../../domain/entities/task.dart';

// Task repository provider
final taskRepositoryProvider = Provider<TaskRepository>((ref) {
  return TaskRepository(ref.watch(apiClientProvider));
});

// Task list provider
final taskListProvider = FutureProvider<List<Task>>((ref) async {
  final repository = ref.watch(taskRepositoryProvider);
  final tasks = await repository.getTasks();
  return tasks.map((model) => model.toEntity()).toList();
});

// Task detail provider
final taskDetailProvider = FutureProvider.family<Task?, String>((ref, taskId) async {
  final repository = ref.watch(taskRepositoryProvider);
  final task = await repository.getTaskById(taskId);
  return task?.toEntity();
});

// Create task provider
final createTaskProvider = Provider<Future<Task?> Function({
  required String prompt,
  required String outputType,
})>((ref) {
  final repository = ref.watch(taskRepositoryProvider);

  return ({required String prompt, required String outputType}) async {
    final task = await repository.createTask(
      prompt: prompt,
      outputType: outputType,
    );
    return task?.toEntity();
  };
});
```

---

## UI/UX Design

### Design System

#### Colors

```dart
// lib/shared/themes/app_colors.dart
class AppColors {
  // Primary
  static const primary = Color(0xFF6366F1);      // Indigo
  static const primaryDark = Color(0xFF4F46E5);
  static const primaryLight = Color(0xFF818CF8);

  // Secondary
  static const secondary = Color(0xFF8B5CF6);    // Purple
  static const accent = Color(0xFF06B6D4);       // Cyan

  // Status
  static const success = Color(0xFF10B981);      // Green
  static const warning = Color(0xFFF59E0B);      // Amber
  static const error = Color(0xFFEF4444);        // Red
  static const info = Color(0xFF3B82F6);         // Blue

  // Neutral
  static const background = Color(0xFFF9FAFB);
  static const surface = Color(0xFFFFFFFF);
  static const textPrimary = Color(0xFF111827);
  static const textSecondary = Color(0xFF6B7280);
  static const border = Color(0xFFE5E7EB);
}
```

#### Typography

```dart
// lib/shared/themes/app_typography.dart
class AppTypography {
  static const fontFamily = 'SF Pro Text';

  static const h1 = TextStyle(
    fontSize: 32,
    fontWeight: FontWeight.bold,
    letterSpacing: -0.5,
  );

  static const h2 = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.bold,
    letterSpacing: -0.5,
  );

  static const h3 = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w600,
  );

  static const body1 = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.normal,
    height: 1.5,
  );

  static const body2 = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.normal,
    height: 1.5,
  );

  static const caption = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.normal,
    color: AppColors.textSecondary,
  );
}
```

### Screen Designs

#### 1. Home Screen

**File**: `lib/features/tasks/presentation/screens/home_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/task_provider.dart';
import '../widgets/task_card.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tasksAsync = ref.watch(taskListProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AgentHQ'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.refresh(taskListProvider),
          ),
        ],
      ),
      body: tasksAsync.when(
        data: (tasks) {
          if (tasks.isEmpty) {
            return const Center(
              child: Text('No tasks yet. Create your first task!'),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => ref.refresh(taskListProvider),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: tasks.length,
              itemBuilder: (context, index) {
                return TaskCard(task: tasks[index]);
              },
            ),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, stack) => Center(
          child: Text('Error: $error'),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          Navigator.pushNamed(context, '/tasks/create');
        },
        icon: const Icon(Icons.add),
        label: const Text('New Task'),
      ),
    );
  }
}
```

#### 2. Task Card Widget

**File**: `lib/features/tasks/presentation/widgets/task_card.dart`

```dart
import 'package:flutter/material.dart';
import '../../domain/entities/task.dart';
import 'task_status_chip.dart';

class TaskCard extends StatelessWidget {
  final Task task;

  const TaskCard({Key? key, required this.task}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
      ),
      child: InkWell(
        onTap: () {
          Navigator.pushNamed(
            context,
            '/tasks/${task.id}',
            arguments: task,
          );
        },
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      task.prompt,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8),
                  TaskStatusChip(status: task.status),
                ],
              ),

              const SizedBox(height: 12),

              // Metadata
              Row(
                children: [
                  Icon(
                    _getOutputIcon(task.outputType),
                    size: 16,
                    color: Colors.grey[600],
                  ),
                  const SizedBox(width: 4),
                  Text(
                    task.outputType.toUpperCase(),
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey[600],
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Icon(
                    Icons.access_time,
                    size: 16,
                    color: Colors.grey[600],
                  ),
                  const SizedBox(width: 4),
                  Text(
                    _formatTime(task.createdAt),
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey[600],
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  IconData _getOutputIcon(String type) {
    switch (type.toLowerCase()) {
      case 'docs':
        return Icons.description;
      case 'sheets':
        return Icons.table_chart;
      case 'slides':
        return Icons.slideshow;
      default:
        return Icons.file_present;
    }
  }

  String _formatTime(DateTime dateTime) {
    final now = DateTime.now();
    final difference = now.difference(dateTime);

    if (difference.inMinutes < 1) {
      return 'Just now';
    } else if (difference.inHours < 1) {
      return '${difference.inMinutes}m ago';
    } else if (difference.inDays < 1) {
      return '${difference.inHours}h ago';
    } else {
      return '${difference.inDays}d ago';
    }
  }
}
```

---

## Testing

### Unit Tests

**File**: `test/features/tasks/data/repositories/task_repository_test.dart`

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';

void main() {
  group('TaskRepository', () {
    test('getTasks should return list of tasks', () async {
      // Arrange
      final repository = TaskRepository(mockApiClient);

      // Act
      final tasks = await repository.getTasks();

      // Assert
      expect(tasks, isA<List<TaskModel>>());
      expect(tasks.length, greaterThan(0));
    });

    test('createTask should return created task', () async {
      // Arrange
      final repository = TaskRepository(mockApiClient);

      // Act
      final task = await repository.createTask(
        prompt: 'Test prompt',
        outputType: 'docs',
      );

      // Assert
      expect(task, isNotNull);
      expect(task?.prompt, equals('Test prompt'));
    });
  });
}
```

### Widget Tests

```dart
void main() {
  testWidgets('HomeScreen displays tasks', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: HomeScreen()),
      ),
    );

    // Wait for tasks to load
    await tester.pumpAndSettle();

    // Verify task cards are displayed
    expect(find.byType(TaskCard), findsWidgets);
  });
}
```

---

## Deployment

### iOS Deployment

```bash
# 1. Build iOS app
cd mobile
flutter build ios --release

# 2. Open Xcode
open ios/Runner.xcworkspace

# 3. Archive and distribute via Xcode
# Product → Archive → Distribute App → App Store Connect
```

### Android Deployment

```bash
# 1. Build Android app bundle
flutter build appbundle --release

# 2. Upload to Google Play Console
# build/app/outputs/bundle/release/app-release.aab
```

---

## Success Criteria

### Technical Metrics
- ✅ iOS & Android 빌드 성공
- ✅ 60fps 렌더링 유지
- ✅ OAuth 인증 성공률 100%
- ✅ Offline mode 정상 작동
- ✅ Test coverage 70%+

### User Experience
- ✅ 앱 시작 < 3초
- ✅ Task 생성 < 5초
- ✅ 직관적인 UI/UX
- ✅ 에러 처리 완벽

---

## Next Steps

- **Phase 4**: Collaboration & Enterprise features
- **Analytics**: Firebase Analytics 통합
- **Crash Reporting**: Sentry/Firebase Crashlytics
- **Performance**: 성능 최적화

---

## References

- [Flutter Documentation](https://docs.flutter.dev/)
- [Riverpod Documentation](https://riverpod.dev/)
- [Material Design](https://m3.material.io/)
- [PHASE_PLAN.md](PHASE_PLAN.md)
