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

### Design System (Genspark Style)
**Dark Theme 기반 현대적 UI/UX**

- 🎨 **Color Palette**:
  - Background: #0F0F0F (Main), #1A1A1A (Cards), #1F1F1F (Input)
  - Primary: #3B82F6 (Blue accent)
  - Text: #E5E5E5 (Primary), #A0A0A0 (Secondary)

- 📐 **Layout**:
  - 중앙 큰 검색창 (Hero interaction)
  - 아이콘 그리드 (AI 도구 선택)
  - 카드 기반 콘텐츠 (이미지 + 메타데이터)

- ✨ **Components**:
  - Agent Selection Hub (11개 AI 도구)
  - Multi-line Search Input (음성, 이미지, 파일 첨부)
  - Task Cards with AI Pods badges
  - Status chips with icons

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

#### Colors (Genspark Dark Theme)

```dart
// lib/shared/themes/app_colors.dart
class AppColors {
  // Dark Theme Base (Genspark style)
  static const backgroundDark = Color(0xFF0F0F0F);     // Main background
  static const backgroundCard = Color(0xFF1A1A1A);     // Card background
  static const backgroundInput = Color(0xFF1F1F1F);    // Input fields
  static const backgroundSidebar = Color(0xFF161616);  // Sidebar

  // Primary Blue (Accent)
  static const primary = Color(0xFF3B82F6);            // Blue
  static const primaryHover = Color(0xFF2563EB);
  static const primaryLight = Color(0xFF60A5FA);

  // Secondary
  static const secondary = Color(0xFF8B5CF6);          // Purple
  static const accent = Color(0xFF06B6D4);             // Cyan
  static const accentGold = Color(0xFFD4AF37);         // Gold for premium

  // Status
  static const success = Color(0xFF10B981);            // Green
  static const warning = Color(0xFFF59E0B);            // Amber
  static const error = Color(0xFFEF4444);              // Red
  static const info = Color(0xFF3B82F6);               // Blue

  // Text (Dark Theme)
  static const textPrimary = Color(0xFFE5E5E5);        // Light gray
  static const textSecondary = Color(0xFFA0A0A0);      // Medium gray
  static const textTertiary = Color(0xFF6B7280);       // Dark gray
  static const textDisabled = Color(0xFF4B5563);

  // Borders & Dividers
  static const border = Color(0xFF2A2A2A);
  static const divider = Color(0xFF1F1F1F);

  // Overlay & Shadow
  static const overlay = Color(0x80000000);            // 50% black
  static const shadowDark = Color(0xFF000000);
}
```

#### Typography (Genspark Style)

```dart
// lib/shared/themes/app_typography.dart
class AppTypography {
  static const fontFamily = 'Inter';  // Modern, clean font

  // Hero Title (Genspark 슈퍼 에이전트 style)
  static const hero = TextStyle(
    fontSize: 36,
    fontWeight: FontWeight.w700,
    letterSpacing: -1.0,
    height: 1.2,
    color: AppColors.textPrimary,
  );

  static const h1 = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.8,
    color: AppColors.textPrimary,
  );

  static const h2 = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.5,
    color: AppColors.textPrimary,
  );

  static const h3 = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w600,
    color: AppColors.textPrimary,
  );

  // Body text
  static const body1 = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.normal,
    height: 1.5,
    color: AppColors.textSecondary,
  );

  static const body2 = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.normal,
    height: 1.5,
    color: AppColors.textSecondary,
  );

  // Small text
  static const caption = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.normal,
    color: AppColors.textTertiary,
  );

  // Button text
  static const button = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.3,
  );

  // Agent card title
  static const agentTitle = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    color: AppColors.textSecondary,
  );
}
```

### Screen Designs (Genspark Style)

#### 1. Home Screen - Agent Selection Hub

**File**: `lib/features/tasks/presentation/screens/home_screen.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../widgets/agent_grid.dart';
import '../widgets/search_input.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      backgroundColor: AppColors.backgroundDark,
      body: SafeArea(
        child: Column(
          children: [
            // Top Navigation
            _buildTopBar(context),

            // Main Content
            Expanded(
              child: SingleChildScrollView(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    children: [
                      const SizedBox(height: 60),

                      // Hero Title
                      Text(
                        'AgentHQ 슈퍼 에이전트',
                        style: AppTypography.hero.copyWith(
                          color: AppColors.textSecondary,
                        ),
                        textAlign: TextAlign.center,
                      ),

                      const SizedBox(height: 40),

                      // Large Search Input
                      const SearchInput(),

                      const SizedBox(height: 60),

                      // Agent Grid
                      const AgentGrid(),

                      const SizedBox(height: 40),

                      // Recent Tasks Section
                      _buildRecentTasks(ref),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Logo or Menu
          IconButton(
            icon: const Icon(Icons.menu, color: AppColors.textSecondary),
            onPressed: () {
              Scaffold.of(context).openDrawer();
            },
          ),

          // Right actions
          Row(
            children: [
              // Premium button
              OutlinedButton(
                onPressed: () {},
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: AppColors.primary),
                  foregroundColor: AppColors.primary,
                ),
                child: const Text('온디바이스 Free AI'),
              ),
              const SizedBox(width: 12),
              // Profile
              CircleAvatar(
                radius: 18,
                backgroundColor: AppColors.backgroundCard,
                child: const Icon(Icons.person, size: 20),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRecentTasks(WidgetRef ref) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '최근',
              style: AppTypography.h3.copyWith(
                color: AppColors.textSecondary,
              ),
            ),
            TextButton(
              onPressed: () {},
              child: const Text('모두 보기'),
            ),
          ],
        ),
        const SizedBox(height: 16),
        // Recent task cards will be rendered here
        const SizedBox(height: 40),
      ],
    );
  }
}
```

#### 2. Search Input Widget

**File**: `lib/features/tasks/presentation/widgets/search_input.dart`

```dart
import 'package:flutter/material.dart';

class SearchInput extends StatefulWidget {
  const SearchInput({Key? key}) : super(key: key);

  @override
  State<SearchInput> createState() => _SearchInputState();
}

class _SearchInputState extends State<SearchInput> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.backgroundInput,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: _focusNode.hasFocus
            ? AppColors.primary
            : AppColors.border,
          width: 1.5,
        ),
      ),
      child: Column(
        children: [
          // Main input
          TextField(
            controller: _controller,
            focusNode: _focusNode,
            maxLines: null,
            style: AppTypography.body1.copyWith(
              color: AppColors.textPrimary,
            ),
            decoration: InputDecoration(
              hintText: '무엇이든 질문하고 만들어보세요',
              hintStyle: AppTypography.body1.copyWith(
                color: AppColors.textTertiary,
              ),
              border: InputBorder.none,
              contentPadding: const EdgeInsets.all(20),
            ),
          ),

          // Bottom action bar
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: const BoxDecoration(
              border: Border(
                top: BorderSide(color: AppColors.border, width: 1),
              ),
            ),
            child: Row(
              children: [
                // Left actions
                _buildActionButton(Icons.person_outline, '채팅 대화 연결'),
                const SizedBox(width: 12),
                _buildActionButton(Icons.palette_outlined, '폰트'),
                const SizedBox(width: 12),
                _buildActionButton(Icons.attach_file, ''),

                const Spacer(),

                // Right actions
                IconButton(
                  icon: const Icon(Icons.mic, color: AppColors.textSecondary),
                  onPressed: () {},
                ),
                IconButton(
                  icon: const Icon(Icons.image_outlined, color: AppColors.textSecondary),
                  onPressed: () {},
                ),
                IconButton(
                  icon: const Icon(Icons.send, color: AppColors.primary),
                  onPressed: () {
                    // Send message
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionButton(IconData icon, String label) {
    return InkWell(
      onTap: () {},
      child: Row(
        children: [
          Icon(icon, size: 18, color: AppColors.textSecondary),
          if (label.isNotEmpty) ...[
            const SizedBox(width: 4),
            Text(
              label,
              style: AppTypography.caption.copyWith(
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ],
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }
}
```

#### 3. Agent Grid Widget

**File**: `lib/features/tasks/presentation/widgets/agent_grid.dart`

```dart
import 'package:flutter/material.dart';

class AgentGrid extends StatelessWidget {
  const AgentGrid({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Grid of agents
        Wrap(
          spacing: 20,
          runSpacing: 24,
          alignment: WrapAlignment.center,
          children: [
            _buildAgentCard(
              icon: Icons.description_outlined,
              label: 'AI 문서',
              color: Colors.blue,
            ),
            _buildAgentCard(
              icon: Icons.table_chart_outlined,
              label: 'AI 시트',
              color: Colors.green,
            ),
            _buildAgentCard(
              icon: Icons.photo_library_outlined,
              label: 'AI 개발자',
              color: Colors.purple,
            ),
            _buildAgentCard(
              icon: Icons.slideshow_outlined,
              label: 'AI 슬라이드',
              color: Colors.orange,
            ),
            _buildAgentCard(
              icon: Icons.design_services_outlined,
              label: 'AI 디자이너',
              color: Colors.pink,
            ),
            _buildAgentCard(
              icon: Icons.code_outlined,
              label: '플랫 자바스크립트',
              color: Colors.yellow,
            ),
            _buildAgentCard(
              icon: Icons.chat_bubble_outline,
              label: 'AI 채팅',
              color: Colors.cyan,
            ),
            _buildAgentCard(
              icon: Icons.image_outlined,
              label: 'AI 이미지',
              color: AppColors.accentGold,
            ),
            _buildAgentCard(
              icon: Icons.videocam_outlined,
              label: 'AI 동영상',
              color: Colors.red,
            ),
            _buildAgentCard(
              icon: Icons.dashboard_outlined,
              label: 'AI 화이트 보드',
              color: Colors.teal,
            ),
            _buildAgentCard(
              icon: Icons.apps,
              label: '모든 에이전트',
              color: AppColors.textSecondary,
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildAgentCard({
    required IconData icon,
    required String label,
    required Color color,
  }) {
    return InkWell(
      onTap: () {
        // Navigate to agent
      },
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 80,
        child: Column(
          children: [
            // Icon container
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: AppColors.backgroundCard,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: AppColors.border,
                  width: 1,
                ),
              ),
              child: Icon(
                icon,
                color: color,
                size: 28,
              ),
            ),
            const SizedBox(height: 8),
            // Label
            Text(
              label,
              style: AppTypography.agentTitle,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}
```

#### 4. Task Card Widget (Dark Theme)

**File**: `lib/features/tasks/presentation/widgets/task_card.dart`

```dart
import 'package:flutter/material.dart';
import '../../domain/entities/task.dart';
import 'task_status_chip.dart';

class TaskCard extends StatelessWidget {
  final Task task;
  final String? imageUrl;
  final String? label;

  const TaskCard({
    Key? key,
    required this.task,
    this.imageUrl,
    this.label,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 280,
      margin: const EdgeInsets.only(right: 16),
      decoration: BoxDecoration(
        color: AppColors.backgroundCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.border,
          width: 1,
        ),
      ),
      child: InkWell(
        onTap: () {
          Navigator.pushNamed(
            context,
            '/tasks/${task.id}',
            arguments: task,
          );
        },
        borderRadius: BorderRadius.circular(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Image preview (if available)
            if (imageUrl != null)
              ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(16),
                ),
                child: Image.network(
                  imageUrl!,
                  height: 160,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) {
                    return Container(
                      height: 160,
                      color: AppColors.backgroundInput,
                      child: Icon(
                        _getOutputIcon(task.outputType),
                        size: 48,
                        color: AppColors.textTertiary,
                      ),
                    );
                  },
                ),
              ),

            // Content
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Label badge (AI Pods style)
                  if (label != null)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.backgroundInput,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.auto_awesome,
                            size: 12,
                            color: AppColors.primary,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            label!,
                            style: AppTypography.caption.copyWith(
                              color: AppColors.textSecondary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),

                  const SizedBox(height: 12),

                  // Task title
                  Text(
                    task.prompt,
                    style: AppTypography.body1.copyWith(
                      color: AppColors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),

                  const SizedBox(height: 12),

                  // Metadata row
                  Row(
                    children: [
                      // Output type
                      Icon(
                        _getOutputIcon(task.outputType),
                        size: 14,
                        color: AppColors.textTertiary,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        task.outputType.toUpperCase(),
                        style: AppTypography.caption.copyWith(
                          color: AppColors.textTertiary,
                        ),
                      ),

                      const Spacer(),

                      // Status
                      TaskStatusChip(status: task.status),
                    ],
                  ),

                  const SizedBox(height: 8),

                  // Time
                  Text(
                    _formatTime(task.createdAt),
                    style: AppTypography.caption.copyWith(
                      color: AppColors.textTertiary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  IconData _getOutputIcon(String type) {
    switch (type.toLowerCase()) {
      case 'docs':
        return Icons.description_outlined;
      case 'sheets':
        return Icons.table_chart_outlined;
      case 'slides':
        return Icons.slideshow_outlined;
      default:
        return Icons.auto_awesome;
    }
  }

  String _formatTime(DateTime dateTime) {
    final now = DateTime.now();
    final difference = now.difference(dateTime);

    if (difference.inMinutes < 1) {
      return '방금 전';
    } else if (difference.inHours < 1) {
      return '${difference.inMinutes}분 전';
    } else if (difference.inDays < 1) {
      return '${difference.inHours}시간 전';
    } else {
      return '${difference.inDays}일 전';
    }
  }
}
```

#### 5. Task Status Chip (Dark Theme)

**File**: `lib/features/tasks/presentation/widgets/task_status_chip.dart`

```dart
import 'package:flutter/material.dart';

class TaskStatusChip extends StatelessWidget {
  final String status;

  const TaskStatusChip({Key? key, required this.status}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final config = _getStatusConfig(status);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: config['bgColor'],
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: config['borderColor'],
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            config['icon'],
            size: 12,
            color: config['iconColor'],
          ),
          const SizedBox(width: 4),
          Text(
            config['label'],
            style: AppTypography.caption.copyWith(
              color: config['textColor'],
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Map<String, dynamic> _getStatusConfig(String status) {
    switch (status.toLowerCase()) {
      case 'completed':
        return {
          'label': '완료',
          'icon': Icons.check_circle,
          'iconColor': AppColors.success,
          'textColor': AppColors.success,
          'bgColor': AppColors.success.withOpacity(0.1),
          'borderColor': AppColors.success.withOpacity(0.3),
        };
      case 'processing':
      case 'in_progress':
        return {
          'label': '진행중',
          'icon': Icons.access_time,
          'iconColor': AppColors.primary,
          'textColor': AppColors.primary,
          'bgColor': AppColors.primary.withOpacity(0.1),
          'borderColor': AppColors.primary.withOpacity(0.3),
        };
      case 'failed':
        return {
          'label': '실패',
          'icon': Icons.error,
          'iconColor': AppColors.error,
          'textColor': AppColors.error,
          'bgColor': AppColors.error.withOpacity(0.1),
          'borderColor': AppColors.error.withOpacity(0.3),
        };
      default:
        return {
          'label': '대기중',
          'icon': Icons.schedule,
          'iconColor': AppColors.textTertiary,
          'textColor': AppColors.textTertiary,
          'bgColor': AppColors.backgroundInput,
          'borderColor': AppColors.border,
        };
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
