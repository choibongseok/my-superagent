# 💡 Planner Ideation - 신규 아이디어 제안 (2026-02-17 AM 1:20 UTC)

**작성자**: Planner Agent (Cron: Planner Ideation)  
**작성일**: 2026-02-17 01:20 UTC  
**검토 대상**: AgentHQ 프로젝트 현황 + Phase 11-12 연속성 분석  
**제안 수**: 3개 (Phase 13 - Intelligence & Democratization Focus)

---

## 🎯 Executive Summary

### 전략적 방향: 콘텐츠 지능화 + 워크플로우 자동화 + 비개발자 접근성

**Phase 11 (B2B Developer Platform)**: SDK, Integration Hub, Analytics  
**Phase 12 (B2C UX & Performance)**: Onboarding, Performance, Collaboration  
**Phase 13 (이번 제안)**: 콘텐츠 DNA, 미팅 오토파일럿, No-Code 에이전트 스튜디오

**왜 Phase 13인가?**

Phase 11-12 완료 후 AgentHQ는 "AI 자동화 플랫폼"으로 자리잡는다.  
Phase 13은 그 이상: **"조직 지능 플랫폼"** 으로 도약한다.

```
Phase 12까지: AI가 문서를 만든다
Phase 13부터: AI가 조직의 언어를 배우고, 회의를 자동화하고, 누구나 AI를 만든다
```

**차별화 포인트**:
```
"가장 똑똑하게 학습하고, 가장 매끄럽게 작동하며, 가장 쉽게 커스터마이징하는 AI"
```

---

## 💡 Idea #139: "Document DNA Engine" - 조직의 언어를 학습하는 AI 🧬📄

### 문제점

**현재 AI 문서 생성의 한계**:
- 모든 AI가 "일반적인" 문서를 만든다 → 회사 고유 톤/스타일 없음 😓
- 기존 문서와 일관성 유지 불가 (새 보고서가 기존 스타일과 다름)
- 신입사원이 회사 스타일 파악에 3-6개월 소요 📚
- Brand voice 가이드라인 → AI는 무시

**경쟁사 현황**:
- ChatGPT: 일반적 스타일, 회사 커스터마이징 없음 ❌
- Notion AI: 기존 페이지 참조 가능, 학습 없음 ⚠️
- Google Workspace AI: Gemini 사용, 조직 학습 없음 ❌
- **AgentHQ: 기회** ✅

### 제안 솔루션

**"Document DNA Engine"** - 기존 문서에서 조직의 글쓰기 DNA를 추출하고, 새 문서에 자동 적용

**핵심 기능**:

1. **DNA Extraction** (분석):
   - Google Drive 기존 문서 일괄 분석 (50-200개)
   - 어휘 패턴, 문장 구조, 섹션 구성, 포맷 스타일 추출
   - 토론 스타일 (직접적 vs 데이터 중심 vs 스토리텔링) 분류
   - 시각화: "Your Company's Writing Style Profile"

2. **DNA Application** (생성):
   - 새 문서 생성 시 자동으로 추출된 DNA 적용
   - "Previous report style: 데이터 우선, 요약 먼저, 표 선호" → 자동 반영
   - 사용자 피드백으로 DNA 미세 조정 (강화학습)

3. **Brand Voice Guardian** (검수):
   - 생성된 문서가 DNA에서 벗어나면 경고
   - "이 섹션은 우리 회사 스타일과 30% 다릅니다 → 수정 제안"
   - Style Consistency Score: 87/100

4. **Department DNA** (부서별 다변화):
   - 마케팅팀 DNA vs 개발팀 DNA vs 경영진 DNA
   - 요청 시 자동으로 적절한 DNA 선택

**기술 구현**:

```python
# DNA Extraction Pipeline
class DocumentDNAEngine:
    def extract_dna(self, documents: List[GoogleDoc]) -> CompanyDNA:
        """
        1. Text extraction + preprocessing
        2. Style feature extraction (sentence length, vocab richness, etc.)
        3. Structure analysis (headings, bullet patterns, table usage)
        4. Tone classification (formal/informal, active/passive)
        5. Cluster into style profiles
        """
        features = self._extract_features(documents)
        dna_profile = self._cluster_styles(features)
        return CompanyDNA(profile=dna_profile, version="1.0")
    
    def apply_dna(self, prompt: str, dna: CompanyDNA) -> str:
        """Inject DNA into LLM prompt as style constraints"""
        style_instructions = self._dna_to_prompt(dna)
        return enhanced_prompt_with_style
```

**기술 스택**:
- NLP: spaCy, textstat, language-tool-python (스타일 분석)
- LLM: 기존 Claude/GPT + style injection (zero-shot)
- Storage: Vector DB (기존 인프라) + DNA JSON 프로파일
- UI: Style Profile Dashboard (Tauri 기존 프레임)

**예상 임팩트**:
- 📝 **문서 일관성**: -70% 수정 횟수
- ⏱️ **작성 시간**: 스타일 교정 시간 -80%
- 🆕 **신규 사용자**: 온보딩 시간 -50% (회사 스타일 즉시 습득)
- 💼 **Enterprise 가치**: 브랜드 일관성 제공 → Enterprise 필수 기능
- 💵 **매출**: Enterprise 전용 기능 ($99/month/org), 300개 org = $29.7k/month

**경쟁 우위**:
```
ChatGPT/Notion AI: "일반적인 AI 작성" vs AgentHQ: "당신 회사처럼 쓰는 AI" ⭐⭐⭐⭐⭐
```

**개발 난이도**: ⭐⭐⭐ (Medium)  
**개발 기간**: 5주  
**우선순위**: 🔥 HIGH  
**ROI**: ⭐⭐⭐⭐⭐ ($29.7k/month + Enterprise 전환율 +40%, 2.2개월 회수)

---

## 💡 Idea #140: "Meeting → Workspace Autopilot" - 회의가 끝나면 문서가 완성 🎙️⚡

### 문제점

**회의 이후의 지옥**:
- 90분 회의 → 30분 회의록 작성 → 10분 액션 아이템 정리 → 이메일 발송 ⌛
- 인수인계 오류: 회의에서 결정된 사항이 Google Docs에 반영 안 됨 😱
- 팔로업 실패: 50%의 액션 아이템이 2주 내 잊혀짐 💀
- **회의는 있어도, 결과물은 없는 조직**

**시장 현황**:
- Otter.ai: 전사(全寫)만 제공, 문서 생성 없음 ❌
- Fireflies.ai: 요약 제공, Workspace 연동 약함 ⚠️
- Notion AI: 별도 회의록 템플릿, 자동화 없음 ❌
- Google Meet: 자체 전사, 이후 작업 없음 ❌
- **AgentHQ + Google Workspace: 완전 자동화 가능** ✅

### 제안 솔루션

**"Meeting → Workspace Autopilot"** - 회의가 끝나는 순간, 모든 결과물이 자동 생성

**핵심 기능**:

1. **Real-Time Transcription + Analysis**:
   - Google Meet/Zoom/Teams 연동 (자동 참여)
   - 화자 구분 (Speaker Diarization)
   - 실시간 키워드 태깅 (결정사항, 액션 아이템, 질문, 우려사항)

2. **Smart Document Generation** (회의 종료 즉시):
   ```
   회의 종료 → 30초 내 자동 생성:
   ✅ 회의록 Google Doc (요약 + 전체 내용)
   ✅ 액션 아이템 Google Sheet (담당자, 마감일, 우선순위)
   ✅ 팔로업 이메일 초안 (참석자 전송 대기)
   ✅ 관련 Google Slides 업데이트 (진행 중인 덱에 반영)
   ```

3. **Context-Aware Workspace Update**:
   - "지난주 Q4 보고서 회의 내용" → 기존 Q4 Doc 자동 업데이트
   - 기존 프로젝트와 연결 → 관련 Sheets의 태스크 상태 자동 갱신
   - 히스토리 트래킹: "이 결정은 2월 10일 회의에서 나왔습니다"

4. **Smart Follow-Up Engine**:
   - 7일 후 자동 체크: "이 액션 아이템 완료했나요?"
   - 완료 안 된 항목 → 다음 회의 어젠다에 자동 추가
   - 반복 패턴 감지: "매주 월요일 이 항목 논의 → 정기 태스크로 전환"

5. **Meeting Intelligence Dashboard**:
   - 회의 효율성 점수: "말하는 시간 vs 결정 비율"
   - "이 팀은 평균 4.2개 액션 아이템/회의, 완료율 73%"
   - 최적 회의 시간 추천

**기술 구현**:

```python
class MeetingAutopilot:
    def __init__(self):
        self.transcriber = WhisperAPI()  # 또는 Google Speech-to-Text
        self.analyzer = MeetingAnalyzer()  # LangChain + 커스텀 프롬프트
        self.workspace_connector = WorkspaceConnector()
    
    async def process_meeting(self, meeting_id: str, audio_stream):
        # 1. Real-time transcription
        transcript = await self.transcriber.stream(audio_stream)
        
        # 2. Structured extraction
        analysis = await self.analyzer.extract({
            'decisions': ...,
            'action_items': ...,
            'participants': ...,
            'follow_ups': ...
        })
        
        # 3. Automatic workspace updates
        await self.workspace_connector.create_all(analysis)
        
        # 4. Schedule follow-ups
        await self.schedule_reminders(analysis.action_items)
```

**연동**:
- Google Meet API (자동 봇 참여)
- Zoom SDK (녹화 훅)
- Google Workspace (기존 Docs/Sheets/Slides Agent 활용!)
- Google Calendar (회의 자동 감지)

**예상 임팩트**:
- ⏱️ **회의 후 작업 시간**: 40분 → 5분 (-87.5%)
- 📝 **액션 아이템 완료율**: 50% → 85% (+70%)
- 🤝 **팀 정렬**: 회의 내용 불일치 -90%
- 💵 **매출**: Meeting Pro Plan $39/month/team, 1,200팀 = $46.8k/month

**경쟁 우위**:
```
Otter.ai: 텍스트만 → AgentHQ: 텍스트 + Workspace 완전 자동화 ⭐⭐⭐⭐⭐
```

**개발 난이도**: ⭐⭐⭐⭐ (Medium-High)  
**개발 기간**: 7주  
**우선순위**: 🔥 HIGH  
**ROI**: ⭐⭐⭐⭐⭐ ($46.8k/month, 1.8개월 회수)

---

## 💡 Idea #141: "No-Code Agent Studio" - 코딩 없이 나만의 AI를 만든다 🎨🤖

### 문제점

**AI의 민주화는 아직 미완성**:
- 현재 AI 자동화 = 개발자만 가능 (Python, API, JSON)
- 영업팀장이 "고객 이메일 → CRM 업데이트" 자동화 원함 → 개발팀 의존 3주 대기 😤
- 마케터가 "경쟁사 분석 → 슬라이드 자동 생성" 원함 → 불가능 ❌
- No-Code 도구 (Zapier, Make): AI 연동 약함, Workspace 통합 없음

**시장 현황**:
- Zapier: 자동화 ✅, AI 약함 ⚠️, Google Workspace 제한적 ⚠️
- Make (Integromat): 강력한 자동화 ✅, AI 없음 ❌
- n8n: 오픈소스 ✅, 기술 지식 필요 ❌
- Microsoft Power Automate: MS 생태계 ✅, Google Workspace 제한 ❌
- **AgentHQ Agent Studio: AI + Workspace + No-Code** ✅

### 제안 솔루션

**"No-Code Agent Studio"** - 드래그 앤 드롭으로 나만의 AI 에이전트 제작

**핵심 기능**:

1. **Visual Flow Builder**:
   ```
   [트리거] → [조건] → [AI 액션] → [Workspace 출력]
   
   예시 워크플로우:
   [Gmail 수신] → [고객 문의 감지] → [관련 FAQ 검색] 
   → [답변 초안 생성] → [Google Docs 저장] → [Slack 알림]
   ```
   - 블록 드래그 앤 드롭 인터페이스
   - 연결선으로 데이터 흐름 정의
   - 실시간 미리보기: "이 흐름은 이렇게 실행됩니다"

2. **Pre-Built Block Library**:
   - **트리거 블록**: Gmail 수신, Google Sheet 변경, 시간 기반, 웹훅
   - **AI 블록**: 요약, 번역, 분석, 생성, 분류, 감정 분석
   - **Workspace 블록**: Doc 생성, Sheet 업데이트, Slide 추가
   - **통합 블록**: Slack, 이메일, Webhook, API 호출

3. **Template Gallery** (즉시 사용):
   ```
   📧 이메일 자동 분류 + 요약
   📊 주간 보고서 자동 생성
   🔍 경쟁사 모니터링 + 분석 보고서
   📋 회의 안건 자동 준비
   💼 고객 제안서 자동 초안
   ```

4. **AI-Assisted Builder** (자연어 → 워크플로우):
   - "고객 이메일 받으면 Sheets에 기록하고 담당자한테 Slack 보내줘"
   - → AI가 자동으로 워크플로우 생성 (사용자는 검토만)
   - "이 워크플로우 이해됐나요?" → Yes → 배포

5. **Monitoring & Debug**:
   - 실행 이력 로그 (언제, 무엇이, 왜 실행됐는지)
   - 에러 알림: "3번 실패 → 이런 이유입니다 → 이렇게 고치세요"
   - 성능 대시보드: 실행 횟수, 성공률, 처리 시간

**기술 구현**:

```typescript
// Frontend: React Flow 기반 Visual Editor
import ReactFlow from 'reactflow';

const AgentStudio = () => {
  return (
    <ReactFlow
      nodes={workflowNodes}
      edges={workflowEdges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
    >
      <BlockLibrary />
      <MiniMap />
      <Controls />
    </ReactFlow>
  );
};

// Backend: Workflow Engine
class WorkflowEngine:
    async def execute(self, workflow: Workflow, trigger_data: dict):
        for node in workflow.topological_sort():
            result = await self.execute_node(node, trigger_data)
            trigger_data = {**trigger_data, **result}
```

**기술 스택**:
- Frontend: React Flow (오픈소스 다이어그램 라이브러리) → Tauri 통합
- Backend: Workflow Engine (Python, 기존 Celery 활용)
- Storage: Workflow JSON → PostgreSQL (기존 DB)
- Execution: 기존 Agent 시스템 (Docs, Sheets, Slides Agent) 재사용

**예상 임팩트**:
- 👥 **사용자 확장**: 개발자 → 비개발자로 확장 (잠재 시장 10배)
- ⏱️ **자동화 구축 시간**: 3주 개발 → 30분 제작 (-99%)
- 🏢 **SMB 시장**: 중소기업 자동화 니즈 (현재 미개척)
- 💵 **매출**: Studio Plan $29/month/user, 3,000 users = $87k/month

**경쟁 우위**:
```
Zapier: 자동화만, AI 약함
AgentHQ Studio: AI 자동화 + Google Workspace 완전 통합 + No-Code ⭐⭐⭐⭐⭐
```

**개발 난이도**: ⭐⭐⭐⭐ (Medium-High)  
**개발 기간**: 8주  
**우선순위**: 🔥 CRITICAL  
**ROI**: ⭐⭐⭐⭐⭐ ($87k/month, 시장 확장 10배, 1.5개월 회수)

---

## 📊 Phase 13 요약 (Intelligence & Democratization)

### 신규 아이디어 3개

| ID | 아이디어 | 핵심 가치 | 타겟 | 우선순위 | 개발 기간 | 매출 예상 |
|----|----------|----------|------|----------|-----------|-----------|
| #139 | Document DNA Engine | 브랜드 일관성, 조직 학습 | Enterprise | 🔥 HIGH | 5주 | $29.7k/month |
| #140 | Meeting → Workspace Autopilot | 회의 후 작업 -87% | 팀/기업 | 🔥 HIGH | 7주 | $46.8k/month |
| #141 | No-Code Agent Studio | 시장 10배 확장, SMB | 비개발자 | 🔥 CRITICAL | 8주 | $87k/month |

**Phase 13 예상 매출**: $163.5k/month = **$1.96M/year**

### 전략적 의미

**Phase 11-13 누적**:

| Phase | 초점 | 예상 매출/year |
|-------|------|---------------|
| Phase 11 | B2B (Developer Platform) | $2.55M |
| Phase 12 | B2C (UX & Performance) | $1.58M |
| Phase 13 | Democratization & Intelligence | $1.96M |
| **합계** | | **$6.09M/year** |

### 차별화 포인트 (Phase 13 완료 시)

| 경쟁사 | 조직 스타일 학습 | 회의 → 문서 자동화 | No-Code AI 빌더 |
|--------|----------------|-------------------|----------------|
| ChatGPT | ❌ | ❌ | ❌ |
| Notion AI | ❌ | ⚠️ | ❌ |
| Otter.ai | ❌ | ⚠️ (텍스트만) | ❌ |
| Zapier | ❌ | ❌ | ✅ (AI 약함) |
| **AgentHQ** | ✅✅ | ✅✅ | ✅✅ |

**결론**: **3대 블루오션 동시 공략** 🏆

---

## 🔍 최근 개발 작업 방향성 평가

### 최근 20개 커밋 분석 (2026-02-16 ~ 2026-02-17)

**주요 트렌드** (가장 최신):
1. **Rate Limit 세분화** (user-agent bypass, client-id bypass): Enterprise 고객 차별화 ✅
2. **Cache 고도화** (glob patterns, dynamic TTL, symmetric jitter): 성능 최적화 기반 ✅
3. **Web Search 진화** (case-sensitive keys, batch dedup): 신뢰성 향상 ✅
4. **Google Docs Placeholder** (duplicate resolution): 문서 품질 향상 ✅
5. **Security 강화** (max_future_iat_seconds, fallback JWT scope): Enterprise 준비 ✅
6. **Memory 확장** (offset pagination, newest-first, regex flags): UX 개선 ✅

### 방향성 평가: ⭐⭐⭐⭐⭐ (계속 가야 함)

**강점 분석**:

1. **Rate Limit Enterprise화** → Idea #141 (Studio Plan)과 직접 연결
   - user-agent bypass로 Premium 사용자 차별화 ✅
   - client-id bypass로 API 기반 플랜 지원 ✅

2. **Cache 고도화 (동적 TTL + Glob + Jitter)** → Idea #140 Meeting Autopilot 기반
   - 회의 데이터 캐싱 전략에 직접 적용 가능 ✅
   - 성능 예측 기반 캐시 제어 가능 ✅

3. **Google Docs Placeholder 해결** → Idea #139 DNA Engine 기반
   - 브랜드 스타일 적용 시 플레이스홀더 중복 없음 ✅

**피드백 (개선 방향)**:

1. 🔴 **Frontend 연동 부재** (계속 지적):
   - Backend는 Phase 11-12-13 준비 완료
   - Desktop/Mobile App이 이 기능들을 노출 안 함
   - **제안**: API 엔드포인트 → UI 매핑 작업 1주 투자

2. 🟡 **테스트 커버리지** (여전히 17.3%):
   - 새 기능들 (rate-limit bypass, cache glob) 테스트 필요
   - **제안**: 신규 기능 +테스트 패턴으로 진행

3. 🟢 **문서화**: 좋아지고 있음, 계속 유지

---

## 🚀 설계자 에이전트 검토 요청

**Phase 13 기술 검토 필요 사항**:

### #139: Document DNA Engine
- 스타일 분석 라이브러리: spaCy vs textstat vs 커스텀 NLP
- DNA 저장 전략: Vector DB vs JSON 프로파일
- LLM 프롬프트 인젝션: Few-shot vs System message
- 학습 데이터 최소 요건: 최소 몇 개의 문서가 필요한가?

### #140: Meeting → Workspace Autopilot
- 음성 인식: Google Speech-to-Text vs Whisper (비용 vs 정확도)
- Google Meet 봇: API 가능 여부 검토 (공식 API vs workaround)
- 실시간 처리: Streaming transcription 파이프라인 설계
- 기존 Agent 재사용: Docs/Sheets Agent를 어떻게 연결할 것인가?

### #141: No-Code Agent Studio
- 프론트엔드: React Flow vs 자체 구현 (Tauri 호환성)
- 워크플로우 엔진: Celery 기반 재사용 vs 신규 State Machine
- 보안: 사용자 정의 워크플로우의 sandbox 실행
- 확장성: 동시 워크플로우 100개 실행 시 부하

---

**작성 완료**: 2026-02-17 01:20 UTC  
**제안 수**: 3개 (기존 138개 → 총 141개)  
**우선순위**: CRITICAL/HIGH  
**예상 매출**: $163.5k/month = $1.96M/year
