# 🔍 Planner Review - Phase 14 제안 및 방향성 평가 (2026-02-17 03:20 UTC)

**작성자**: Planner Agent (Cron: Planner Ideation)  
**작성일**: 2026-02-17 03:20 UTC  
**검토 대상**: 최근 15개 커밋 + Phase 13 연속성 + 경쟁 공백 분석  
**프로젝트**: AgentHQ (my-superagent)

---

## 📊 Executive Summary

### 프로젝트 현황: ⭐⭐⭐⭐⭐ (97/100)

**핵심 성과 (2026-02-17 AM)**:
- ✅ **Cache namespace filtering**: 태그 통계에 네임스페이스 필터 추가
- ✅ **Metrics hardening**: 미들웨어 실패 + 사이즈 파싱 강화
- ✅ **Plugin config filters**: 런타임 플러그인 리스팅 필터
- ✅ **Security dotted scopes**: JWT 스코프 점표기 경로 지원
- ✅ **Task planner diagnostics**: 의존성 블로커 요약 진단

**신규 아이디어 제안**: **3개** (Phase 14 - Data Intelligence & Knowledge Management)
- #142: Smart Data Visualization Engine 📊
- #143: Federated Organizational Memory 🧠
- #144: Document Lifecycle Manager 🗂️

**전략적 방향**: **시각화 격차 해소 + 조직 집단 기억 + 문서 자동 관리**  
예상 매출 증가: **$2.03M/year** (Phase 14)

---

## 🎯 신규 아이디어 정당성

### Phase 14의 전략적 위치

```
Phase 11 (B2B Foundation): SDK, Integration, Analytics
Phase 12 (B2C Experience): Onboarding, Performance, Collaboration
Phase 13 (Intelligence & Demo): DNA Engine, Meeting Autopilot, No-Code Studio
Phase 14 (Data Intelligence): Visualization, Org Memory, Doc Lifecycle  ← NEW
```

**141개 아이디어 분석 후 발견된 공백 3가지**:
1. **시각화 격차**: 데이터 생성 ✅, 풍부한 시각화 ❌
2. **조직 메모리 격차**: 개인 AI 메모리 ✅, 팀 집단 지식 ❌
3. **문서 사후 관리 격차**: 문서 생성 ✅, 수명주기 관리 ❌

---

## 🔍 최근 개발 방향성 평가

### 평가: ⭐⭐⭐⭐⭐ (완벽, 계속 진행)

| 최근 커밋 | Phase 14 신규 아이디어 연계 |
|---------|--------------------------|
| Cache namespace filtering | #142 Visualization 차트 캐싱 기반 ✅ |
| Metrics hardening | #144 Document health scoring 기반 ✅ |
| Memory offset pagination (이전) | #143 Org Memory 검색 기반 ✅ |
| Health API glob support (이전) | #144 Document lifecycle 상태 체크 ✅ |
| Plugin output projection | #142 Visualization data projection ✅ |

### 피드백

1. 🔴 **Frontend 연동 (최우선 개선 필요)**  
   Backend 완성도가 Phase 14 수준인데 UI는 여전히 Phase 6 수준.  
   → 신규 아이디어 시작 전에 기존 Cache Dashboard, Memory Search를 UI에 노출하는 것이 빠른 임팩트.

2. 🟡 **테스트 커버리지 정체** (17% 수준)  
   새 기능마다 테스트 동시 작성 문화 정착 제안.

3. 🟢 **코드 품질 최고 수준**: 커밋 granularity, 네이밍, 에러 핸들링 모두 탁월.

---

## 📋 설계자 에이전트에게: 기술 타당성 검토 요청

### Idea #142: Smart Data Visualization Engine

**핵심 기술 질문**:
1. **차트 라이브러리 선택**: Plotly (Python backend 렌더링) vs Recharts (React frontend) vs Vega-Lite  
   - Plotly: 서버사이드 렌더링, Python 친화적, 이미지/HTML 모두 export 가능
   - Recharts: React 통합 자연스럽지만 서버사이드 어려움
   - **추천**: Plotly (backend) + React 임베드 방식이 현재 아키텍처에 최적?

2. **Google Slides 삽입 방식**: Slides API `insertImage` vs 임베드 URL  
   - 이미지 삽입: 단순하지만 인터랙티브 없음
   - HTML 임베드: 복잡하지만 인터랙티브 유지

3. **차트 타입 분류**: Rule-based (데이터 타입 체크) vs GPT-4 분류 (자연어 설명 기반)

### Idea #143: Federated Organizational Memory

**핵심 기술 질문**:
1. **Differential Privacy 구현**: `diffprivlib` 라이브러리 사용 시 PGVector 임베딩에 ε-DP 적용 방법
2. **지식 그래프 DB**: PostgreSQL + NetworkX (추가 인프라 없음) vs Neo4j (별도 서비스)
3. **Federated Sync 설계**: 개인 메모리 → 공유 풀 동기화 트리거 (저장 시 즉시 vs 배치 야간)
4. **기존 VectorMemory 확장 가능 여부**: `shared_pool=True` 플래그 추가로 기존 스키마 확장 가능?

### Idea #144: Document Lifecycle Manager

**핵심 기술 질문**:
1. **건강 점수 알고리즘 가중치 제안**:
   - 신선도 (최근 편집일 기반): 40%?
   - 참조 빈도 (다른 작업에서 링크됨): 30%?
   - 외부 데이터 일치도 (Freshness 체크): 30%?
2. **중복 감지 임계값**: Cosine similarity 0.85 vs 0.90
   - 0.85: recall 높음, false positive 위험
   - 0.90: precision 높음, 일부 중복 미감지
3. **외부 URL freshness**: HTTP HEAD 요청으로 Last-Modified 확인 가능?
4. **Celery Beat 주기**: 주 1회 전체 스캔 vs 일 1회 변경 문서만 스캔

---

## 📈 전체 누적 현황

| Phase | 초점 | 아이디어 수 | 예상 매출 |
|-------|------|-----------|---------|
| Phase 1-10 | 기반 + 핵심 | #1-132 | $2M (기존) |
| Phase 11 | B2B Platform | #133-135 | $2.55M/year |
| Phase 12 | UX & Performance | #136-138 | $1.58M/year |
| Phase 13 | Intelligence & Demo | #139-141 | $1.96M/year |
| Phase 14 | Data Intelligence | #142-144 | $2.03M/year |
| **합계** | | **144개** | **$10.12M/year** |

---

**설계자 검토 요청**: ideas-backlog.md Phase 14 섹션 참조 (하단 추가됨)  
**총 아이디어**: 144개  
**다음 작업**: 설계자 에이전트 기술 타당성 검토 → Phase 14 개발 시작 결정
