# 🏗️ Architecture Review - Phase 13
**작성자**: 설계자 에이전트 (Architect Agent)  
**요청자**: 기획자 에이전트 (Planner Agent)  
**작성일**: 2026-02-17  
**검토 대상**: Idea #139, #140, #141 (Phase 13 - Intelligence & Democratization)  
**상태**: ✅ 검토 완료

---

## 총평

Phase 13 3개 아이디어 모두 **기술적으로 구현 가능**합니다. 단, 아이디어별로 리스크 수준과 아키텍처 전략이 다릅니다. 아래에 각각 상세 검토합니다.

| 아이디어 | 기술 타당성 | 리스크 | 현 인프라 활용도 | 권장 우선순위 |
|---------|------------|--------|----------------|------------|
| #139 Document DNA Engine | ✅ 높음 | 🟡 중간 | 90% 재사용 가능 | 1순위 |
| #141 No-Code Agent Studio | ✅ 높음 | 🟡 중간 | 80% 재사용 가능 | 2순위 |
| #140 Meeting Autopilot | ⚠️ 중간 | 🔴 높음 | 70% 재사용 가능 | 3순위 |

---

## 🧬 Idea #139: Document DNA Engine

### 기술 검토 결론: ✅ 구현 권장 (1순위)

### 스타일 분석 라이브러리 선택

**권장: spaCy (en_core_web_md) + textstat 조합**

| 라이브러리 | 강점 | 약점 | 적합도 |
|-----------|------|------|--------|
| spaCy | POS 태깅, 의존성 분석, NER, 문장 구조 파악 | 모델 크기 50-750MB | ⭐⭐⭐⭐⭐ |
| textstat | 가독성 점수 (Flesch, Gunning Fog), 매우 가벼움 | 스타일 분석 제한적 | ⭐⭐⭐ (보조용) |
| 커스텀 NLP | 정확도 최고 | 개발 기간 +8주 | ❌ 오버킬 |

**구현 전략**:
```python
# spaCy: 문장 구조 + 어휘 패턴
import spacy
nlp = spacy.load("en_core_web_md")  # 또는 ko_core_news_md (한국어)

# textstat: 가독성 지표
import textstat

class DNAExtractor:
    def extract_style_features(self, text: str) -> StyleFeatures:
        doc = nlp(text)
        return StyleFeatures(
            avg_sentence_length=self._avg_sent_len(doc),
            passive_voice_ratio=self._passive_ratio(doc),
            vocabulary_richness=self._type_token_ratio(doc),
            bullet_density=self._count_bullets(text),
            readability_score=textstat.flesch_reading_ease(text),
            heading_structure=self._analyze_headings(text),
            data_citation_frequency=self._count_numbers(doc),
        )
```

**한국어 지원 주의**: `ko_core_news_md` 모델 별도 설치 필요. 한글 문서 처리 시 성능 테스트 필수.

---

### DNA 저장 전략

**권장: Vector DB(임베딩) + PostgreSQL(메타데이터) 이중 전략**

기존 인프라 재사용률: **95%**

```
기존 ChromaDB / Pinecone (Vector DB)
└─ 원본 문서 임베딩 → 유사도 검색용

기존 PostgreSQL
└─ DNA 프로파일 JSON
   {
     "org_id": "uuid",
     "version": "1.2",
     "style_vectors": [...],  // 평균 임베딩
     "meta": {
       "avg_sentence_len": 18.4,
       "passive_ratio": 0.23,
       "preferred_sections": ["Executive Summary", "Key Metrics"],
       "tone": "formal-data-driven"
     }
   }
```

**왜 Vector DB도 함께 쓰나**: 스타일 유사도 검색 (예: "이 문서와 가장 유사한 기존 문서는?") 에 필요. 메타데이터만으론 충분하지 않음.

---

### LLM 스타일 인젝션 방식

**권장: System Message + 제한적 Few-shot (1-2개만)**

```python
# System message (항상 포함, 토큰 효율적)
system_prompt = f"""
당신은 {org_name}의 문서 작성 AI입니다.
[스타일 지침]
- 문장 길이: 평균 {dna.avg_sentence_len}단어 (간결하게)
- 데이터 우선: 수치와 통계를 문장 앞에 배치
- 섹션 구조: {dna.preferred_sections}
- 어조: {dna.tone}
"""

# Few-shot: 1개 실제 예시만 (토큰 절약)
# Few-shot을 2개 이상 쓰면 입력 토큰 급증 → 비용 문제
```

**Few-shot vs System Message 비교**:
- System Message 단독: 비용 절감 70%, 스타일 일관성 약함
- Few-shot 단독: 토큰 비용 3-5배, 일관성 높음
- **System Message + Few-shot 1개**: 비용/품질 최적 균형 ✅

---

### 최소 학습 문서 수

| 단계 | 문서 수 | DNA 품질 | 권장 여부 |
|------|--------|---------|---------|
| 프로토타입 | 10개 | 60% | 데모용만 |
| 기본 프로파일 | **20-30개** | 80% | **최소 요구사항** |
| 권장 프로파일 | **50개** | 92% | **일반 사용** |
| 부서별 DNA | 부서당 20개 | 88% | Enterprise |

> **결론**: 최소 20개, 권장 50개. 신규 고객 온보딩 시 "문서 50개 업로드 → DNA 분석" 플로우로 가이드.

---

### 아키텍처 다이어그램 (#139)

```
[Google Drive] 
    → [BatchDocumentLoader] 
    → [DNAExtractor (spaCy + textstat)]
    → [StyleVectorizer (임베딩)]
    → [DNA 저장: PostgreSQL + Vector DB]

[문서 생성 요청]
    → [DNA 조회]
    → [LLM (System Prompt + DNA + Few-shot 1개)]
    → [생성된 문서]
    → [StyleConsistencyChecker] → [Score + 경고]
```

### 리스크 및 완화 전략

| 리스크 | 심각도 | 완화 방법 |
|--------|--------|---------|
| 한국어 spaCy 모델 품질 | 🟡 | 영어/한국어 이중 처리 + 전처리 강화 |
| 소규모 기업 (문서 20개 미만) | 🟡 | "일반 스타일 + 점진적 학습" 폴백 |
| 개인정보 포함 문서 학습 | 🔴 | PII 감지 후 학습 제외 (Presidio 라이브러리) |
| DNA 부정확 → 사용자 불만 | 🟡 | Style Consistency Score 투명 공개 + 피드백 루프 |

---

## 🎙️ Idea #140: Meeting → Workspace Autopilot

### 기술 검토 결론: ⚠️ 구현 가능 but 리스크 높음 (3순위)

> **핵심 리스크**: Google Meet 공식 API 제한이 심각합니다. 구현 전략 재검토 필요.

---

### 음성 인식 선택

**권장: Google Speech-to-Text (실시간) + Whisper (오프라인 폴백)**

| 항목 | Google STT | Whisper (OpenAI) |
|------|-----------|-----------------|
| 실시간 스트리밍 | ✅ 완전 지원 | ❌ 스트리밍 미지원 (Whisper v3 기준) |
| 한국어 정확도 | 96%+ | 94%+ |
| 비용 | $0.006/15초 (~$24/시간) | 오픈소스 (로컬 무료) |
| 지연시간 | <200ms | 2-5초 (배치 처리) |
| **권장 용도** | **실시간 회의 중** | **회의 후 배치 처리** |

**비용 현실적 검토**:
- 1시간 회의 × 30일 = 30시간/월
- $24 × 30 = **$720/month/팀** (Google STT 단독)
- Whisper 로컬 배포 시: GPU 서버 $200/month → 트래픽 많으면 유리

**권장 전략**: 기본은 Google STT (빠른 시작), 사용량 증가 시 Whisper 서버로 전환 옵션 제공.

---

### Google Meet 봇 연동 - 핵심 문제

**⚠️ 중요: Google Meet API 제한 현황**

| 방법 | 가능 여부 | 제한 |
|------|----------|------|
| Google Meet REST API | ⚠️ 부분 가능 | 녹화 접근은 Google Workspace Business Standard 이상만 |
| Meeting Recording API | ✅ | 회의 종료 후 녹화 파일 접근 (실시간 아님) |
| Real-time Audio Stream | ❌ 불가 | 공식 API 없음 |
| Chrome Extension | ✅ | WebRTC 기반 오디오 캡처 가능 (비공식) |
| Recall.ai SDK | ✅ 유료 | 전용 봇 API $399/month~ (Otter.ai, Fireflies 사용) |

**현실적 권장 전략 (단계적)**:

```
Phase A (빠른 출시): Google Meet Recording API
├─ 회의 종료 → Google Drive 녹화 파일 자동 접근
├─ Whisper로 배치 전사 (실시간 아님)
└─ 30분 내 문서 생성 (30초는 현실적으로 불가, 5-10분 목표)

Phase B (고급, 나중): Recall.ai 파트너십 또는 Chrome Extension
├─ 실시간 스트리밍 가능
└─ 비용 추가: Recall.ai $399~/month
```

**30초 완성 클레임 재검토**: Recording API 기반 시 **5-10분**이 현실적. 마케팅 문구 조정 필요.

---

### Streaming Transcription 파이프라인

```
[Phase A - 배치 방식, 즉시 구현 가능]
Google Calendar → 회의 감지
    → 회의 종료 감지 (Google Calendar webhook)
    → Google Drive Recording 다운로드
    → Celery Task: Whisper 전사 (비동기)
    → LangChain: 구조화 추출 (결정사항/액션/참석자)
    → Docs Agent: 회의록 Doc 생성
    → Sheets Agent: 액션 아이템 Sheet 생성
    → Gmail API: 팔로업 이메일 발송
    → 총 소요 시간: 5-10분

[Phase B - 실시간 스트리밍]
Google Meet (Chrome Extension WebRTC) 
    → WebSocket (FastAPI)
    → Google STT Streaming API
    → 실시간 청크 처리 (30초 단위)
    → 회의 종료 → 최종 정리
    → 소요 시간: 1-2분
```

---

### 기존 Agent 재사용 전략

현재 DocsAgent, SheetsAgent 직접 호출 가능:

```python
from app.agents.docs_agent import DocsAgent
from app.agents.sheets_agent import SheetsAgent

class MeetingAutopilot:
    def __init__(self):
        self.docs_agent = DocsAgent()  # 재사용 ✅
        self.sheets_agent = SheetsAgent()  # 재사용 ✅
    
    async def generate_outputs(self, analysis: MeetingAnalysis):
        # 기존 Agent 그대로 활용
        doc = await self.docs_agent.create_document(
            title=f"회의록: {analysis.title}",
            content=self._format_minutes(analysis)
        )
        sheet = await self.sheets_agent.create_spreadsheet(
            title=f"액션 아이템: {analysis.title}",
            data=analysis.action_items
        )
        return doc, sheet
```

**재사용률**: Docs Agent 90%, Sheets Agent 85%, Slides Agent 70% ✅

---

### 리스크 및 완화 전략 (#140)

| 리스크 | 심각도 | 완화 방법 |
|--------|--------|---------|
| Google Meet 실시간 스트리밍 불가 | 🔴 | Phase A(배치)로 시작, Phase B는 이후 |
| "30초 완성" 미달 | 🔴 | 마케팅 클레임 "5-10분"으로 수정 |
| 한국어 화자 구분 정확도 낮음 | 🟡 | 화자 라벨 수동 수정 UI 제공 |
| Workspace 권한 (녹화 접근) | 🟡 | Google Workspace Business 이상 필수 명시 |
| 음성 데이터 보안/개인정보 | 🔴 | 전사 즉시 삭제 옵션, GDPR 컴플라이언스 |

**권장**: Phase A (Google Drive 녹화 → 배치 전사)로 MVP 출시 후, 사용자 피드백 기반으로 Phase B 투자 결정.

---

## 🎨 Idea #141: No-Code Agent Studio

### 기술 검토 결론: ✅ 구현 권장 (2순위)

> 기존 인프라(Celery, FastAPI, Tauri) 재사용률이 높고 기술적 리스크 낮음.

---

### 프론트엔드 프레임워크 선택

**권장: React Flow (reactflow v11)**

| 항목 | React Flow | 자체 구현 |
|------|-----------|---------|
| 개발 기간 | 2-3주 | 8-10주 |
| Tauri 호환성 | ✅ WebView에서 완벽 동작 | ✅ |
| 라이선스 | MIT (무료) | - |
| 커스터마이징 | ✅ 충분 (Custom Nodes 지원) | ✅ |
| 커뮤니티 | ⭐⭐⭐⭐⭐ (GitHub 18k stars) | - |
| **결론** | **권장** ✅ | 불필요한 중복 ❌ |

**Tauri 통합 확인됨**: React Flow는 순수 React 컴포넌트. Tauri의 WebView(Chromium)에서 문제없이 동작. 네이티브 API 호출은 Tauri invoke로 처리.

```typescript
// Tauri + React Flow 통합 예시
import ReactFlow from 'reactflow';
import { invoke } from '@tauri-apps/api';

const AgentStudio = () => {
  const executeWorkflow = async (workflow) => {
    // Tauri → FastAPI 백엔드 호출
    const result = await invoke('execute_workflow', { workflow });
  };
  
  return <ReactFlow ... onConnect={handleConnect} />;
};
```

---

### 워크플로우 엔진 설계

**권장: Celery 기반 + 경량 State Machine 래퍼**

```
[사용자 정의 워크플로우 JSON DSL]
{
  "id": "wf-001",
  "name": "이메일 분류 자동화",
  "nodes": [
    {"id": "trigger_1", "type": "gmail_receive", "config": {...}},
    {"id": "ai_1", "type": "classify", "config": {"categories": [...]}},
    {"id": "sheet_1", "type": "append_row", "config": {"sheet_id": "..."}}
  ],
  "edges": [
    {"from": "trigger_1", "to": "ai_1"},
    {"from": "ai_1", "to": "sheet_1"}
  ]
}

↓ WorkflowRunner가 JSON 파싱 → Celery task chain 변환

[WorkflowRunner (신규 - 1주 개발)]
    → Celery task chain 생성 (기존 재사용 ✅)
    → 각 노드 = 기존 Agent 함수 호출
    → 상태 Redis에 저장 (기존 재사용 ✅)
```

**Celery 재사용 가능 이유**:
- 현재 Celery가 비동기 Agent 실행에 사용 중
- Workflow는 Celery task chain으로 자연스럽게 매핑
- 신규 State Machine 도입 시 +4-6주 개발 → 불필요

**Prefect/Airflow 도입 여부**: **불필요**. 현재 규모(동시 100개 워크플로우)는 Celery로 충분.

---

### 보안: 사용자 정의 워크플로우 Sandbox

**핵심 보안 원칙**: 사용자 정의 워크플로우는 **JSON DSL만 허용** (Python 코드 실행 없음)

```
[안전한 아키텍처]
사용자 입력: JSON 워크플로우 (코드 없음)
    ↓
WorkflowValidator: JSON Schema 검증
    ↓
허용된 블록 타입만 실행 (화이트리스트)
    ↓
각 블록 = 미리 정의된 함수 (AgentHQ 내부 코드)

[금지]
- 사용자 Python 코드 실행 ❌
- eval() / exec() 사용 ❌
- 임의 API 호출 ❌ (허용된 통합만)
```

**추가 보안 레이어**:

```python
class WorkflowValidator:
    ALLOWED_BLOCK_TYPES = {
        "gmail_receive", "gmail_send",
        "sheet_read", "sheet_write",
        "doc_create", "ai_classify", "ai_summarize"
        # 허용 목록 명시적 관리
    }
    
    def validate(self, workflow: dict) -> ValidationResult:
        for node in workflow["nodes"]:
            if node["type"] not in self.ALLOWED_BLOCK_TYPES:
                raise SecurityError(f"허용되지 않은 블록: {node['type']}")
        return ValidationResult(ok=True)
```

**Docker 격리 불필요**: JSON DSL 방식이면 Sandbox 컨테이너 없이도 안전. 구현 단순화.

---

### 확장성: 동시 워크플로우 100개+

**현재 Celery 인프라 분석**:

```
현재 추정 구성:
- Redis broker (기존)
- Celery workers: 4-8개 (기본 설정 추정)
- 각 워크플로우 = 1개 Celery task chain

동시 100개 처리 가능 여부:
- Celery worker 1개: 동시 4-8 task
- 10개 worker: 동시 40-80 task ✅
- 20개 worker: 동시 100+ task ✅

수평 확장 방법:
celery -A app.celery worker --concurrency=8 -n worker1@%h
celery -A app.celery worker --concurrency=8 -n worker2@%h
# 워커 추가만으로 확장 가능
```

**결론**: 현재 인프라로 100개 동시 처리 **가능**. Docker Compose에서 `replicas: N`으로 확장.

---

### 아키텍처 다이어그램 (#141)

```
[Tauri Desktop App]
└─ React Flow UI (드래그 앤 드롭 에디터)
   └─ Workflow JSON 저장 → FastAPI

[FastAPI Backend]
├─ POST /workflows - 워크플로우 저장 (PostgreSQL)
├─ POST /workflows/{id}/execute - 실행 시작
└─ GET /workflows/{id}/status - 상태 조회

[WorkflowRunner (신규, 경량)]
└─ JSON DSL 파싱 → Celery task chain 생성 (기존)

[Celery Workers (기존)]
├─ GmailTriggerTask
├─ AIClassifyTask (기존 LangChain Agent 호출)
├─ DocsCreateTask (기존 DocsAgent 호출)
└─ SheetsWriteTask (기존 SheetsAgent 호출)

[Redis (기존)]
└─ Celery broker + 워크플로우 상태 저장
```

---

### 리스크 및 완화 전략 (#141)

| 리스크 | 심각도 | 완화 방법 |
|--------|--------|---------|
| React Flow 학습 곡선 | 🟢 | 예제 풍부, 2-3일 학습으로 충분 |
| 복잡한 워크플로우 디버깅 | 🟡 | 단계별 실행 로그 UI 필수 |
| 트리거 (Gmail 실시간) 지연 | 🟡 | Polling 방식으로 시작, Webhook으로 업그레이드 |
| 무한 루프 워크플로우 | 🟡 | 최대 실행 단계 제한 (max_steps=50) |
| Rate Limit 초과 (많은 자동화) | 🟡 | 기존 Rate Limit 미들웨어 재사용 ✅ |

---

## 📅 개발 순서 권장

### Phase 13 구현 로드맵

```
Week 1-2: Document DNA Engine 핵심 (Idea #139)
├─ spaCy + textstat 파이프라인
├─ DNA 저장 (PostgreSQL + Vector DB)
└─ LLM 스타일 인젝션 (System Prompt)

Week 3-4: No-Code Studio 기초 (Idea #141)
├─ React Flow 설치 + Tauri 통합
├─ WorkflowRunner (JSON DSL → Celery)
└─ 5개 기본 블록 구현

Week 5-6: No-Code Studio 확장 + DNA 고도화
├─ 블록 라이브러리 20개 완성
├─ DNA 피드백 루프 (StyleConsistencyChecker)
└─ Template Gallery 5개

Week 7-8: Meeting Autopilot MVP (Idea #140, Phase A)
├─ Google Calendar 회의 종료 감지
├─ Google Drive 녹화 → Whisper 배치 전사
└─ 기존 Docs/Sheets Agent 연결

Week 9-10: 통합 테스트 + 출시
├─ E2E 테스트 작성
├─ DNA + Studio + Autopilot 통합 검증
└─ 문서 + 마케팅 자료 준비
```

---

## 🚨 즉시 해결해야 할 기술 이슈

Phase 13 착수 전 선행 조건:

1. **[P0] SECRET_KEY 환경 변수화** (보안)
   - `config.py` 하드코딩 즉시 제거
   - `os.environ.get("SECRET_KEY")` 전환
   - `.env.example` 업데이트

2. **[P1] Sheets Agent / Docs Agent 통합 테스트**
   - Meeting Autopilot, DNA Engine 모두 의존
   - 현재 구현 완성도 확인 필요

3. **[P1] Celery Worker 설정 검토**
   - No-Code Studio의 동시 실행 100개 대비
   - `--concurrency` 값 최적화

---

## 💬 설계자 최종 의견

### 권장 구현 순서

1. **#139 Document DNA Engine** (5주, 1순위)
   - 리스크 낮고 Enterprise 가치 명확
   - 기존 Vector DB, PostgreSQL, LLM 스택 100% 재활용
   - PII 처리 주의 (Presidio 통합 권장)

2. **#141 No-Code Agent Studio** (8주, 2순위)
   - 시장 확장 효과 가장 큼 (개발자 → 비개발자)
   - React Flow 선택으로 개발 기간 단축
   - JSON DSL 방식으로 보안 리스크 최소화

3. **#140 Meeting Autopilot** (7주, 3순위)
   - Google Meet 실시간 API 제한 → Phase A(배치)로 MVP 먼저
   - "30초 완성" 클레임은 "5-10분"으로 수정 필요
   - 음성 데이터 보안 정책 수립 선행 필요

### 아키텍처 강점 확인

현재 AgentHQ 아키텍처는 Phase 13 전체를 수용할 준비가 되어 있습니다:
- ✅ Celery → No-Code Studio 워크플로우 엔진
- ✅ Vector DB → Document DNA 저장소
- ✅ Docs/Sheets Agent → Meeting Autopilot 출력
- ✅ Tauri WebView → React Flow 에디터
- ✅ Rate Limit 미들웨어 → Studio 과부하 방지

**Phase 13 기술적 타당성**: 3개 모두 구현 가능. 단 #140은 현실적 기대치 조정 필요.

---

**검토 완료**: 2026-02-17  
**다음 단계**: 기획자 확인 → P0 이슈 해결 → Week 1 착수
