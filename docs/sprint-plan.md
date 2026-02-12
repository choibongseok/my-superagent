# 🎯 AgentHQ 6주 스프린트 계획서

> **기획 날짜**: 2026-02-12  
> **목표**: Phase 0-4 기술 부채 해결 및 Phase 3-1 (Mobile) 완성  
> **기간**: Week 1-6 (총 6주)

---

## 📊 프로젝트 현황 분석

### ✅ 완료된 기능
- **Phase 0**: LangChain/LangFuse 통합 (구조만)
- **Phase 1**: Research Agent, Docs Agent (부분 구현)
- **Phase 2**: Memory System, Citation Tracker (미연결)
- **Phase 3**: Desktop UI (완료 - React/Tauri)
- **Phase 3-1**: Mobile UI (30% - Flutter, 로직 없음)

### ❌ 주요 문제점 (PHASE_0-4_AUDIT 기준)

#### **Critical (P0) - 서비스 중단**
1. ❌ **Agent 메모리 연결 오류**  
   - `backend/app/agents/base.py:248` → `self.memory.buffer` 속성 없음
   - 모든 Agent 초기화 시 `AttributeError` 발생

2. ❌ **Celery 비동기 처리 버그**  
   - `backend/app/agents/celery_app.py:56` → async 메서드를 await 없이 호출
   - Task가 coroutine 객체 반환하고 실패

3. ❌ **Google API 인증 누락**  
   - `backend/app/agents/celery_app.py:101` → `credentials=None` 고정
   - Google Workspace API 호출 전부 실패

#### **High (P1) - 기능 미구현**
4. ❌ **Sheets Agent, Slides Agent 미구현**  
   - `backend/app/agents/sheets_agent.py:1`, `slides_agent.py:1` → TODO 상태
   - 핵심 기능 2개 완전 누락

5. ❌ **Memory Manager 미사용**  
   - `backend/app/memory/manager.py:21` → 정의만 되고 import 안 됨
   - Phase 2 Memory 레이어 전체 미작동

6. ❌ **Mobile OAuth 미구현**  
   - `mobile/lib/features/auth/presentation/screens/login_screen.dart:17` → Placeholder
   - Google Sign-In 안 됨, Backend API 통합 없음

7. ❌ **Mobile Data Layer 없음**  
   - Repository, ApiClient, Models 전부 누락
   - UI만 있고 동작 안 함

#### **Medium (P2) - 기능 불완전**
8. ❌ **Citation Tracker 미연결**  
   - `backend/app/agents/research_agent.py:155` → Citation Tracker 안 쓰고 직접 생성
   - Phase 2 Citation 시스템 무용지물

9. ❌ **WebSocket 라이프사이클 버그**  
   - `desktop/src/pages/HomePage.tsx:38` → reconnect 시 chat join 누락
   - 실시간 메시지 손실 가능

10. ❌ **Alembic 마이그레이션 오류**  
    - `backend/alembic/versions/c4d39e6ece1f_add_chat_and_message_models.py:21` → Type import 누락
    - DB 마이그레이션 실패

---

## 🎯 6주 스프린트 목표

### **Week 1-2: 긴급 버그 수정 (P0)**
> 목표: 서비스 정상 작동 복구

1. Agent 메모리 연결 수정
2. Celery 비동기 처리 수정
3. Google API 인증 정상화
4. Alembic 마이그레이션 수정

### **Week 3-4: 핵심 기능 완성 (P1)**
> 목표: Sheets/Slides Agent 구현 + Mobile Backend 통합

5. Sheets Agent 완전 구현
6. Slides Agent 완전 구현
7. Memory Manager 연결
8. Mobile Data Layer 구현 (Repository, ApiClient, Models)
9. Mobile OAuth 완성

### **Week 5-6: 최적화 및 통합 테스트 (P2)**
> 목표: 시스템 안정화 + 성능 최적화

10. Citation Tracker 연결
11. WebSocket 버그 수정
12. Mobile Offline Mode 구현
13. 통합 테스트 (Desktop ↔ Mobile ↔ Backend)
14. 성능 프로파일링 및 최적화

---

## 📅 상세 스프린트 계획

---

## **Week 1: Critical 버그 수정 (Phase 0-1 긴급 복구)**

### 목표
- ✅ Agent 초기화 오류 해결
- ✅ Celery Task 정상 작동
- ✅ Google API 연동 복구

### 작업 항목

#### **Day 1-2: Agent Memory 연결 수정**
```python
# backend/app/memory/conversation.py
class ConversationMemory:
    def __init__(self, ...):
        self.memory = ConversationBufferMemory(...)
        self.buffer = self.memory  # ✅ 추가: buffer 속성 노출
    
    @property
    def buffer(self):
        """LangChain agent가 접근할 수 있도록 buffer 노출"""
        return self.memory
```

**검증 방법**:
```bash
pytest tests/test_memory.py -v
curl -X POST http://localhost:8000/api/v1/tasks \
  -d '{"prompt": "Test memory", "task_type": "research"}'
```

---

#### **Day 3-4: Celery 비동기 처리 수정**
```python
# backend/app/agents/celery_app.py (BEFORE)
@celery.task
def research_task(prompt: str, user_id: str):
    agent = ResearchAgent()
    result = agent.research(prompt)  # ❌ coroutine 객체 반환

# backend/app/agents/celery_app.py (AFTER)
@celery.task
def research_task(prompt: str, user_id: str):
    agent = ResearchAgent()
    result = asyncio.run(agent.research(prompt))  # ✅ await 처리
    return result
```

**추가 수정**:
- `docs_agent.py:137` → `content_request` 파라미터 제거 또는 추가
- `celery_app.py` 전체 async 호출 검토

**검증 방법**:
```bash
celery -A app.agents.celery_app worker --loglevel=info
# 다른 터미널에서
python -c "from app.agents.celery_app import research_task; research_task.delay('AI trends', 'user-123')"
```

---

#### **Day 5: Google API 인증 정상화**
```python
# backend/app/agents/celery_app.py (BEFORE)
def create_document(prompt: str, content: dict, user_id: str):
    docs_agent = DocsAgent(credentials=None)  # ❌

# backend/app/agents/celery_app.py (AFTER)
def create_document(prompt: str, content: dict, user_id: str):
    from app.services.google_auth import get_user_credentials
    creds = get_user_credentials(user_id)  # ✅ 실제 인증 정보
    docs_agent = DocsAgent(credentials=creds)
```

**검증 방법**:
```bash
# .env에 Google OAuth 설정 후
pytest tests/integration/test_google_api.py
```

---

## **Week 2: Database & Migration 수정**

### 목표
- ✅ Alembic 마이그레이션 정상화
- ✅ DB 스키마 검증

### 작업 항목

#### **Day 1-2: Alembic 마이그레이션 수정**
```python
# backend/alembic/versions/c4d39e6ece1f_add_chat_and_message_models.py
from sqlalchemy.dialects.postgresql import UUID  # ✅ 추가
import sqlalchemy as sa

def upgrade():
    # ❌ 수동 CREATE TYPE 제거
    # op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')")
    
    # ✅ SQLAlchemy Enum 사용
    message_role_enum = sa.Enum('user', 'assistant', 'system', name='message_role')
    message_role_enum.create(op.get_bind(), checkfirst=True)
    
    op.create_table(
        'messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('role', message_role_enum, nullable=False),
        # ...
    )
```

**검증 방법**:
```bash
alembic downgrade -1
alembic upgrade head
# DB 스키마 확인
psql -d agenthq -c "\d messages"
```

---

#### **Day 3-5: Desktop WebSocket 버그 수정**
```typescript
// desktop/src/pages/HomePage.tsx (BEFORE)
useEffect(() => {
  if (socket?.connected) {
    socket.emit('join_chat', { chatId });  // ❌ 초기 연결만
  }
}, [chatId]);

// desktop/src/pages/HomePage.tsx (AFTER)
useEffect(() => {
  if (!socket) return;
  
  const handleConnect = () => {
    if (chatId) socket.emit('join_chat', { chatId });
  };
  
  socket.on('connect', handleConnect);  // ✅ 재연결 대응
  if (socket.connected) handleConnect();
  
  return () => {
    socket.off('connect', handleConnect);
  };
}, [socket, chatId]);
```

**검증 방법**:
```bash
# Backend WebSocket 서버 재시작 후
# Desktop 앱에서 chat 전환 테스트
npm run tauri dev
```

---

## **Week 3-4: Sheets & Slides Agent 구현 + Mobile Backend 통합**

### 목표
- ✅ Sheets Agent 완전 구현
- ✅ Slides Agent 완전 구현
- ✅ Memory Manager 연결
- ✅ Mobile Data Layer 완성
- ✅ Mobile OAuth 완성

---

### **Week 3: Sheets Agent 구현**

#### **Day 1-3: Sheets Agent 핵심 기능**
```python
# backend/app/agents/sheets_agent.py
from googleapiclient.discovery import build
from langchain.tools import Tool

class SheetsAgent(BaseAgent):
    def __init__(self, credentials):
        self.credentials = credentials
        self.service = build('sheets', 'v4', credentials=credentials)
        
        tools = [
            Tool(
                name="create_spreadsheet",
                func=self._create_spreadsheet,
                description="Create a new Google Sheet with data"
            ),
            Tool(
                name="add_chart",
                func=self._add_chart,
                description="Add chart to spreadsheet"
            )
        ]
        
        super().__init__(
            agent_type="sheets",
            tools=tools,
            prompt_template=sheets_prompt
        )
    
    def _create_spreadsheet(self, title: str, data: List[List]) -> str:
        """스프레드시트 생성"""
        spreadsheet = {
            'properties': {'title': title},
            'sheets': [{
                'data': [{
                    'rowData': [
                        {'values': [{'userEnteredValue': {'stringValue': cell}} 
                                   for cell in row]}
                        for row in data
                    ]
                }]
            }]
        }
        result = self.service.spreadsheets().create(body=spreadsheet).execute()
        return result['spreadsheetId']
    
    def _add_chart(self, spreadsheet_id: str, chart_type: str, range: str) -> dict:
        """차트 추가"""
        requests = [{
            'addChart': {
                'chart': {
                    'spec': {
                        'title': 'Data Chart',
                        'basicChart': {
                            'chartType': chart_type.upper(),
                            'domains': [{'domain': {'sourceRange': {'sources': [{'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 10}]}}}]
                        }
                    }
                }
            }
        }]
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, 
            body={'requests': requests}
        ).execute()
        return {'status': 'chart_added'}
```

**검증 방법**:
```bash
pytest tests/agents/test_sheets_agent.py -v
curl -X POST http://localhost:8000/api/v1/tasks \
  -d '{"prompt": "Create sales data spreadsheet", "task_type": "sheets"}'
```

---

#### **Day 4-5: Slides Agent 구현**
```python
# backend/app/agents/slides_agent.py
from googleapiclient.discovery import build

class SlidesAgent(BaseAgent):
    def __init__(self, credentials):
        self.credentials = credentials
        self.service = build('slides', 'v1', credentials=credentials)
        
        tools = [
            Tool(name="create_presentation", func=self._create_presentation),
            Tool(name="add_slide", func=self._add_slide),
            Tool(name="add_text", func=self._add_text)
        ]
        
        super().__init__(agent_type="slides", tools=tools)
    
    def _create_presentation(self, title: str) -> str:
        """프레젠테이션 생성"""
        presentation = {'title': title}
        result = self.service.presentations().create(body=presentation).execute()
        return result['presentationId']
    
    def _add_slide(self, presentation_id: str, layout: str) -> str:
        """슬라이드 추가"""
        requests = [{
            'createSlide': {
                'slideLayoutReference': {'predefinedLayout': layout}
            }
        }]
        response = self.service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()
        return response['replies'][0]['createSlide']['objectId']
    
    def _add_text(self, presentation_id: str, slide_id: str, text: str) -> dict:
        """텍스트 추가"""
        requests = [{
            'insertText': {
                'objectId': slide_id,
                'text': text,
                'insertionIndex': 0
            }
        }]
        self.service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={'requests': requests}
        ).execute()
        return {'status': 'text_added'}
```

---

### **Week 4: Mobile Backend 통합**

#### **Day 1-2: Mobile Data Models**
```dart
// mobile/lib/core/data/models/user_model.dart
import 'package:json_annotation/json_annotation.dart';

part 'user_model.g.dart';

@JsonSerializable()
class UserModel {
  final String id;
  final String email;
  final String name;
  final String? avatarUrl;
  final DateTime createdAt;
  
  UserModel({
    required this.id,
    required this.email,
    required this.name,
    this.avatarUrl,
    required this.createdAt,
  });
  
  factory UserModel.fromJson(Map<String, dynamic> json) => _$UserModelFromJson(json);
  Map<String, dynamic> toJson() => _$UserModelToJson(this);
  
  UserModel copyWith({String? name, String? avatarUrl}) {
    return UserModel(
      id: id,
      email: email,
      name: name ?? this.name,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      createdAt: createdAt,
    );
  }
}
```

```dart
// mobile/lib/features/tasks/data/models/task_model.dart
@JsonSerializable()
class TaskModel {
  final String id;
  final String userId;
  final String prompt;
  final String taskType;
  final String status;
  final Map<String, dynamic>? result;
  final String? errorMessage;
  final String? documentUrl;
  final DateTime createdAt;
  final DateTime? completedAt;
  
  factory TaskModel.fromJson(Map<String, dynamic> json) => _$TaskModelFromJson(json);
  Map<String, dynamic> toJson() => _$TaskModelToJson(this);
}
```

**Build runner 실행**:
```bash
cd mobile
flutter pub run build_runner build
```

---

#### **Day 3-4: ApiClient 구현**
```dart
// mobile/lib/core/network/api_client.dart
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiClient {
  late final Dio _dio;
  final FlutterSecureStorage _storage;
  
  ApiClient(this._storage) {
    _dio = Dio(BaseOptions(
      baseUrl: 'https://your-backend.run.app/api/v1',
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
    ));
    
    // Token Interceptor
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await _storage.read(key: 'access_token');
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          // Token refresh logic
          final refreshed = await _refreshToken();
          if (refreshed) {
            return handler.resolve(await _retry(error.requestOptions));
          }
        }
        handler.next(error);
      },
    ));
  }
  
  Future<Response> get(String path) => _dio.get(path);
  Future<Response> post(String path, {dynamic data}) => _dio.post(path, data: data);
  Future<Response> put(String path, {dynamic data}) => _dio.put(path, data: data);
  Future<Response> delete(String path) => _dio.delete(path);
  
  Future<bool> _refreshToken() async {
    final refreshToken = await _storage.read(key: 'refresh_token');
    if (refreshToken == null) return false;
    
    try {
      final response = await _dio.post('/auth/refresh', data: {'refresh_token': refreshToken});
      await _storage.write(key: 'access_token', value: response.data['access_token']);
      return true;
    } catch (e) {
      return false;
    }
  }
  
  Future<Response> _retry(RequestOptions options) {
    return _dio.fetch(options);
  }
}
```

---

#### **Day 5: Mobile OAuth 구현**
```dart
// mobile/lib/features/auth/data/repositories/auth_repository.dart
import 'package:google_sign_in/google_sign_in.dart';

class AuthRepository {
  final ApiClient _apiClient;
  final FlutterSecureStorage _storage;
  final GoogleSignIn _googleSignIn;
  
  AuthRepository(this._apiClient, this._storage)
      : _googleSignIn = GoogleSignIn(
          scopes: [
            'email',
            'https://www.googleapis.com/auth/drive.file',
            'https://www.googleapis.com/auth/documents',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/presentations',
          ],
        );
  
  Future<UserModel?> signInWithGoogle() async {
    try {
      // 1. Google Sign-In
      final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
      if (googleUser == null) throw Exception('Sign-in cancelled');
      
      // 2. Get tokens
      final GoogleSignInAuthentication googleAuth = await googleUser.authentication;
      
      // 3. Send to backend
      final response = await _apiClient.post('/auth/google/mobile', data: {
        'id_token': googleAuth.idToken,
        'access_token': googleAuth.accessToken,
      });
      
      // 4. Store tokens
      await _storage.write(key: 'access_token', value: response.data['access_token']);
      await _storage.write(key: 'refresh_token', value: response.data['refresh_token']);
      
      // 5. Return user
      return UserModel.fromJson(response.data['user']);
    } catch (e) {
      throw AuthException('Google Sign-In failed: $e');
    }
  }
  
  Future<void> signOut() async {
    await _googleSignIn.signOut();
    await _storage.deleteAll();
  }
  
  Future<UserModel?> getCurrentUser() async {
    final token = await _storage.read(key: 'access_token');
    if (token == null) return null;
    
    try {
      final response = await _apiClient.get('/users/me');
      return UserModel.fromJson(response.data);
    } catch (e) {
      return null;
    }
  }
}
```

**Backend Endpoint 추가 필요**:
```python
# backend/app/api/v1/auth.py
@router.post("/google/mobile")
async def google_mobile_auth(
    id_token: str = Body(...),
    access_token: str = Body(...),
    db: Session = Depends(get_db)
):
    """Mobile Google OAuth verification"""
    # Verify id_token with Google
    # Create/update user
    # Return JWT tokens
    pass
```

---

## **Week 5: Memory & Citation 연결**

### 목표
- ✅ Memory Manager 전체 연결
- ✅ Citation Tracker 연결

---

#### **Day 1-2: Memory Manager 연결**
```python
# backend/app/agents/base.py
from app.memory.manager import MemoryManager  # ✅ import 추가

class BaseAgent:
    def __init__(self, ...):
        # ❌ 기존
        # self.memory = ConversationMemory(...)
        
        # ✅ 변경
        self.memory_manager = MemoryManager(
            conversation_memory=ConversationMemory(...),
            vector_memory=VectorMemory(...)
        )
    
    async def execute(self, prompt: str):
        # Context retrieval
        context = await self.memory_manager.get_relevant_context(prompt)
        
        # Agent execution with context
        result = await self.agent.run(prompt, context=context)
        
        # Save to memory
        await self.memory_manager.save_conversation(prompt, result)
        await self.memory_manager.save_to_vector_store(prompt, result)
        
        return result
```

**검증 방법**:
```bash
# Multi-turn conversation 테스트
curl -X POST http://localhost:8000/api/v1/tasks -d '{"prompt": "AI trends", ...}'
# 같은 user_id로 follow-up
curl -X POST http://localhost:8000/api/v1/tasks -d '{"prompt": "More details", ...}'
# Context가 유지되는지 확인
```

---

#### **Day 3-5: Citation Tracker 연결**
```python
# backend/app/agents/research_agent.py
from app.services.citation.tracker import CitationTracker  # ✅ import

class ResearchAgent(BaseAgent):
    def __init__(self, ...):
        super().__init__(...)
        self.citation_tracker = CitationTracker()  # ✅ 초기화
    
    async def research(self, prompt: str):
        # Web scraping
        sources = await self._scrape_web(prompt)
        
        # ❌ 기존: 직접 Citation 생성
        # citations = [{'url': s.url, 'title': s.title} for s in sources]
        
        # ✅ 변경: Citation Tracker 사용
        for source in sources:
            self.citation_tracker.add_source(
                url=source.url,
                title=source.title,
                content=source.content,
                timestamp=datetime.now()
            )
        
        # LLM analysis with citations
        citations = self.citation_tracker.get_all_citations(style='apa')
        result = await self._analyze_with_llm(sources, citations)
        
        return result
```

**검증 방법**:
```bash
# Research task 실행 후 DB 확인
curl -X POST http://localhost:8000/api/v1/tasks \
  -d '{"prompt": "Research AI ethics", "task_type": "research"}'

# DB에서 citations 확인
psql -d agenthq -c "SELECT * FROM citations WHERE task_id='...'"
```

---

## **Week 6: Mobile Offline & 통합 테스트**

### 목표
- ✅ Mobile Offline Mode 구현
- ✅ End-to-End 통합 테스트
- ✅ 성능 최적화

---

#### **Day 1-2: Mobile Offline Storage**
```dart
// mobile/lib/core/storage/storage_service.dart
import 'package:hive_flutter/hive_flutter.dart';

class StorageService {
  late Box<TaskModel> _taskBox;
  late Box<UserModel> _userBox;
  
  Future<void> init() async {
    await Hive.initFlutter();
    Hive.registerAdapter(TaskModelAdapter());
    Hive.registerAdapter(UserModelAdapter());
    
    _taskBox = await Hive.openBox<TaskModel>('tasks');
    _userBox = await Hive.openBox<UserModel>('user');
  }
  
  // Cache tasks
  Future<void> cacheTasks(List<TaskModel> tasks) async {
    await _taskBox.clear();
    for (var task in tasks) {
      await _taskBox.put(task.id, task);
    }
  }
  
  List<TaskModel> getCachedTasks() {
    return _taskBox.values.toList();
  }
  
  // Cache user
  Future<void> cacheUser(UserModel user) async {
    await _userBox.put('current', user);
  }
  
  UserModel? getCachedUser() {
    return _userBox.get('current');
  }
}
```

```dart
// mobile/lib/features/tasks/presentation/providers/task_provider.dart
final taskProvider = StateNotifierProvider<TaskNotifier, TaskState>((ref) {
  final repository = ref.watch(taskRepositoryProvider);
  final storage = ref.watch(storageServiceProvider);
  return TaskNotifier(repository, storage);
});

class TaskNotifier extends StateNotifier<TaskState> {
  final TaskRepository _repository;
  final StorageService _storage;
  
  Future<void> loadTasks() async {
    state = state.copyWith(isLoading: true);
    
    try {
      // Try online first
      final tasks = await _repository.getTasks();
      await _storage.cacheTasks(tasks);  // ✅ Cache
      state = TaskState(tasks: tasks);
    } catch (e) {
      // Fallback to offline
      final cachedTasks = _storage.getCachedTasks();  // ✅ Offline
      state = TaskState(
        tasks: cachedTasks,
        isOffline: true,
        error: 'Using cached data'
      );
    }
  }
}
```

---

#### **Day 3-4: 통합 테스트**
```python
# tests/integration/test_end_to_end.py
import pytest
from app.main import app
from fastapi.testclient import TestClient

@pytest.mark.integration
def test_full_workflow():
    """Desktop → Backend → Google API → Database"""
    client = TestClient(app)
    
    # 1. Login
    response = client.post("/api/v1/auth/google/mock", json={"email": "test@example.com"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    
    # 2. Create task
    response = client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "Create sales report", "task_type": "docs"}
    )
    assert response.status_code == 201
    task_id = response.json()["task_id"]
    
    # 3. Poll task
    import time
    max_wait = 60
    for _ in range(max_wait):
        response = client.get(f"/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {token}"})
        status = response.json()["status"]
        if status in ["completed", "failed"]:
            break
        time.sleep(1)
    
    # 4. Verify result
    assert status == "completed"
    result = response.json()
    assert "document_url" in result
    assert result["document_url"].startswith("https://docs.google.com")
```

```dart
// mobile/test/integration/auth_flow_test.dart
void main() {
  testWidgets('Full auth flow', (WidgetTester tester) async {
    await tester.pumpWidget(App());
    
    // 1. Splash screen
    expect(find.byType(SplashScreen), findsOneWidget);
    await tester.pumpAndSettle();
    
    // 2. Login screen
    expect(find.byType(LoginScreen), findsOneWidget);
    
    // 3. Google Sign-In button
    await tester.tap(find.text('Google로 로그인'));
    await tester.pumpAndSettle();
    
    // 4. Home screen
    expect(find.byType(HomeScreen), findsOneWidget);
  });
}
```

---

#### **Day 5: 성능 최적화**
```python
# backend/app/api/v1/tasks.py
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache

@router.get("/tasks")
@cache(expire=60)  # ✅ 1분 캐싱
async def get_tasks(
    skip: int = 0,
    limit: int = 20,  # ✅ Pagination
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tasks = db.query(Task).filter(
        Task.user_id == current_user.id
    ).order_by(
        Task.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    return tasks
```

```dart
// mobile - Image caching
import 'package:cached_network_image/cached_network_image.dart';

CachedNetworkImage(
  imageUrl: user.avatarUrl,
  placeholder: (context, url) => CircularProgressIndicator(),
  errorWidget: (context, url, error) => Icon(Icons.error),
  cacheManager: CustomCacheManager(),  // ✅ 캐싱
)
```

---

## 📊 성공 지표 (Definition of Done)

### Week 1-2 완료 조건
- [ ] ✅ `pytest tests/` 전체 통과 (90%+ coverage)
- [ ] ✅ Agent 초기화 시 `AttributeError` 없음
- [ ] ✅ Celery Task 성공률 95%+
- [ ] ✅ Google API 호출 성공
- [ ] ✅ Alembic migration 오류 없음

### Week 3-4 완료 조건
- [ ] ✅ Sheets Agent → Spreadsheet 생성 성공
- [ ] ✅ Slides Agent → Presentation 생성 성공
- [ ] ✅ Mobile → Backend API 통신 성공
- [ ] ✅ Mobile Google Sign-In 성공
- [ ] ✅ Mobile Task 생성/조회 성공

### Week 5-6 완료 조건
- [ ] ✅ Multi-turn conversation context 유지
- [ ] ✅ Citation 자동 생성 및 DB 저장
- [ ] ✅ Mobile Offline Mode 동작
- [ ] ✅ Desktop ↔ Mobile 데이터 동기화
- [ ] ✅ E2E 테스트 전체 통과

---

## 🚨 리스크 관리

### High Risk
1. **Google API 할당량 초과**  
   - 해결책: Free Tier 모니터링, 필요 시 유료 전환

2. **LLM API 비용 폭증**  
   - 해결책: LangFuse로 비용 추적, Prompt 최적화

3. **Mobile OAuth iOS 인증서 문제**  
   - 해결책: Android 우선 개발, iOS는 Week 4 후반

### Medium Risk
4. **Hive Migration 데이터 손실**  
   - 해결책: Backup 스크립트, Rollback 계획

5. **WebSocket 재연결 누락**  
   - 해결책: Heartbeat 추가, Auto-reconnect 로직

---

## 📚 참고 문서

- [PHASE_0-4_AUDIT.md](PHASE_0-4_AUDIT.md) - 버그 상세 목록
- [PHASE_3-1_STATUS.md](PHASE_3-1_STATUS.md) - Mobile 현황
- [ARCHITECTURE.md](ARCHITECTURE.md) - 시스템 아키텍처
- [README.md](../README.md) - 프로젝트 전체 개요

---

## 💡 다음 단계 (Week 7+)

### Phase 5: Advanced Features
- [ ] WebSocket 실시간 업데이트
- [ ] Team Collaboration (Multi-user)
- [ ] Template Marketplace
- [ ] Advanced Analytics

### Phase 6: Enterprise
- [ ] Multi-tenant Support
- [ ] SSO Integration
- [ ] Audit Logs
- [ ] RBAC (Role-Based Access Control)

---

**작성자**: Planner Agent  
**작성일**: 2026-02-12  
**버전**: 1.0  
**상태**: ✅ Ready for Execution
