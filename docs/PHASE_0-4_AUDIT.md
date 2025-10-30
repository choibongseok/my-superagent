# Phase 0-4 Audit Findings

## Phase 0 — Foundation Enhancement
- `backend/app/agents/base.py:248` passes `self.memory.buffer` into the agent executor, but `ConversationMemory` exposes only the underlying memory object, not a `.buffer` attribute. Every agent initialization therefore raises `AttributeError` on first use.
- `backend/app/memory/conversation.py:40` implements the memory wrapper but never exposes `.buffer`, so the above failure reproduces consistently.
- `backend/app/prompts/templates/research.py:7` still embeds prompts directly; the new registry is never consumed by the agents, so prompt versioning from Phase 0 is unused.

## Phase 1 — Core Agent Implementation
- `backend/app/agents/sheets_agent.py:1` and `backend/app/agents/slides_agent.py:1` remain TODO stubs with no tools, prompts, or Google API integrations, leaving half the “core” agents unimplemented.
- `backend/app/agents/celery_app.py:56` calls the async `ResearchAgent.research` method without awaiting it, returning a coroutine object instead of results; the docs task does the same and even passes a non-existent `content_request` parameter (`backend/app/agents/docs_agent.py:137`).
- `backend/app/agents/celery_app.py:101` always instantiates document/slide/sheet agents with `credentials=None`, so any Google Workspace call would fail before reaching the API.

## Phase 2 — Intelligence & Memory
- `backend/app/memory/manager.py:21` defines the combined conversation/vector memory manager, but no routes or agents import it, so the Phase 2 memory layer is effectively unused.
- `backend/app/services/citation/tracker.py:1` and related models exist, yet `backend/app/agents/research_agent.py:155` still fabricates citations from tool traces instead of using the tracker, leaving citation management disconnected.

## Phase 3 — Desktop Client UI
- `desktop/src/services/api.ts:67` omits the `user` payload from the callback response type, while `desktop/src/pages/LoginPage.tsx:34` dereferences `data.user`, causing TypeScript compilation failures under strict settings.
- `desktop/src/pages/HomePage.tsx:38` reads the Zustand auth store with `getState()` inside a mount-only effect; the socket never reconnects if the store updates later, and pending chat joins can be lost before the connection opens.

## Phase 3-1 — Mobile Client (Flutter)
- `mobile/lib/features/auth/presentation/screens/login_screen.dart:17` still contains a placeholder sign-in flow that delays for one second and navigates without calling the backend, so Google OAuth is unimplemented.
- `mobile/lib/features/tasks/presentation/screens/home_screen.dart:127` renders hard-coded “샘플 작업” entries with TODO comments; no Riverpod providers or API integrations exist.
- `mobile/lib/core/storage/storage_service.dart:27` defines Hive/SecureStorage setup, but nothing invokes `init()`, so offline caching never runs.
- `mobile/pubspec.yaml:69` references launcher/splash assets that are missing from the tree, leading to Flutter build failures.

## Phase 4 — Real-time & Backend Integration
- `backend/alembic/versions/c4d39e6ece1f_add_chat_and_message_models.py:21` mixes manual `CREATE TYPE` statements with SQLAlchemy enums and references `sa.UUID` without importing the type, so applying the migration fails.
- `desktop/src/pages/HomePage.tsx:82` only joins chats if the WebSocket is already open; reconnects that occur after a selection drop messages until the user toggles chats. The server’s WebSocket messages at `backend/app/api/v1/messages.py:147` also omit fields (e.g., `updated_at`) that the UI assumes.

## Recommended Next Actions
1. Fix the agent memory wiring and finish the missing LLM/Celery integrations so Phase 0-1 features operate end-to-end.
2. Either complete or explicitly defer the Phase 2 memory/citation tooling by integrating it with agents and API responses.
3. Align both clients with the backend contracts—finish OAuth, storage, and WebSocket flows—before marking Phase 3/3-1 complete.
4. Repair the alembic migration and real-time lifecycle so Phase 4 reproducibly provisions schema and maintains chat subscriptions.
