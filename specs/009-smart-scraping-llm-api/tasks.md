# Tasks: Smart Scraping LLM API

**Input**: Design documents from `specs/009-smart-scraping-llm-api/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are requested via Constitution Principle VI (Test-First) in plan.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create project structure `src/{api,domain,infrastructure,actions,core}` and `tests/{unit,integration,contract}`
- [ ] T002 Initialize Python 3.11+ project using `uv init` and add dependencies (FastAPI, Taskiq, Playwright, Redis, Pydantic, OpenAI, HTTPX) via `uv add`
- [ ] T003 [P] Configure `ruff` for linting and `pytest` with `pytest-asyncio`
- [ ] T004 Create `src/core/config.py` for API keys, Redis URLs, and timeout settings
- [ ] T043 [P] Create `docker-compose.yml` to manage Redis service for Taskiq and caching

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

### Foundational Tests (Test-First)

- [ ] T005 [P] Write failing integration test for Redis connection in `tests/integration/test_redis.py`
- [ ] T006 [P] Write failing unit test for LLM Facade base class in `tests/unit/test_llm_facade.py`
- [ ] T007 [P] Write failing test for Static API Key auth in `tests/integration/test_auth.py`

### Foundational Implementation

- [ ] T008 [P] Implement `src/infrastructure/queue/broker.py` for Taskiq Redis broker setup (connect to Redis via Docker)
- [ ] T009 [P] Implement `src/infrastructure/browser/pool_manager.py` for global Playwright browser instance management
- [ ] T010 [P] Implement `src/infrastructure/external_api/facade.py` base `LLMFacade` for modular provider management
- [ ] T011 [P] Implement Static API Key authentication middleware in `src/api/auth.py`
- [ ] T012 Implement base DSL Command models in `src/domain/models/dsl.py`
- [ ] T013 Implement Action Registry in `src/domain/registry/action_registry.py`
- [ ] T014 [P] Implement `src/infrastructure/queue/workers.py` to host Taskiq workers

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Fast Atomic Scraping (Priority: P1) 🎯 MVP

**Goal**: High-throughput stateless scraping and Google search.

**Independent Test**: Send a request to `POST /scraper` or `POST /serper` and receive valid content/results without session state.

### Tests for User Story 1 (Test-First)

- [ ] T015 [P] [US1] Write failing contract test for `/scraper` and `/serper` in `tests/contract/test_stateless.py`
- [ ] T016 [P] [US1] Write failing integration test for Playwright atomic scrape in `tests/integration/test_atomic_scrape.py`
- [ ] T017 [P] [US1] Write failing contract test for `/omni-parse` and `/jina-extract` in `tests/contract/test_analysis.py`

### Implementation for User Story 1

- [ ] T018 [P] [US1] Create `ScrapeTask` model in `src/domain/models/requests.py`
- [ ] T019 [US1] Implement stateless browser context management in `src/infrastructure/browser/pool_manager.py`
- [ ] T020 [US1] Implement `POST /scraper` endpoint in `src/api/routers/stateless.py`
- [ ] T021 [US1] Implement Serper-compatible search transformation in `src/infrastructure/external_api/search_client.py`
- [ ] T022 [US1] Implement `POST /serper` endpoint in `src/api/routers/stateless.py`
- [ ] T023 [P] [US1] Implement proxy round-robin selection from local file in `src/infrastructure/browser/proxy_provider.py`
- [ ] T024 [P] [US1] Implement Omni-Parser analysis endpoint `POST /omni-parse` in `src/api/routers/stateless.py`
- [ ] T025 [P] [US1] Implement Jina extraction endpoint `POST /jina-extract` in `src/api/routers/stateless.py`

**Checkpoint**: User Story 1 (Atomic Scraper & Search) is fully functional.

---

## Phase 4: User Story 2 - Interactive Session Tools (Priority: P2)

**Goal**: Stateful sessions with browser ownership and DSL command execution.

**Independent Test**: Initiate a session via `POST /sessions`, connect via WebSocket, and execute a `screenshot` command.

### Tests for User Story 2 (Test-First)

- [ ] T026 [P] [US2] Write failing contract test for `/sessions` and WebSocket in `tests/contract/test_sessions.py`
- [ ] T027 [P] [US2] Write failing integration test for Taskiq Actor browser session in `tests/integration/test_session_actor.py`
- [ ] T028 [P] [US2] Write failing unit tests for DSL actions (click, fill, goto) in `tests/unit/test_actions.py`

### Implementation for User Story 2

- [ ] T029 [P] [US2] Create `InteractiveSession` model in `src/domain/models/dsl.py`
- [ ] T030 [US2] Implement Taskiq Actor for isolated browser sessions in `src/infrastructure/queue/session_actor.py`
- [ ] T031 [US2] Implement Redis Pub/Sub coordination for WebSockets in `src/api/websockets/manager.py`
- [ ] T032 [US2] Implement `POST /sessions` endpoint in `src/api/routers/sessions.py`
- [ ] T033 [US2] Implement WebSocket handler for command loop in `src/api/websockets/handler.py`
- [ ] T034 [P] [US2] Implement navigation actions (goto, scroll) in `src/actions/navigation.py`
- [ ] T035 [P] [US2] Implement interaction actions (click_coord, fill) in `src/actions/interaction.py`
- [ ] T036 [P] [US2] Implement extraction actions (screenshot, get_dom) in `src/actions/extraction.py`
- [ ] T037 [US2] Integrate Omni-click and Jina-extract into session actions in `src/actions/ai_actions.py`

**Checkpoint**: User Story 2 (Stateful Sessions) is fully functional.

---

## Phase 5: User Story 3 - Resource Recovery and Timeout (Priority: P3)

**Goal**: Automatic cleanup of idle sessions.

**Independent Test**: Create a session, wait for inactivity timeout, and verify the Taskiq process/browser context is closed.

### Tests for User Story 3 (Test-First)

- [ ] T038 [P] [US3] Write failing unit test for inactivity monitor in `tests/unit/test_cleanup.py`
- [ ] T039 [US3] Write failing integration test for session auto-termination in `tests/integration/test_timeout.py`

### Implementation for User Story 3

- [ ] T040 [US3] Implement inactivity tracking in `src/infrastructure/browser/session_manager.py`
- [ ] T041 [US3] Implement background cleanup task for timed-out sessions in `src/infrastructure/queue/cleanup_worker.py`
- [ ] T042 [US3] Implement Fail-Fast blocking detection and error reporting in `src/infrastructure/browser/session_manager.py`

**Checkpoint**: User Story 3 (Resource Management) is fully functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T038 [P] Verify compliance with Constitution Principles (I-VI)
- [ ] T039 [P] Update `README.md` and `quickstart.md` with final API examples
- [ ] T040 Finalize error handling and logging formatting in `src/core/logging.py`
- [ ] T041 Run full suite of contract and integration tests using `uv run pytest`
- [ ] T042 [P] Security audit of static API key implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on T001-T004.
- **User Stories (Phase 3-5)**: Depend on Phase 2 completion.
  - US1 (Phase 3) is independent and can start first.
  - US2 (Phase 4) depends on foundation but is independent of US1.
  - US3 (Phase 5) depends on US2 (session infrastructure).
- **Polish (Phase 6)**: Depends on all stories.

### Parallel Opportunities

- T005-T008 can run in parallel.
- US1 (Phase 3) and US2 (Phase 4) can start in parallel once Phase 2 is done.
- T029-T031 (DSL Actions) can be implemented in parallel.
- All tasks marked [P] can be executed concurrently.

---

## Parallel Example: Phase 3 (US1)

```bash
# Implement search and extraction endpoints in parallel
Task: "T017 [US1] Implement Serper-compatible search transformation in src/infrastructure/external_api/search_client.py"
Task: "T020 [P] [US1] Implement Omni-Parser analysis endpoint POST /omni-parse in src/api/routers/stateless.py"
Task: "T021 [P] [US1] Implement Jina extraction endpoint POST /jina-extract in src/api/routers/stateless.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 & 2.
2. Complete Phase 3 (User Story 1).
3. **STOP and VALIDATE**: Verify atomic scraping and search work as a standalone high-throughput service.

### Incremental Delivery

1. Deliver US1 as MVP.
2. Deliver US2 to enable interactive orchestration.
3. Deliver US3 to ensure production stability and resource efficiency.
