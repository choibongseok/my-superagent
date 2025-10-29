# AgentHQ Documentation

이 폴더는 AgentHQ 프로젝트의 모든 문서를 포함합니다.

## 📚 문서 목록

### 개발 가이드
- **[DEV_GUIDE.md](DEV_GUIDE.md)** - 개발 환경 설정 및 실행 가이드
- **[AGENTS.md](AGENTS.md)** - AI 에이전트 시스템 문서

### Phase 구현 가이드
- **[PHASE_PLAN.md](PHASE_PLAN.md)** - 전체 Phase 계획
- **[PHASE_0_IMPLEMENTATION.md](PHASE_0_IMPLEMENTATION.md)** - LangChain & LangFuse 통합
- **[PHASE_1_IMPLEMENTATION.md](PHASE_1_IMPLEMENTATION.md)** - Core Agents (Research, Docs, Sheets, Slides)
- **[PHASE_2_IMPLEMENTATION.md](PHASE_2_IMPLEMENTATION.md)** - Intelligence & Memory
- **[PHASE_3_IMPLEMENTATION.md](PHASE_3_IMPLEMENTATION.md)** - Flutter Mobile Client
- **[PHASE_4_IMPLEMENTATION.md](PHASE_4_IMPLEMENTATION.md)** - Team Collaboration
- **[PHASE_5_IMPLEMENTATION.md](PHASE_5_IMPLEMENTATION.md)** - Performance Optimization
- **[PHASE_6_IMPLEMENTATION.md](PHASE_6_IMPLEMENTATION.md)** - Advanced Features

### PR 템플릿
- **[PR_TEMPLATE.md](PR_TEMPLATE.md)** - Pull Request 템플릿
- **[PR_DESCRIPTION.md](PR_DESCRIPTION.md)** - PR 설명 가이드
- **[PHASE0_PR.md](PHASE0_PR.md)** - Phase 0 PR 설명
- **[PHASE1_PR.md](PHASE1_PR.md)** - Phase 1 PR 설명
- **[PHASE3_PR.md](PHASE3_PR.md)** - Phase 3 PR 설명

### LangChain & LangFuse 가이드
- **[LANGCHAIN_GUIDE.md](LANGCHAIN_GUIDE.md)** - LangChain 통합 가이드
- **[LANGFUSE_SETUP.md](LANGFUSE_SETUP.md)** - LangFuse 설정 가이드
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - 기여 가이드

## 🚀 빠른 시작

프로젝트를 시작하려면 [DEV_GUIDE.md](DEV_GUIDE.md)를 참조하세요.

```bash
# 원클릭 실행
./scripts/dev.sh

# 종료
./scripts/stop.sh
```

## 📖 문서 구조

```
docs/
├── README.md                          # 이 파일
├── DEV_GUIDE.md                       # 개발 환경 가이드
├── AGENTS.md                          # 에이전트 문서
├── PHASE_PLAN.md                      # Phase 계획
├── PHASE_*_IMPLEMENTATION.md          # Phase 구현 가이드
├── PHASE*_PR.md                       # PR 설명
├── PR_TEMPLATE.md                     # PR 템플릿
├── PR_DESCRIPTION.md                  # PR 가이드
├── LANGCHAIN_GUIDE.md                 # LangChain 가이드
├── LANGFUSE_SETUP.md                  # LangFuse 가이드
└── CONTRIBUTING.md                    # 기여 가이드
```
