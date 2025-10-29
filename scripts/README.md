# AgentHQ Scripts

개발 환경 관리를 위한 스크립트 모음입니다.

## 📜 스크립트 목록

### 개발 환경 관리

#### `dev.sh` - 개발 환경 시작
원클릭으로 전체 개발 환경을 시작합니다.

```bash
./dev.sh
```

**실행 내용**:
- Docker 환경 확인
- .env 파일 자동 생성
- Docker Compose 빌드 및 시작
- PostgreSQL, Redis health check
- 데이터베이스 마이그레이션 실행
- Backend API, Celery Worker 시작
- 서비스 상태 확인

**시작되는 서비스**:
- Backend API (http://localhost:8000)
- API Docs (http://localhost:8000/docs)
- Celery Flower (http://localhost:5555)
- PostgreSQL (localhost:5432)
- Redis (localhost:6379)

#### `stop.sh` - 개발 환경 종료
모든 서비스를 안전하게 종료합니다.

```bash
./scripts/stop.sh
```

**실행 내용**:
- 모든 Docker 컨테이너 중지
- 데이터는 Docker volume에 보존

## 🔧 사용법

### 기본 사용
```bash
# 시작
./scripts/dev.sh

# 종료
./scripts/stop.sh
```

### 문제 해결
```bash
# 로그 확인
docker-compose logs -f

# 특정 서비스 재시작
docker-compose restart backend

# 데이터 완전 삭제 후 재시작
docker-compose down -v
./scripts/dev.sh
```

## 📚 추가 정보

- 상세 가이드: [DEV_GUIDE.md](../docs/DEV_GUIDE.md)
- 문제 해결: [DEV_GUIDE.md - 문제 해결](../docs/DEV_GUIDE.md#-문제-해결)
