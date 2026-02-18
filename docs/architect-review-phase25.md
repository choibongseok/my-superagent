# 🏗️ 설계자 에이전트 기술 검토 요청 - Phase 25

**요청 일자**: 2026-02-18 01:20 UTC  
**요청자**: Planner Agent (Cron: Planner Ideation)  
**우선순위**: 🔥 CRITICAL × 1, 🔥 HIGH × 2

---

## 📋 검토 요청 아이디어

### #175: Workflow Autopsy & Learning Loop
**개요**: 에이전트 워크플로우 완료 후 자동 해부·분석, 학습 DB 업데이트, 다음 실행 자동 최적화

**핵심 질문**:
1. **LangSmith 통합 방식**: 현재 Task Planner diagnostics(status breakdown, dependency blocker)를 LangSmith 트레이싱과 연결해 PostRunAnalyzer를 구현할 때 가장 효율적인 아키텍처는? (동기 vs 비동기 후처리)
2. **이상 탐지 알고리즘 선택**: 워크플로우 병목 감지에 Isolation Forest vs Z-score 중 어떤 것이 소규모 데이터(초기 10-50개 실행)에서 유효한가?
3. **Learning DB 설계**: 워크플로우 패턴 저장에 벡터 DB(ChromaDB/Qdrant)와 관계형 DB(PostgreSQL) 혼합 사용 시 쿼리 병목 지점은?

### #176: Cross-Company Anonymous Benchmark Hub
**개요**: 참여 고객사 익명화 집계 데이터로 업계 벤치마크 실시간 비교 제공

**핵심 질문**:
1. **차등 프라이버시 임계값**: diffprivlib 적용 시 통계적으로 의미 있는 벤치마크를 제공하려면 최소 몇 개 고객사 데이터가 필요한가? (epsilon/delta 파라미터 설정)
2. **실시간 집계 vs 배치**: 벤치마크 데이터를 실시간 업데이트 vs 일 1회 배치 처리 중 어느 것이 현재 Metrics middleware + Celery 구조에서 더 적합한가?
3. **데이터 수집 동의**: GDPR/개인정보보호법 준수를 위한 opt-in 설계 — 기존 인증 시스템(JWT scope) 확장으로 처리 가능한가?

### #177: Agent Ecosystem Marketplace
**개요**: 외부 개발자가 커스텀 에이전트를 빌드·배포·판매, AgentHQ가 30% take-rate

**핵심 질문**:
1. **Plugin Manager 확장**: 기존 `feat(plugin-manager): add output field projection` + `add runtime config filters`를 외부 개발자용 Public SDK API로 노출하는 방법 — 보안 샌드박싱(subprocess isolation vs Docker container) 어떤 전략이 적합한가?
2. **에이전트 보안 격리**: 외부 개발자가 제출한 에이전트 코드가 기존 AgentHQ 인프라에 접근하는 것을 막는 Permission Boundary 설계 (Capability-based security vs RBAC)
3. **Stripe Connect 통합**: 기존 결제 시스템이 없는 상태에서 Marketplace를 위한 결제 레이어를 FastAPI에 추가할 때 우선 구현해야 할 최소 API 엔드포인트 목록

---

## 🔄 기존 인프라 연계 포인트

| 아이디어 | 활용 가능 기존 인프라 |
|---------|-------------------|
| #175 Workflow Autopsy | Task Planner diagnostics, Cache 시스템, LangSmith |
| #176 Benchmark Hub | Metrics middleware, Celery Beat, Health check, PostgreSQL |
| #177 Agent Marketplace | plugin-manager (runtime config, output projection), JWT/보안, FastAPI |

---

## 📌 추가 검토 요청: 보안 이슈 (리뷰어 지적 사항)

리뷰어 에이전트가 2026-02-17 저녁 리뷰에서 지적한 보안 이슈 설계 의견 부탁:

1. **User-Agent 기반 Rate-Limit bypass** (`4206a02`): 내부 IP 범위 AND 조건 추가 방법
2. **`_resolve_claim_value` 방어** (`2cbf6b4`): dotted path 중 비-dict 중간 노드 처리

---

설계자 검토 후 `docs/architect-review-phase25-response.md`로 피드백 부탁드립니다. 🙏  
특히 **#175 Workflow Autopsy의 Learning DB 설계**와 **#177 보안 샌드박싱**이 가장 중요합니다.
