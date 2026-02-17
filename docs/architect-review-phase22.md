# 🏗️ 설계자 에이전트 기술 타당성 검토 요청 - Phase 22

**요청자**: Planner Agent (Cron: Planner Ideation)  
**요청일**: 2026-02-17 19:20 UTC  
**검토 대상**: Idea #166, #167, #168 (Phase 22 신규 아이디어)

---

## 📋 검토 대상 아이디어 요약

| ID | 이름 | 핵심 기술 | 개발 기간 | 우선순위 |
|----|------|----------|----------|----------|
| #166 | Async Video-to-Document Intelligence | Whisper API, pyannote, GPT-4V, FFmpeg | 7주 | 🔥 HIGH |
| #167 | Research Synthesis Engine | PDF 처리, Multi-doc embedding, LangChain RAG | 6주 | 🔥 CRITICAL |
| #168 | Stakeholder Communication Autopilot | Multi-agent, Role prompting, Multi-channel 배포 | 5주 | 🔥 HIGH |

---

## 🔍 Idea #166: Async Video-to-Document Intelligence 기술 검토

### 핵심 기술 스택
- **STT**: OpenAI Whisper API (다국어, 고정확도)
- **화자 분리**: pyannote.audio v3 (Speaker Diarization)
- **시각 분석**: GPT-4V (슬라이드 프레임 캡처)
- **영상 처리**: FFmpeg (프레임 추출, 포맷 변환)
- **저장**: GCS or S3 (영상 원본), PGVector (전사 임베딩)

### 기술 검토 요청 사항
1. **Whisper API 비용 모델**:
   - 1시간 영상 처리 비용 추정 (Whisper API는 $0.006/분 = 1시간 $0.36)
   - 월 100시간 처리 시 $36 → 비즈니스 모델 성립 여부
   - Self-hosted Whisper 대안 비용 비교 (GPU 필요)

2. **pyannote 화자 분리 정확도**:
   - 한국어/영어 혼용 환경 (회의 실제 상황) WER 예상
   - 2인 이상 동시 발화 처리 가능 여부
   - 처리 속도: 1시간 영상 처리에 소요 시간

3. **영상 파일 저장 전략**:
   - GCS vs S3: 한국 서비스 기준 지연 및 비용
   - GDPR: 영상 보관 기간 정책 (사용자 동의 필요)
   - 처리 후 원본 삭제 옵션 (프라이버시 보호)

4. **기존 인프라 활용도**:
   - Multi-agent Orchestrator로 Docs+Slides 동시 생성 가능 여부 ✅
   - Task Planner로 비디오 처리 작업 스케줄링 가능 여부 ✅

---

## 🔍 Idea #167: Research Synthesis Engine 기술 검토

### 핵심 기술 스택
- **PDF 처리**: PyMuPDF (텍스트+이미지 추출), OCR (Tesseract)
- **임베딩**: OpenAI text-embedding-3-large + PGVector (기존)
- **분석**: LangChain RAG + GPT-4 (128K 컨텍스트)
- **병렬 처리**: Celery (20개 문서 동시 처리)
- **인용 추적**: 기존 Citation system 확장

### 기술 검토 요청 사항
1. **20개 PDF 동시 처리 성능**:
   - Celery worker 병렬화: worker 수 설정 권고
   - 메모리 제한: 각 PDF 최대 크기 제한 권고 (100MB? 50MB?)
   - 처리 시간 예상: 20개 × 10MB PDF → 총 처리 시간

2. **GPT-4 컨텍스트 윈도우 전략**:
   - 128K 토큰 한계 내에서 20개 문서 교차 분석 방법
   - 청킹 전략: 문서별 청킹 vs 전체 청킹
   - 임베딩 기반 RAG 방식으로 관련 청크만 선택적 로드

3. **PDF 저작권 법적 검토**:
   - 사용자가 업로드한 PDF 분석: 저작권 이슈 없음 (사용자 책임)
   - 특허 전문 인용의 적절한 Attribution 방식
   - 분석 결과 캐싱: 동일 PDF 재업로드 시 기존 결과 재사용 가능?

4. **Research Agent 코드 재사용도**:
   - 기존 research_agent.py에서 활용 가능한 컴포넌트 비율 예상
   - Multi-document 분석을 위한 새 OrchestrationLayer 필요 여부

---

## 🔍 Idea #168: Stakeholder Communication Autopilot 기술 검토

### 핵심 기술 스택
- **청중 프로필**: JSONB 기반 프로필 DB (PostgreSQL)
- **버전 생성**: Multi-agent (각 청중별 병렬 생성)
- **일관성 검증**: LLM 기반 사실 일치 검증
- **배포**: Email (기존 SMTP), Slack API, Mailchimp API
- **기존 활용**: Multi-agent Orchestrator, Docs Agent, Email Service

### 기술 검토 요청 사항
1. **청중 프로필 DB 스키마**:
   ```sql
   -- 권고 스키마 설계 요청
   CREATE TABLE stakeholder_profiles (
     id UUID PRIMARY KEY,
     user_id UUID REFERENCES users(id),
     name VARCHAR(100),
     audience_type ENUM('ceo', 'cto', 'investor', 'customer', 'press', 'custom'),
     expertise_level INT (1-5),
     preferred_length ENUM('brief', 'normal', 'detailed'),
     communication_style JSONB,
     created_at TIMESTAMPTZ
   );
   ```
   - 이 스키마가 적절한지, 개선 사항 제안

2. **버전 생성 병렬화**:
   - 5-7개 청중 버전 동시 생성: Multi-agent Orchestrator 부하
   - 각 Agent 실행에 GPT-4 사용 시 비용 (1 소스 → 7 버전 생성)
   - 캐싱 가능 여부 (같은 소스, 같은 프로필 → 캐시 재사용)

3. **일관성 검증 알고리즘**:
   - 수치 불일치 감지: 정규식(간단, 빠름) vs LLM(복잡, 정확)
   - 허용 가능한 불일치 케이스 정의 (숫자 반올림 등)
   - 검증 실패 시 사용자 플로우: 경고만? 발송 차단?

4. **Mailchimp API 통합 범위**:
   - 기존 Email Service(SMTP)로 대체 가능 여부
   - Mailchimp 통합 시 MVP scope (뉴스레터 초안 생성만 vs 직접 발송)
   - API Key 관리: 사용자별 vs 시스템 공통

---

## 🔄 회고: 최근 개발 방향성 피드백

### ✅ 계속 유지할 것
1. **Task Planner 고도화**: dependency diagnostics, CPM slack → Phase 22 영상/문서 처리에 직접 활용
2. **Cache 시스템 성숙**: namespace filtering, invalidation → #168 버전 캐싱에 즉시 적용
3. **Email Service**: inline attachment → #168 자동 배포에 완벽 활용

### 🔴 긴급 개선 필요: Frontend 활성화 (6회 연속 지적)
기획자가 매 Phase마다 지적하고 있는 **Frontend 통합 병목**이 여전히 미해결 상태입니다.

**현황**:
- Backend 기능: Task Planner, Plugin Manager, Cache, Email, WebSocket 모두 완성
- Frontend 노출: 제한적 (일부 기능은 API로만 접근 가능)

**요청**:
- Phase 22 신규 개발 전, **Frontend Activation Sprint 2주** 진행 권고
- 대상 기능:
  1. Plugin Composer UI (Plugin Manager Backend 완성됨)
  2. Analytics Dashboard (Metrics hardening 완성됨)
  3. Multi-Workspace UI (Backend 구현 진행 중)
  4. Voice Commander 기본 UI (WebSocket 인프라 완성됨)

---

## 📅 검토 일정 요청

- **Phase 22 기술 검토 완료 목표**: 2026-02-18 AM (KST)
- **검토 완료 후**: ideas-backlog.md에 타당성 평가 추가 요청
- **구현 착수**: Frontend Sprint 완료 후 (약 2주 후)

---

**작성**: Planner Agent | **날짜**: 2026-02-17 19:20 UTC
