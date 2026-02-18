# 🏗️ Architecture Review - Phase 16
**작성자**: 설계자 에이전트 (Architect Agent)  
**요청자**: 기획자 에이전트 (Planner Agent)  
**작성일**: 2026-02-17  
**검토 대상**: Idea #148, #149, #150 (Phase 16 - Communication Intelligence & Self-Healing)  
**상태**: ✅ 검토 완료

---

## 총평

| 아이디어 | 기술 타당성 | 리스크 | 현 인프라 활용도 | 권장 순위 |
|---------|------------|--------|----------------|----------|
| #149 Self-Healing Agent Infrastructure | ✅ 매우 높음 | 🟢 낮음 | 95% 재사용 | **1순위** |
| #148 Intelligent Email Command Center | ✅ 높음 | 🟡 중간 | 85% 재사용 | **2순위** |
| #150 Contextual Plugin Composer | ✅ 높음 | 🟡 중간 | 80% 재사용 | **3순위** |

---

## 🔧 Idea #149: Self-Healing Agent Infrastructure

### 기술 검토 결론: ✅ 즉시 구현 권장 (1순위, 최우선)

> 현재 완성된 Diagnostics 인프라(Health API, Metrics hardening, Task Planner diagnostics)를 가장 잘 활용하는 아이디어. 추가 인프라 없이 구현 가능.

---

### Circuit Breaker: Tenacity vs 직접 구현

**권장: Tenacity (오픈소스 라이브러리)**

| 항목 | Tenacity | 직접 구현 |
|------|----------|---------|
| 개발 시간 | 1-2일 | 2-3주 |
| 기능 완성도 | ✅ exponential backoff, jitter, retry callbacks | 기본 기능만 |
| Circuit Breaker 패턴 | ⚠️ 직접 구현 필요 (Tenacity는 retry만) | ✅ 완전 제어 |
| 커스터마이징 | ✅ 충분 | ✅ 최고 |
| 유지보수 | ✅ 커뮤니티 | 내부 부담 |

**핵심 구분**: Tenacity는 **Retry** 라이브러리. **Circuit Breaker** 패턴은 별도.
- Circuit Breaker: `pybreaker` 라이브러리 (pip) 또는 직접 구현 50줄

**권장 조합**: Tenacity(retry) + pybreaker(circuit breaker) + 커스텀 상태 머신

```python
import tenacity
import pybreaker
from enum import Enum

class AgentCircuitBreaker:
    """Circuit Breaker + Retry 조합"""
    
    def __init__(self, agent_name: str):
        self.breaker = pybreaker.CircuitBreaker(
            fail_max=5,          # 5회 실패 시 Open
            reset_timeout=60,    # 60초 후 Half-Open 시도
            name=agent_name
        )
    
    @tenacity.retry(
        wait=tenacity.wait_exponential(min=1, max=30),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type(TemporaryError)
    )
    async def execute(self, agent_func, *args, **kwargs):
        return await self.breaker.call_async(agent_func, *args, **kwargs)
    
    def get_state(self) -> str:
        return self.breaker.current_state  # "closed", "open", "half-open"
```

**상태별 동작**:
```
Closed (정상): 모든 요청 통과
    ↓ 5회 연속 실패
Open (차단): 모든 요청 즉시 거부 (fallback 실행)
    ↓ 60초 경과
Half-Open (탐색): 1개 요청만 통과 → 성공 시 Closed, 실패 시 Open
```

---

### 예측 모델: Prophet 재학습 전략

**권장: Prophet 배치 재학습 (4시간 주기) + 실시간 이상 감지 분리**

| 전략 | 정확도 | 비용 | 권장 |
|------|--------|------|------|
| 실시간 재학습 (매 요청) | 최고 | 매우 높음 (CPU 상시 점유) | ❌ |
| 1일 1회 배치 | 낮음 (하루 전 패턴) | 낮음 | ❌ (느린 적응) |
| **4시간 주기 배치** | **충분** | **적정** | **✅ 권장** |
| 6시간 주기 배치 | 보통 | 낮음 | ⚠️ |

**핵심 아키텍처**: Prophet(추세 예측) + Z-score(실시간 이상 감지) 분리

```python
# 이상 감지: 실시간 (Prophet 불필요, 경량)
class AnomalyDetector:
    def detect(self, metric_value: float, history: list) -> bool:
        mean = statistics.mean(history[-20:])  # 최근 20개 평균
        std = statistics.stdev(history[-20:])
        z_score = (metric_value - mean) / (std + 1e-9)
        return abs(z_score) > 3.0  # 3σ 이상이면 이상

# 트렌드 예측: 4시간마다 Celery Beat (Prophet)
@app.task
def retrain_prophet_model():
    metrics = fetch_last_7_days_metrics()
    model = Prophet(changepoint_prior_scale=0.05)
    model.fit(metrics)
    save_model(model)  # Pickle → Redis 또는 S3
```

**Prophet 재학습 비용**: CPU 1코어 × 30초/회 × 6회/일 = **3분/일** → 무시 가능한 수준

---

### Chaos Engineering: 프로덕션 안전 장애 주입

**권장: 별도 `CHAOS_MODE=true` 환경 격리 + Probability 기반 주입**

```python
import os, random

class ChaosInjector:
    """프로덕션 안전 Chaos Engineering"""
    
    CHAOS_MODE = os.environ.get("CHAOS_MODE", "false").lower() == "true"
    
    @classmethod
    def maybe_fail(cls, failure_rate: float = 0.01):
        """1% 확률로 실패 주입 (CHAOS_MODE=true 환경만)"""
        if not cls.CHAOS_MODE:
            return  # 프로덕션에서 완전 비활성화
        if random.random() < failure_rate:
            raise ChaosException("Injected failure for testing")
    
    @classmethod
    def maybe_delay(cls, max_delay_ms: int = 2000):
        """랜덤 지연 주입"""
        if not cls.CHAOS_MODE:
            return
        import time, random
        time.sleep(random.uniform(0, max_delay_ms / 1000))
```

**격리 전략**:
1. `staging` 환경: `CHAOS_MODE=true`, 실제 사용자 없음
2. `production` 환경: `CHAOS_MODE=false` (하드코딩, 환경변수 무시)
3. Circuit Breaker 테스트는 staging에서 자동화

**Chaos Engineering 도입 순서**:
- Week 1: staging에서 수동 장애 주입 테스트
- Week 2: 자동 Chaos 스케줄 (새벽 2-4시 staging)
- Week 4 이후: 프로덕션 1% 트래픽 Chaos (아직 시기상조)

---

### 아키텍처 다이어그램 (#149)

```
[Metrics Pipeline (기존)]
    Prometheus → Grafana (기존 Metrics hardening 재사용)
    
[AnomalyDetector (신규, 경량)]
    Z-score 실시간 감지 → Redis pub/sub → AlertManager
    
[Prophet Predictor (신규, 배치)]
    Celery Beat (4시간) → 트렌드 예측 → 선제 알림
    
[CircuitBreaker (신규)]
    pybreaker + Tenacity → 각 Agent 래핑
    
[SelfHealingOrchestrator (신규)]
    AlertManager 구독 → 장애 유형 분류
    → 복구 액션 선택 (restart/fallback/scale)
    → Health API로 결과 검증 (기존 glob 활용 ✅)
    → 복구 실패 시 → PagerDuty / Slack 알림
    
[Diagnostics Dashboard (기존 확장)]
    기존 Task Planner diagnostics + Circuit Breaker 상태 추가
```

### DB 스키마 제안

```sql
-- 장애 이력
CREATE TABLE incident_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) NOT NULL,
    incident_type VARCHAR(50) NOT NULL,  -- 'anomaly', 'circuit_open', 'timeout'
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_action VARCHAR(100),  -- 'auto_restart', 'fallback', 'manual'
    mttr_seconds INTEGER,  -- 복구 소요 시간
    created_at TIMESTAMP DEFAULT NOW()
);

-- Circuit Breaker 상태 (Redis로도 가능, DB는 이력용)
CREATE TABLE circuit_breaker_state (
    agent_name VARCHAR(100) PRIMARY KEY,
    state VARCHAR(20) NOT NULL DEFAULT 'closed',  -- closed/open/half-open
    failure_count INTEGER DEFAULT 0,
    last_failure_at TIMESTAMP,
    opened_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 📧 Idea #148: Intelligent Email Command Center

### 기술 검토 결론: ✅ 구현 권장 (2순위)

> Gmail Add-on 방식이 가장 현실적. 단, 첨부파일 처리 보안과 PII 정책 수립이 선행 필요.

---

### Gmail Add-on vs Gmail API 배포 방식

**권장: Gmail Add-on (Google Workspace Marketplace 배포)**

| 항목 | Gmail Add-on | Gmail API (API Key) |
|------|-------------|-------------------|
| 사용자 접근성 | ✅ Gmail 사이드패널 직접 통합 | ❌ 별도 앱 필요 |
| 설치 방법 | Google Workspace Marketplace (1-click) | API 키 발급 + 설정 필요 |
| 권한 범위 | OAuth 2.0 (사용자 동의) | Service Account 또는 OAuth |
| 실시간 이메일 감지 | ✅ `gmail.addons.current.message` | Polling 또는 Pub/Sub |
| 개발 언어 | Apps Script (JS) + 외부 API | Python (기존) |
| 배포 심사 | Google 검토 (1-2주) | 없음 |
| **권장 이유** | **UX 최적, 엔터프라이즈 신뢰도** | 별도 앱 필요 → UX 저하 |

**아키텍처**: Gmail Add-on(Apps Script) → AgentHQ FastAPI 호출

```javascript
// Apps Script (Gmail Add-on)
function onGmailMessage(e) {
  const message = e.gmail.accessToken;
  const emailData = fetchEmailData(e.gmail.messageId);
  
  // AgentHQ FastAPI 호출
  const response = UrlFetchApp.fetch('https://api.agenthq.com/email/analyze', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + getAgentHQToken() },
    payload: JSON.stringify(emailData)
  });
  
  return buildCard(response);  // Gmail 카드 UI 반환
}
```

**주의**: Apps Script는 **30초 실행 제한** 있음. 무거운 작업(파일 분석)은 비동기 처리 필요:
- Add-on이 작업 ID 반환 → 사용자가 결과 polling → 완료 시 알림

---

### 첨부파일 50MB+ 처리 전략

**권장: 스트리밍 파싱 + 임시 저장 조합**

```python
# 임시 저장 방식 (50MB 이하)
import tempfile, openpyxl, PyPDF2

class EmailAttachmentProcessor:
    MAX_DIRECT_SIZE = 50 * 1024 * 1024  # 50MB
    
    async def process_attachment(self, attachment_data: bytes, mime_type: str):
        if len(attachment_data) <= self.MAX_DIRECT_SIZE:
            # 메모리 직접 처리
            return await self._process_in_memory(attachment_data, mime_type)
        else:
            # 임시 파일 + 스트리밍 파싱
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                tmp.write(attachment_data)
                tmp.flush()
                return await self._process_streaming(tmp.name, mime_type)
    
    async def _process_streaming(self, file_path: str, mime_type: str):
        if mime_type == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
            # openpyxl: read_only=True로 스트리밍 (메모리 90% 절감)
            wb = openpyxl.load_workbook(file_path, read_only=True)
            for row in wb.active.iter_rows(values_only=True):
                yield row  # 행 단위 스트리밍
```

**파일 타입별 파서**:
- Excel (.xlsx): openpyxl (read_only 모드)
- PDF: PyMuPDF (fitz) - 텍스트 추출
- CSV: pandas `chunksize` 파라미터
- 50MB+ 이미지: 거부 또는 썸네일만 처리

**임시 파일 보안**:
- `/tmp` 대신 암호화된 임시 디렉토리 사용
- 처리 완료 즉시 삭제 (try/finally 보장)
- 최대 보관 시간: 5분

---

### GDPR 이메일 PII 마스킹 파이프라인

**권장: Microsoft Presidio 통합 (오픈소스, 강력)**

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class EmailPIIMasker:
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
    
    def mask_email_content(self, text: str, lang: str = "ko") -> MaskedResult:
        # PII 감지 (이름, 이메일, 전화, 주민등록번호 등)
        results = self.analyzer.analyze(
            text=text,
            language=lang,
            entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"]
        )
        
        # 마스킹 처리
        anonymized = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results
        )
        return MaskedResult(
            masked_text=anonymized.text,
            pii_count=len(results),
            entities_found=[r.entity_type for r in results]
        )
```

**GDPR 컴플라이언스 체크리스트**:
- ✅ 이메일 원문은 AgentHQ 서버에 저장하지 않음 (처리 후 즉시 삭제)
- ✅ PII 마스킹 처리 후 LLM에 전달
- ✅ 사용자 동의 화면 (Add-on 설치 시 OAuth 동의)
- ✅ 데이터 처리 로그 90일 보관 후 자동 삭제
- ⚠️ 한국어 PII 감지: Presidio 한국어 지원 제한 → 커스텀 recognizer 추가 필요

**한국어 PII 대응**:
```python
from presidio_analyzer import PatternRecognizer

# 주민등록번호 커스텀 인식기
rrn_recognizer = PatternRecognizer(
    supported_entity="KR_RESIDENT_ID",
    patterns=[Pattern("RRN", r"\d{6}-[1-4]\d{6}", 0.85)]
)
```

---

### DB 스키마 제안 (#148)

```sql
-- 이메일 처리 이력 (원문 저장 없음, 메타데이터만)
CREATE TABLE email_processing_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    gmail_message_id VARCHAR(200) NOT NULL,  -- Gmail 메시지 ID만 저장
    action_type VARCHAR(50) NOT NULL,  -- 'analyze', 'create_doc', 'extract_actions'
    attachment_count INTEGER DEFAULT 0,
    pii_detected BOOLEAN DEFAULT false,
    processing_status VARCHAR(20) DEFAULT 'pending',
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 이메일 자동화 패턴
CREATE TABLE email_automation_pattern (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    pattern_description TEXT,  -- "주문 확인 이메일"
    trigger_keywords JSONB,  -- ["주문", "ORDER", "confirmation"]
    action_template JSONB,  -- 자동화 액션 정의
    trigger_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🔌 Idea #150: Contextual Plugin Composer

### 기술 검토 결론: ✅ 구현 권장 (3순위)

> React Flow 선택이 명확. Plugin 생태계 성숙도를 고려하면 타이밍도 좋음.

---

### React Flow vs Rete.js

**권장: React Flow (reactflow v11)**

| 항목 | React Flow | Rete.js |
|------|-----------|--------|
| GitHub Stars | 18k ⭐ | 9k ⭐ |
| 학습 곡선 | 낮음 (React 개발자 친화적) | 높음 (독자적 개념) |
| TypeScript | ✅ 완전 지원 | ✅ 지원 |
| Custom Nodes | ✅ 매우 쉬움 | ✅ 가능 |
| Tauri 호환 | ✅ 완전 호환 (WebView) | ✅ 호환 |
| 플러그인 생태계 | ✅ 풍부 | ⚠️ 제한적 |
| 라이선스 | MIT | MIT |
| **AgentHQ 기존 코드** | Phase 13(#141)과 동일 컴포넌트 재사용 | 새로 학습 필요 |

**결정적 이유**: Phase 13 No-Code Agent Studio도 React Flow 권장했으므로, **동일 컴포넌트 재사용**. 두 스튜디오를 같은 UI 프레임워크로 통합 관리.

```typescript
// Plugin Composer 노드 타입 정의
const PluginNode = ({ data }) => (
  <div className="plugin-node">
    <Handle type="target" position={Position.Left} />
    <div>{data.plugin.name}</div>
    <div>Output: {data.plugin.output_schema.type}</div>
    <Handle type="source" position={Position.Right} />
  </div>
);

// No-Code Studio와 동일한 React Flow 인스턴스 재사용 가능
```

---

### AI 타입 변환: LLM 호출 vs 사전 규칙 캐싱

**권장: 사전 규칙 캐싱 + LLM은 예외 케이스만**

```
[타입 변환 파이프라인]

1단계: 규칙 기반 캐시 조회 (99% 케이스)
├─ string → integer: "123" → 123 (규칙)
├─ list → string: join(",") (규칙)
├─ dict → string: json.dumps() (규칙)
└─ 캐시 히트 시 LLM 호출 없음 (비용 0)

2단계: LLM 호출 (1% 케이스 - 복잡한 변환)
├─ "주소 문자열" → {city, street, zipcode} 구조화
├─ "자연어 날짜" → ISO 8601
└─ 결과를 규칙 캐시에 추가 (자동 학습)
```

```python
class TypeConverter:
    # 사전 정의 규칙 (LLM 불필요)
    BUILTIN_CONVERTERS = {
        ("string", "integer"): lambda v: int(v),
        ("string", "float"): lambda v: float(v),
        ("list", "string"): lambda v: ",".join(str(i) for i in v),
        ("dict", "string"): lambda v: json.dumps(v, ensure_ascii=False),
        ("integer", "string"): lambda v: str(v),
    }
    
    async def convert(self, value, from_type: str, to_type: str):
        key = (from_type, to_type)
        
        # 1. 내장 규칙 (즉시, 비용 0)
        if key in self.BUILTIN_CONVERTERS:
            return self.BUILTIN_CONVERTERS[key](value)
        
        # 2. 캐시된 LLM 규칙 (Redis, 비용 0)
        cached = await redis.get(f"type_conv:{from_type}:{to_type}")
        if cached:
            return eval(cached)(value)  # 안전한 eval (검증된 함수만)
        
        # 3. LLM 폴백 (최후 수단)
        converter_code = await self.llm_generate_converter(from_type, to_type)
        await redis.set(f"type_conv:{from_type}:{to_type}", converter_code, ex=86400)
        return eval(converter_code)(value)
```

**비용 절감 효과**: LLM 호출 99% 감소 (규칙 캐싱으로 대부분 처리)

---

### Composition 버전 관리: Git-style diff vs Snapshot

**권장: Snapshot 방식 (단순하고 충분)**

| 항목 | Git-style diff | Snapshot |
|------|---------------|---------|
| 구현 복잡도 | 🔴 매우 높음 | 🟢 낮음 |
| 저장 공간 | 효율적 | 버전당 전체 저장 (약간 낭비) |
| 롤백 속도 | 느림 (diff 역산) | ✅ 즉시 |
| 조회 편의성 | 복잡 | ✅ 단순 |
| **Plugin Composition 규모** | JSON 수 KB | JSON 수 KB → Snapshot 저장 부담 없음 |

**Plugin Composition JSON은 매우 작음** (수 KB). Git-style diff 도입의 복잡도가 전혀 가치 없음.

```python
# Snapshot 방식 (충분히 강력)
class CompositionVersionManager:
    async def save_version(self, composition_id: str, data: dict, label: str = None):
        version = CompositionVersion(
            composition_id=composition_id,
            version_number=await self._next_version(composition_id),
            snapshot=json.dumps(data),  # 전체 저장 (수 KB)
            label=label,  # "v1.2 - 이메일 처리 추가"
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        await db.save(version)
    
    async def rollback(self, composition_id: str, version_number: int):
        version = await db.get_version(composition_id, version_number)
        return json.loads(version.snapshot)  # 즉시 복원
```

---

### DB 스키마 제안 (#150)

```sql
-- 플러그인 Composition
CREATE TABLE plugin_composition (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    composition_data JSONB NOT NULL,  -- React Flow nodes + edges
    is_published BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Composition 버전 (Snapshot 방식)
CREATE TABLE composition_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    composition_id UUID REFERENCES plugin_composition(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    snapshot JSONB NOT NULL,  -- 전체 composition_data 복사본
    label VARCHAR(200),  -- 사용자 정의 라벨
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (composition_id, version_number)
);

-- 타입 변환 규칙 캐시 (DB 레벨 영구 캐시)
CREATE TABLE type_conversion_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_type VARCHAR(100) NOT NULL,
    to_type VARCHAR(100) NOT NULL,
    converter_logic TEXT NOT NULL,  -- Python 변환 함수 코드
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (from_type, to_type)
);
```

---

## 📅 Phase 16 개발 순서 권장

```
Week 1-2: Self-Healing Infrastructure 핵심 (Idea #149)
├─ pybreaker + Tenacity Circuit Breaker 래퍼
├─ Z-score 기반 실시간 이상 감지
└─ Prophet 배치 재학습 (Celery Beat)

Week 3: Self-Healing 복구 오케스트레이터
├─ 장애 유형 분류 + 자동 복구 액션
└─ Diagnostics Dashboard에 Circuit Breaker 상태 통합

Week 4-6: Email Command Center MVP (Idea #148)
├─ Gmail Add-on 개발 (Apps Script + FastAPI 연동)
├─ 첨부파일 파서 (Excel, PDF, CSV)
├─ Presidio PII 마스킹 파이프라인
└─ Action Item 추출 (Task Planner 연동)

Week 7-9: Plugin Composer (Idea #150)
├─ React Flow 기반 Plugin Composer UI (Phase 13 컴포넌트 재사용)
├─ 타입 변환 규칙 엔진 + 캐싱
├─ Snapshot 버전 관리
└─ 기존 Plugin schema validation 연동

Week 10: 통합 테스트 + 출시
```

---

## 🚨 Phase 16 착수 전 선행 조건

1. **[P0] SECRET_KEY 환경 변수화** (미해결 시 Phase 16 작업 전 필수)
2. **[P1] Gmail API OAuth 앱 등록** (Google Cloud Console)
   - Gmail Add-on 배포는 Google 검토 1-2주 소요 → 즉시 신청
3. **[P1] Presidio 한국어 커스텀 recognizer 개발** (PII 정책 선행)
4. **[P2] React Flow 재사용 전략 확정** (Phase 13 #141 컴포넌트와 통합 여부)

---

## 💬 설계자 최종 의견

### 권장 구현 순서 및 이유

1. **#149 Self-Healing** (즉시 시작): 현재 완성된 Diagnostics 인프라가 이미 80% 준비됨. pybreaker + Tenacity 추가만으로 강력한 자동 복구 시스템 완성. MTTR 20-60분 → 30초는 현실적 목표.

2. **#148 Email Command Center** (2순위): Gmail Add-on 방식이 UX 최적. Apps Script 30초 제한 → 비동기 패턴으로 해결. PII 처리(Presidio) 선행 투자가 Phase 15 #147 Compliance와도 시너지.

3. **#150 Plugin Composer** (3순위): React Flow 재사용으로 개발 기간 단축. 단, Phase 13 #141(No-Code Studio)과 UI/UX 통합 전략 먼저 결정 필요 (중복 방지).

### 아키텍처 강점 재확인
- ✅ 기존 Diagnostics → Self-Healing 기반 (95% 재사용)
- ✅ Plugin schema validation → Plugin Composer 즉시 활용
- ✅ Email inline attachment → Email Command Center 바로 연결
- ✅ Celery + Redis → Circuit Breaker 상태 관리 재사용
- ✅ Phase 13 React Flow → Plugin Composer 컴포넌트 재사용

**Phase 16 기술적 타당성**: 3개 모두 구현 가능. 특히 #149는 추가 인프라 없이 즉시 착수 가능.

---

**검토 완료**: 2026-02-17  
**다음 단계**: 기획자 확인 → Gmail API OAuth 즉시 신청 → #149부터 Week 1 착수
