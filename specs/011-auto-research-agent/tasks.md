---

description: "Task list for Auto-Research Agent implementation"
---

# Tasks: Auto-Research Agent

**Input**: Design documents from `/specs/011-auto-research-agent/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: REQUIRED per Constitution Principle VI (Test-First) - all test files must be created RED before implementation

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root
- Paths shown below follow existing project structure in `src/` and `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Add LangGraph and LangChain dependencies to pyproject.toml
- [X] T002 [P] Verify LangGraph/LangChain versions are compatible with Python 3.12

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Create ResearchMode enum in src/domain/models/research.py
- [X] T004 [P] Create ResearchRequest Pydantic model in src/domain/models/research.py
- [X] T005 [P] Create ResearchReport, Citation, Fact, ResearchStats models in src/domain/models/research.py
- [X] T006 Create ResearchState TypedDict for LangGraph state in src/actions/research/state.py
- [ ] T007 [P] Setup Redis task storage helper for research tasks in src/infrastructure/tasks/research_store.py
- [ ] T008 Configure rate limiting for concurrent research tasks (max 5 per API key) in src/api/middleware/rate_limit.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Submit Research Query and Receive Report (Priority: P1) 🎯 MVP

**Goal**: Users submit a natural-language research question and receive a structured report with cited sources

**Independent Test**: POST /api/v1/research/run returns 202 with task_id; GET /api/v1/research/status/{id} returns final report with answer_markdown, citations, facts, stats

### Tests for User Story 1 (TDD - Write FIRST, must FAIL) ⚠️

- [ ] T009 [P] [US1] Contract test: POST /research/run with valid body + API key → 202 {task_id} in tests/contract/test_research_endpoint.py
- [ ] T010 [P] [US1] Contract test: POST /research/run without API key → 401 in tests/contract/test_research_endpoint.py
- [ ] T011 [P] [US1] Contract test: POST /research/run with invalid mode → 422 in tests/contract/test_research_endpoint.py
- [ ] T012 [P] [US1] Contract test: POST /research/run when API key has 5 running tasks → 429 in tests/contract/test_research_endpoint.py
- [ ] T013 [P] [US1] Contract test: GET /research/status/{task_id} after completion returns ResearchReport in tests/contract/test_research_endpoint.py
- [ ] T014 [P] [US1] Contract test: GET /research/status/{fake_id} → 404 in tests/contract/test_research_endpoint.py
- [ ] T015 [US1] Unit test: Each graph node transforms state correctly in tests/unit/research/test_nodes.py
- [ ] T016 [US1] Unit test: State transition router truth table in tests/unit/research/test_state_transitions.py

### Implementation for User Story 1

- [ ] T017 [P] [US1] Implement research router endpoint in src/api/routers/research.py
- [ ] T018 [P] [US1] Implement Taskiq task queue setup for research in src/actions/research_task.py
- [ ] T019 [US1] Create LangGraph state graph definition in src/domain/research_graph/__init__.py
- [ ] T020 [US1] Implement classify node in src/domain/research_graph/nodes.py (depends on T019)
- [ ] T021 [US1] Implement plan node in src/domain/research_graph/nodes.py
- [ ] T022 [US1] Implement search node in src/domain/research_graph/nodes.py
- [ ] T023 [US1] Implement rank_dedupe node in src/domain/research_graph/nodes.py
- [ ] T024 [US1] Implement scrape node in src/domain/research_graph/nodes.py
- [ ] T025 [US1] Implement extract_facts node in src/domain/research_graph/nodes.py
- [ ] T026 [US1] Implement reflect node in src/domain/research_graph/nodes.py
- [ ] T027 [US1] Implement answer node in src/domain/research_graph/nodes.py
- [ ] T028 [US1] Integrate LLMFacade for query classification and fact extraction
- [ ] T029 [US1] Add validation and error handling for research endpoints
- [ ] T030 [US1] Add node-level structured logging per FR-021

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Choose Research Depth by Mode (Priority: P2)

**Goal**: Users select research mode (speed/balanced/quality) to trade off speed against depth

**Independent Test**: Mode preset values produce correct state initialization; user overrides take precedence

### Tests for User Story 2 (TDD - Write FIRST, must FAIL) ⚠️

- [ ] T031 [P] [US2] Unit test: Mode preset values verified in tests/unit/research/test_modes.py
- [ ] T032 [P] [US2] Unit test: Mode → state initialization produces correct defaults in tests/unit/research/test_modes.py
- [ ] T033 [P] [US2] Unit test: User-supplied overrides take precedence over mode defaults in tests/unit/research/test_modes.py

### Implementation for User Story 2

- [ ] T034 [P] [US2] Define mode presets (speed/balanced/quality) with max_iters, search_k, scrape_concurrency, token_budget, deadline in src/actions/research/modes.py
- [ ] T035 [US2] Implement mode-to-state initialization function in src/actions/research/modes.py
- [ ] T036 [US2] Add mode validation (speed/balanced/quality only) in src/api/routers/research.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Guaranteed Completion with Graceful Degradation (Priority: P2)

**Goal**: System always returns a best-effort answer even when resource limits are hit

**Independent Test**: Graph terminates within max_iters, emits valid ResearchReport, tiny budget forces beast-mode but still produces answer

### Tests for User Story 3 (TDD - Write FIRST, must FAIL) ⚠️

- [ ] T037 [P] [US3] Unit test: tokens_used >= 85% token_budget triggers beast_mode in tests/unit/research/test_nodes.py
- [ ] T038 [P] [US3] Unit test: time > deadline_ts triggers beast_mode in tests/unit/research/test_nodes.py
- [ ] T039 [P] [US3] Unit test: stall_counter >= 2 triggers beast_mode in tests/unit/research/test_nodes.py
- [ ] T040 [P] [US3] Unit test: Zero new URLs after ranking increments stall_counter in tests/unit/research/test_nodes.py
- [ ] T041 [US3] Integration test: Full graph terminates within max_iters, emits valid ResearchReport in tests/integration/test_research_graph.py
- [ ] T042 [US3] Integration test: Tiny token_budget → beast_mode triggers → answer still produced in tests/integration/test_research_graph.py

### Implementation for User Story 3

- [ ] T043 [P] [US3] Implement beast_mode state flag activation logic in src/domain/research_graph/nodes.py
- [ ] T044 [P] [US3] Implement stall detection (zero new URLs) counter in src/domain/research_graph/nodes.py
- [ ] T045 [US3] Implement deadline enforcement (wall-clock timeout) in src/domain/research_graph/state.py
- [ ] T046 [US3] Implement beast-mode routing (skip to answer node) in src/domain/research_graph/__init__.py
- [ ] T047 [US3] Ensure answer always produced even if degraded in src/domain/research_graph/nodes.py

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should work together

---

## Phase 6: User Story 4 - Monitor Research Progress in Real Time (Priority: P3)

**Goal**: Users observe research agent's decision-making via SSE events

**Independent Test**: SSE events emitted in order during graph traversal

### Tests for User Story 4 (TDD - Write FIRST, must FAIL) ⚠️

- [ ] T048 [P] [US4] Integration test: Graph traversal emits node events in expected order in tests/integration/test_research_graph.py
- [ ] T049 [P] [US4] Contract test: GET /research/stream/{task_id} delivers events as emitted in tests/contract/test_research_endpoint.py

### Implementation for User Story 4

- [ ] T050 [P] [US4] Implement SSE endpoint in src/api/routers/research.py
- [ ] T051 [US4] Add node-entered/node-exited event emission in src/actions/research/nodes.py

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T052 [P] Verify compliance with Constitution Principles (I-X) in src/actions/research/
- [ ] T053 [P] Add doc.md to new directories (src/actions/research/, src/api/routers/)
- [ ] T054 Run quickstart.md validation (test endpoints with curl)
- [ ] T055 Code cleanup and refactoring
- [ ] T056 [P] Run uv run ruff check src tests
- [ ] T057 [P] Run uv run mypy src
- [ ] T058 Run full test suite: python -m pytest tests/ -q

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Should be independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Should be independently testable
- **User Story 4 (P3)**: Can start after Foundational (Phase 2) - Depends on US1 graph implementation

### Within Each User Story

- Tests (TDD) MUST be written and FAIL before implementation
- Models before services
- Graph nodes before graph compilation
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- All test tasks for a story marked [P] can run in parallel
- Model tasks within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Contract test for POST /research/run in tests/contract/test_research_endpoint.py"
Task: "Contract test for GET /research/status/{id} in tests/contract/test_research_endpoint.py"
Task: "Unit test for node transformations in tests/unit/research/test_nodes.py"
Task: "Unit test for state transitions in tests/unit/research/test_state_transitions.py"

# Launch all model implementations together:
Task: "Create ResearchRequest, ResearchReport, Citation, Fact, ResearchStats in src/domain/models/research.py"
Task: "Create ResearchState TypedDict in src/domain/research_graph/state.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD - RED before GREEN)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- All 58 tasks follow the checklist format with Task ID, [P] marker, [Story] label, and file paths