# 📊 LangFuse Setup & Integration Guide

> **AgentHQ LLM Observability & Monitoring 완전 가이드**

---

## 목차
1. [LangFuse란?](#langfuse란)
2. [설치 및 설정](#설치-및-설정)
3. [통합 방법](#통합-방법)
4. [대시보드 활용](#대시보드-활용)
5. [고급 기능](#고급-기능)

---

## LangFuse란?

### LangFuse = LLM Observability Platform

**핵심 기능**:
- 🔍 **Tracing**: 모든 LLM 호출 추적
- 💰 **Cost Tracking**: 비용 실시간 모니터링
- 📊 **Analytics**: 성능 분석 및 인사이트
- 📝 **Prompt Management**: 프롬프트 버전 관리
- 🧪 **A/B Testing**: 프롬프트 실험 및 비교
- 🔔 **Alerting**: 이상 상황 알림

### 왜 LangFuse가 필요한가?

**Without LangFuse**:
```
❌ LLM 호출 비용 모름 → 예산 초과 위험
❌ 성능 병목 찾기 어려움 → 최적화 불가
❌ 에러 원인 파악 어려움 → 디버깅 시간 증가
❌ 프롬프트 품질 평가 불가 → 개선 속도 저하
```

**With LangFuse**:
```
✅ 비용 실시간 추적 → 예산 관리 가능
✅ 병목 구간 시각화 → 타겟 최적화
✅ 에러 트레이스 제공 → 빠른 디버깅
✅ 프롬프트 성능 비교 → 데이터 기반 개선
```

---

## 설치 및 설정

### Option 1: Cloud (권장 - 빠른 시작)

#### 1. 회원가입

```bash
# 1. https://cloud.langfuse.com 접속
# 2. Sign up with GitHub/Google
# 3. 새 프로젝트 생성: "AgentHQ"
```

#### 2. API Keys 획득

```bash
# Settings > API Keys > Create New Key

# 3가지 키 복사:
# - Public Key:  pk-lf-...
# - Secret Key:  sk-lf-...
# - Host URL:    https://cloud.langfuse.com
```

#### 3. 환경 변수 설정

```bash
# backend/.env
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

#### 4. Python 패키지 설치

```bash
cd backend
pip install langfuse==2.6.0 langfuse-langchain==2.6.0
```

---

### Option 2: Self-Hosted (엔터프라이즈)

#### 1. Docker Compose로 배포

```yaml
# docker-compose.langfuse.yml
version: '3.8'

services:
  langfuse-server:
    image: langfuse/langfuse:latest
    container_name: langfuse-server
    ports:
      - "3000:3000"
    environment:
      # Database
      DATABASE_URL: postgresql://postgres:postgres@langfuse-db:5432/langfuse

      # Auth
      NEXTAUTH_SECRET: your-super-secret-key-change-me
      NEXTAUTH_URL: http://localhost:3000

      # Optional: Email (SMTP)
      # EMAIL_FROM: noreply@yourdomain.com
      # SMTP_HOST: smtp.gmail.com
      # SMTP_PORT: 587
      # SMTP_USER: your-email@gmail.com
      # SMTP_PASSWORD: your-app-password

    depends_on:
      - langfuse-db
    restart: unless-stopped

  langfuse-db:
    image: postgres:15-alpine
    container_name: langfuse-db
    environment:
      POSTGRES_DB: langfuse
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - langfuse-db-data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  langfuse-db-data:
```

#### 2. 실행

```bash
# 실행
docker-compose -f docker-compose.langfuse.yml up -d

# 로그 확인
docker-compose -f docker-compose.langfuse.yml logs -f

# 접속
# http://localhost:3000
```

#### 3. 초기 설정

```bash
# 1. http://localhost:3000 접속
# 2. 계정 생성
# 3. 프로젝트 생성
# 4. API Keys 생성

# .env 설정
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

---

## 통합 방법

### 1. 기본 통합 (LangChain)

```python
# backend/app/core/langfuse.py

from langfuse import Langfuse
from langfuse.callback import CallbackHandler
import os

# LangFuse Client 초기화
langfuse_client = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST"),
)


def get_langfuse_handler(
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict | None = None,
) -> CallbackHandler:
    """LangFuse Callback Handler 생성"""
    return CallbackHandler(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST"),
        user_id=user_id,
        session_id=session_id,
        metadata=metadata or {},
    )
```

### 2. Agent 통합

```python
# backend/app/agents/base.py

from app.core.langfuse import get_langfuse_handler

class BaseAgent:
    def __init__(self, user_id: str, session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or f"session_{user_id}"

        # LangFuse Handler
        self.langfuse_handler = get_langfuse_handler(
            user_id=self.user_id,
            session_id=self.session_id,
            metadata={
                "agent_type": self.__class__.__name__,
                "version": "1.0",
            },
        )

        # LLM에 Handler 연결
        self.llm = ChatOpenAI(
            model="gpt-4",
            callbacks=[self.langfuse_handler],
        )

    async def run(self, prompt: str):
        """Agent 실행 - 자동으로 LangFuse에 로깅"""
        result = await self.agent_executor.ainvoke(
            {"input": prompt},
            config={
                "callbacks": [self.langfuse_handler],
            },
        )
        return result
```

### 3. Custom Trace 추가

```python
from langfuse.decorators import observe, langfuse_context

@observe()  # 자동 Trace
async def process_document(doc_id: str, user_id: str):
    """문서 처리 - LangFuse가 자동 추적"""

    # Span 추가 (세부 단계 추적)
    langfuse_context.update_current_trace(
        user_id=user_id,
        metadata={"doc_id": doc_id},
    )

    # 1. 문서 로드
    with langfuse_context.observe(name="load_document") as span:
        doc = load_document(doc_id)
        span.update(output={"doc_size": len(doc)})

    # 2. Agent 실행
    agent = ResearchAgent(user_id=user_id)
    result = await agent.run(f"Summarize: {doc}")

    # 3. 결과 저장
    with langfuse_context.observe(name="save_result"):
        save_result(result)

    return result
```

### 4. Score & Feedback 추가

```python
from langfuse import Langfuse

langfuse = Langfuse()

# User Feedback 기록
def record_user_feedback(trace_id: str, rating: int, comment: str = ""):
    """사용자 피드백 기록"""
    langfuse.score(
        trace_id=trace_id,
        name="user_rating",
        value=rating,  # 1-5
        comment=comment,
    )

# Quality Score 기록
def record_quality_score(trace_id: str, quality: float):
    """품질 점수 기록 (자동 평가)"""
    langfuse.score(
        trace_id=trace_id,
        name="quality_score",
        value=quality,  # 0-1
    )

# 사용 예시
@observe()
async def generate_report(prompt: str, user_id: str):
    result = await agent.run(prompt)

    # 자동 품질 평가
    quality = evaluate_quality(result)
    record_quality_score(
        trace_id=langfuse_context.get_current_trace_id(),
        quality=quality,
    )

    return result
```

---

## 대시보드 활용

### 1. Traces (호출 추적)

**기능**:
- 모든 LLM 호출 내역 확인
- 입력/출력 검토
- 실행 시간 분석
- 에러 추적

**활용 방법**:
```
1. Traces 탭 접속
2. 필터링:
   - User ID
   - Session ID
   - Date Range
   - Status (success/error)
3. 상세 보기:
   - Input Prompt
   - Output
   - Token Usage
   - Latency
   - Error Message (있을 경우)
```

### 2. Sessions (세션 추적)

**기능**:
- 사용자별 대화 흐름 확인
- Multi-turn 대화 분석
- 세션 성능 평가

**활용 방법**:
```
1. Sessions 탭 접속
2. 특정 세션 선택
3. 대화 흐름 확인:
   - 각 턴의 Input/Output
   - 누적 비용
   - 평균 응답 시간
```

### 3. Metrics (성능 지표)

**주요 지표**:
```yaml
비용:
  - Total Cost: 총 비용
  - Cost per User: 사용자당 비용
  - Cost per Session: 세션당 비용

성능:
  - Avg Latency: 평균 응답 시간
  - P95 Latency: 95% 백분위수
  - Error Rate: 에러 발생률

사용량:
  - Total Tokens: 총 토큰 수
  - Tokens per Request: 요청당 토큰
  - Requests per Minute: 분당 요청 수
```

**활용**:
```
1. Metrics 탭 접속
2. 기간 선택 (Last 7 days, Last 30 days, Custom)
3. 그래프 분석:
   - Cost Trend: 비용 추이
   - Latency Distribution: 응답 시간 분포
   - Token Usage: 토큰 사용 패턴
4. 이상 탐지:
   - 비용 급증 시점 확인
   - 성능 저하 구간 파악
```

### 4. Prompts (프롬프트 관리)

**기능**:
- 프롬프트 버전 관리
- A/B 테스트
- 성능 비교

**활용 방법**:
```python
# 1. 프롬프트 등록
from langfuse import Langfuse

langfuse = Langfuse()

langfuse.create_prompt(
    name="research_agent_v1",
    prompt="You are a research agent...",
    config={"model": "gpt-4", "temperature": 0.7},
)

# 2. 프롬프트 사용
prompt = langfuse.get_prompt("research_agent_v1")

# 3. LLM 호출
result = llm.invoke(prompt.prompt)

# 4. 대시보드에서 성능 비교
# - v1 vs v2 비교
# - 평균 품질 점수
# - 비용 차이
```

### 5. Users & Analytics

**사용자 분석**:
```
1. Users 탭 접속
2. 사용자별 통계:
   - 총 요청 수
   - 총 비용
   - 평균 만족도
   - 주요 사용 기능
3. 코호트 분석:
   - 신규 vs 기존 사용자
   - 사용 패턴 차이
```

---

## 고급 기능

### 1. Custom Metadata

```python
@observe()
async def complex_workflow(user_id: str, task_type: str):
    # Trace에 Custom Metadata 추가
    langfuse_context.update_current_trace(
        user_id=user_id,
        metadata={
            "task_type": task_type,
            "environment": "production",
            "version": "1.2.0",
            "feature_flags": {
                "new_ui": True,
                "beta_feature": False,
            },
        },
        tags=["production", "high-priority"],
    )

    # 작업 수행
    result = await perform_task(task_type)

    # 결과 메타데이터
    langfuse_context.update_current_observation(
        output={
            "result": result,
            "metrics": {
                "processing_time": 1.23,
                "items_processed": 42,
            },
        },
    )

    return result
```

### 2. Error Tracking & Alerting

```python
from langfuse import Langfuse

langfuse = Langfuse()

@observe()
async def resilient_agent_run(prompt: str, user_id: str):
    try:
        result = await agent.run(prompt)
        return result

    except Exception as e:
        # 에러 정보 상세 기록
        langfuse_context.update_current_trace(
            status_message=str(e),
            level="ERROR",
            metadata={
                "error_type": type(e).__name__,
                "error_details": str(e),
                "user_id": user_id,
                "prompt": prompt,
            },
        )

        # 대시보드에서 Alert 설정:
        # 1. Alerts 탭
        # 2. Create Alert Rule
        # 3. Condition: error_rate > 5% in 5 minutes
        # 4. Notification: Email/Slack

        raise
```

### 3. A/B Testing

```python
import random
from langfuse import Langfuse

langfuse = Langfuse()

@observe()
async def ab_test_prompts(user_input: str, user_id: str):
    """두 개의 프롬프트 버전 A/B 테스트"""

    # 50/50 랜덤 배정
    variant = "A" if random.random() < 0.5 else "B"

    # Variant Metadata 기록
    langfuse_context.update_current_trace(
        metadata={
            "ab_test": True,
            "variant": variant,
        },
    )

    # 프롬프트 가져오기
    if variant == "A":
        prompt = langfuse.get_prompt("research_agent_v1")
    else:
        prompt = langfuse.get_prompt("research_agent_v2")

    # LLM 호출
    result = await llm.invoke(prompt.prompt.format(input=user_input))

    # 결과 기록
    langfuse_context.update_current_observation(
        output=result,
    )

    return result

# 대시보드에서 분석:
# 1. Traces 필터: metadata.variant = "A" or "B"
# 2. Score 비교: 평균 user_rating
# 3. 통계적 유의성 검정
# 4. 승자 결정 및 배포
```

### 4. Cost Optimization

```python
from langfuse import Langfuse

langfuse = Langfuse()

@observe()
async def cost_aware_agent(prompt: str, budget: float):
    """비용 제약 조건 하에서 Agent 실행"""

    # 현재 세션 비용 확인
    session_id = langfuse_context.get_current_trace_id()
    session_cost = get_session_cost(session_id)

    if session_cost >= budget:
        raise ValueError(f"Budget exceeded: {session_cost} >= {budget}")

    # 저비용 모델 선택
    if budget - session_cost < 0.10:  # $0.10 미만 남음
        model = "gpt-3.5-turbo"  # 저렴한 모델
    else:
        model = "gpt-4-turbo"  # 고급 모델

    langfuse_context.update_current_trace(
        metadata={
            "budget": budget,
            "session_cost": session_cost,
            "model_selected": model,
        },
    )

    # LLM 호출
    llm = ChatOpenAI(model=model)
    result = await llm.ainvoke(prompt)

    return result


def get_session_cost(session_id: str) -> float:
    """LangFuse API로 세션 비용 조회"""
    # LangFuse Dashboard에서 Session Cost API 사용
    # 또는 Traces를 집계하여 계산
    pass
```

---

## Best Practices

### 1. 구조화된 Metadata

```python
# ❌ Bad
langfuse_context.update_current_trace(
    metadata={"info": "some data"},
)

# ✅ Good
langfuse_context.update_current_trace(
    metadata={
        "user": {
            "id": user_id,
            "tier": "premium",
            "country": "KR",
        },
        "task": {
            "type": "research",
            "priority": "high",
            "estimated_tokens": 1000,
        },
        "context": {
            "session_length": 5,
            "previous_tasks": ["task1", "task2"],
        },
    },
)
```

### 2. Meaningful Trace Names

```python
# ❌ Bad
@observe(name="function1")
async def func():
    pass

# ✅ Good
@observe(name="research_agent:web_search")
async def research_web_search():
    pass

@observe(name="docs_agent:create_document")
async def create_google_doc():
    pass
```

### 3. Score Every Trace

```python
@observe()
async def generate_with_quality_check(prompt: str):
    result = await agent.run(prompt)

    # 자동 품질 평가
    quality_score = evaluate_output_quality(result)

    langfuse.score(
        trace_id=langfuse_context.get_current_trace_id(),
        name="output_quality",
        value=quality_score,
        comment=f"Automated quality check",
    )

    return result
```

### 4. Regular Dashboard Review

```
일일:
  - Error Rate 확인
  - 비용 추이 모니터링

주간:
  - 성능 트렌드 분석
  - 프롬프트 A/B 테스트 결과 확인
  - 사용자 피드백 리뷰

월간:
  - 비용 최적화 기회 탐색
  - 모델 업그레이드 검토
  - 아키텍처 개선 계획
```

---

## 참고 자료

### 공식 문서
- [LangFuse Docs](https://langfuse.com/docs)
- [Python SDK](https://langfuse.com/docs/sdk/python)
- [LangChain Integration](https://langfuse.com/docs/integrations/langchain)

### 예제
- [LangFuse Examples](https://github.com/langfuse/langfuse-docs/tree/main/cookbook)

### 커뮤니티
- [Discord](https://discord.gg/langfuse)
- [GitHub Discussions](https://github.com/langfuse/langfuse/discussions)

---

**Last Updated**: 2024-10-29
**Version**: 1.0
