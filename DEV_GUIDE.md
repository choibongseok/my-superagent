# AgentHQ 개발 환경 가이드

로컬 개발 환경을 빠르게 구성하고 실행하는 가이드입니다.

## 🚀 빠른 시작 (원클릭 실행)

### 1. 사전 요구사항

- **Docker Desktop** 설치 필수
  - Mac: https://docs.docker.com/desktop/install/mac-install/
  - Windows: https://docs.docker.com/desktop/install/windows-install/
  - Linux: https://docs.docker.com/desktop/install/linux-install/

- **Git** 설치

### 2. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/choibongseok/my-superagent.git
cd my-superagent

# .env 파일 생성 (자동)
# dev.sh 실행 시 자동으로 생성됨
```

### 3. API 키 설정

`backend/.env` 파일을 열고 다음 API 키를 설정하세요:

```bash
# 필수 API 키
OPENAI_API_KEY=sk-your-openai-api-key

# Google OAuth (선택, 나중에 설정 가능)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret

# LangFuse (선택, 모니터링용)
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
```

### 4. 실행

```bash
# 개발 환경 시작 (원클릭)
./dev.sh

# 개발 환경 종료
./stop.sh
```

## 📡 서비스 URL

실행 후 다음 URL에서 서비스에 접근할 수 있습니다:

| 서비스 | URL | 설명 |
|--------|-----|------|
| Backend API | http://localhost:8000 | FastAPI 백엔드 |
| API Docs (Swagger) | http://localhost:8000/docs | API 문서 |
| API Docs (ReDoc) | http://localhost:8000/redoc | API 문서 (대체) |
| Celery Flower | http://localhost:5555 | Celery 작업 모니터링 |
| PostgreSQL | localhost:5432 | 데이터베이스 |
| Redis | localhost:6379 | 캐시 & 메시지 브로커 |

## 🏗️ 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                         AgentHQ                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Backend    │  │Celery Worker │  │Celery Flower │     │
│  │   (FastAPI)  │  │   (Agents)   │  │ (Monitoring) │     │
│  │   :8000      │  │              │  │   :5555      │     │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘     │
│         │                 │                                 │
│         │                 │                                 │
│  ┌──────┴─────────────────┴───────┐                        │
│  │         PostgreSQL              │                        │
│  │       (with pgvector)           │                        │
│  │          :5432                  │                        │
│  └────────────┬────────────────────┘                        │
│               │                                              │
│  ┌────────────┴────────────────────┐                        │
│  │          Redis                  │                        │
│  │   (Cache & Message Broker)      │                        │
│  │          :6379                  │                        │
│  └─────────────────────────────────┘                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 유용한 명령어

### Docker Compose 명령어

```bash
# 로그 확인 (전체)
docker-compose logs -f

# 특정 서비스 로그
docker logs -f agenthq-backend
docker logs -f agenthq-celery-worker
docker logs -f agenthq-postgres

# 서비스 재시작
docker-compose restart backend
docker-compose restart celery-worker

# 컨테이너 상태 확인
docker-compose ps

# 서비스 중지 (데이터 보존)
./stop.sh

# 서비스 중지 및 데이터 삭제
docker-compose down -v
```

### 데이터베이스 명령어

```bash
# PostgreSQL 접속
docker exec -it agenthq-postgres psql -U agenthq

# 데이터베이스 마이그레이션
docker exec agenthq-backend alembic upgrade head

# 마이그레이션 롤백
docker exec agenthq-backend alembic downgrade -1

# 새 마이그레이션 생성
docker exec agenthq-backend alembic revision --autogenerate -m "description"
```

### Redis 명령어

```bash
# Redis CLI 접속
docker exec -it agenthq-redis redis-cli

# Redis 모니터링
docker exec -it agenthq-redis redis-cli MONITOR

# 캐시 삭제
docker exec -it agenthq-redis redis-cli FLUSHDB
```

### Celery 명령어

```bash
# Celery worker 상태 확인
docker exec agenthq-celery-worker celery -A app.agents.celery_app inspect ping

# 활성 작업 확인
docker exec agenthq-celery-worker celery -A app.agents.celery_app inspect active

# 예약된 작업 확인
docker exec agenthq-celery-worker celery -A app.agents.celery_app inspect scheduled
```

## 🧪 테스트

### Backend 테스트

```bash
# 테스트 실행
docker exec agenthq-backend pytest

# 커버리지 포함
docker exec agenthq-backend pytest --cov=app --cov-report=html

# 특정 테스트 파일
docker exec agenthq-backend pytest tests/test_api.py

# 상세 출력
docker exec agenthq-backend pytest -v
```

### API 테스트 (수동)

```bash
# Health check
curl http://localhost:8000/health

# API 문서
open http://localhost:8000/docs

# 작업 생성 테스트
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "AI에 대한 리서치를 해줘",
    "task_type": "research"
  }'
```

## 📱 Flutter 모바일 개발

### 환경 설정

```bash
cd mobile

# 의존성 설치
flutter pub get

# 코드 생성 (Riverpod, etc.)
flutter pub run build_runner build --delete-conflicting-outputs

# 애널라이즈
flutter analyze
```

### 실행

```bash
# iOS 시뮬레이터
flutter run -d iPhone

# Android 에뮬레이터
flutter run -d emulator

# 디바이스 확인
flutter devices

# Hot reload (실행 중 r 입력)
# Hot restart (실행 중 R 입력)
```

## 🖥️ Desktop 개발 (Tauri)

### 환경 설정

```bash
cd desktop

# 의존성 설치
npm install

# Tauri CLI 설치
cargo install tauri-cli
```

### 실행

```bash
# 개발 모드
npm run tauri dev

# 빌드
npm run tauri build
```

## 🐛 문제 해결

### Docker 관련

**문제**: `Cannot connect to Docker daemon`
```bash
# Docker Desktop이 실행 중인지 확인
# Mac: 상단 메뉴바에 Docker 아이콘 확인
# Windows: 시스템 트레이에 Docker 아이콘 확인
```

**문제**: `Port already in use`
```bash
# 포트 사용 중인 프로세스 확인
lsof -i :8000  # Backend
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis

# 프로세스 종료
kill -9 <PID>
```

**문제**: `Database migration failed`
```bash
# 데이터베이스 초기화
docker-compose down -v
./dev.sh
```

### Backend 관련

**문제**: `ModuleNotFoundError`
```bash
# 컨테이너 재빌드
docker-compose build --no-cache backend
docker-compose up -d
```

**문제**: `OpenAI API key not found`
```bash
# .env 파일 확인
cat backend/.env | grep OPENAI_API_KEY

# .env 편집 후 재시작
./stop.sh
./dev.sh
```

### Celery Worker 관련

**문제**: `Celery worker not responding`
```bash
# Worker 로그 확인
docker logs agenthq-celery-worker

# Worker 재시작
docker-compose restart celery-worker

# Worker 상태 확인
docker exec agenthq-celery-worker celery -A app.agents.celery_app inspect ping
```

## 📊 모니터링

### Celery Flower

Celery 작업 모니터링 대시보드: http://localhost:5555

기능:
- 실시간 작업 모니터링
- Worker 상태 확인
- 작업 실행 이력
- 작업 재시도/취소

### 로그 수집

```bash
# 모든 서비스 로그를 파일로 저장
docker-compose logs > logs.txt

# 실시간 로그 필터링
docker-compose logs -f | grep ERROR
docker-compose logs -f backend | grep -i "celery"
```

## 🔒 보안

### 개발 환경 보안 주의사항

1. **API 키 관리**
   - `.env` 파일은 절대 Git에 커밋하지 마세요
   - 실제 프로덕션 키를 개발에 사용하지 마세요
   - OpenAI 조직 계정 사용 시 별도 개발 키 발급

2. **데이터베이스**
   - 개발 환경 비밀번호는 `agenthq_dev_password` 사용
   - 프로덕션에서는 반드시 강력한 비밀번호 사용

3. **포트 노출**
   - 개발 환경은 localhost에서만 실행
   - 외부 네트워크 노출 금지

## 🚢 프로덕션 배포

프로덕션 배포는 별도 문서 참조:
- AWS ECS 배포: `docs/DEPLOYMENT_AWS.md`
- Kubernetes 배포: `docs/DEPLOYMENT_K8S.md`
- Docker Swarm: `docs/DEPLOYMENT_SWARM.md`

## 📚 추가 문서

- [Phase 0: LangChain/LangFuse](docs/PHASE_0_IMPLEMENTATION.md)
- [Phase 1: Core Agents](docs/PHASE_1_IMPLEMENTATION.md)
- [Phase 2: Intelligence & Memory](docs/PHASE_2_IMPLEMENTATION.md)
- [Phase 3: Mobile Client](docs/PHASE_3_IMPLEMENTATION.md)
- [API 문서](http://localhost:8000/docs) - 실행 후 접속

## 💬 질문 & 지원

- GitHub Issues: https://github.com/choibongseok/my-superagent/issues
- 개발팀 Slack: #agenthq-dev

---

**Happy Coding! 🚀**
