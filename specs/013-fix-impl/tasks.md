---

description: "Task list for Fix Existing Implementations"
---

# Tasks: Fix Existing Implementations

**Input**: Design documents from `/specs/013-fix-impl/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md

**Tests**: TDD is MANDATORY per Constitution Principle VI (FR-009, FR-010). All tests must verify REAL functionality, not placeholders.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Environment and configuration updates

**Dependencies**: None

- [X] T001 Add MAX_CONCURRENT_RESEARCH_TASKS to .env.example with default value 5
- [X] T002 Add EXTRACTION_MODEL_NAME to .env.example with default value jinaai.readerlm-v2

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Error handling infrastructure used by all endpoints

**Dependencies**: Phase 1

**⚠️ CRITICAL**: User stories can begin after this phase

- [X] T003 [P] Create standard error response helper in src/api/utils/errors.py (error: str, code: str, details?: object)
- [X] T004 [P] Add RedisUnavailableError exception class in src/domain/models/errors.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Google Search via Playwright (Priority: P1) 🎯 MVP

**Goal**: Implement real Google search via Playwright with proxy support

**Independent Test**: Call `/serper` endpoint with a query, verify real Google results returned

### Tests for User Story 1 (TDD - Write FIRST) ⚠️

- [X] T005 [P] [US1] Contract test for /serper endpoint in tests/contract/test_google_search.py
- [X] T006 [P] [US1] Integration test for Google search with Playwright in tests/integration/test_google_search.py

### Implementation for User Story 1

- [X] T007 [P] [US1] Create SearchResult model in src/domain/models/requests.py
- [X] T008 [US1] Implement GoogleSearchClient in src/infrastructure/external_api/search_client.py
  - Use headless Playwright browser
  - Navigate to google.com/search?q={query}
  - Extract titles (h3), links (a[href^="/url?q="]), snippets
  - Return SearchResult[]
- [X] T009 [US1] Update /serper endpoint in src/api/routers/stateless.py
  - Use GoogleSearchClient instead of mock
  - Apply proxy rotation from proxy_provider
  - Handle blocking with clear error message

**Checkpoint**: User Story 1 fully functional

---

## Phase 4: User Story 2 - HTML to Markdown Conversion (Priority: P1)

**Goal**: Replace Jina Reader with markdownify library, rename endpoint to /html-to-md

**Independent Test**: Call `/html-to-md` with HTML, verify clean Markdown returned

### Tests for User Story 2 (TDD - Write FIRST) ⚠️

- [X] T010 [P] [US2] Contract test for /html-to-md endpoint in tests/contract/test_html_to_md.py
- [X] T011 [P] [US2] Integration test for HTML-to-Markdown conversion in tests/integration/test_html_to_md.py

### Implementation for User Story 2

- [X] T012 [US2] Add markdownify to dependencies: uv add markdownify
- [X] T013 [US2] Create html_to_markdown() function in src/domain/utils/content_cleaner.py
  - Use markdownify library
  - Support output_format: markdown (default), text
- [X] T014 [US2] Rename JinaExtractRequest to HtmlToMdRequest in src/domain/models/requests.py
  - Keep html field
  - Change format field options: markdown, text
- [X] T015 [US2] Rename /jina-extract to /html-to-md in src/api/routers/stateless.py
  - Use html_to_markdown() from content_cleaner
  - Return converted content
- [X] T016 [US2] Remove extraction_client from stateless.py (no longer needed)

**Checkpoint**: User Story 2 fully functional

---

## Phase 5: User Story 3 - Sessions with Proper Error Handling (Priority: P1)

**Goal**: Handle Redis failures gracefully with HTTP 503 instead of 500

**Independent Test**: Verify session endpoints return 503 when Redis is unavailable

### Tests for User Story 3 (TDD - Write FIRST) ⚠️

- [X] T015 [P] [US3] Contract test for Redis error handling in tests/contract/test_sessions.py
- [X] T016 [P] [US3] Integration test for session Redis failure in tests/integration/test_session_redis_failure.py

### Implementation for User Story 3

- [X] T017 [US3] Update create_session endpoint in src/api/routers/sessions.py
  - Wrap run_session_actor.kiq() in try/except
  - Catch redis.exceptions.ConnectionError
  - Return HTTP 503 with standard error format
- [X] T018 [US3] Update command endpoint in src/api/routers/sessions.py
  - Wrap manager.publish_command() in try/except
  - Return HTTP 503 when Redis unavailable
- [X] T019 [US3] Update delete_session endpoint in src/api/routers/sessions.py
  - Add Redis error handling
- [X] T020 [US3] Update WebSocket manager in src/api/websockets/manager.py
  - Add error handling in publish_command()
  - Add error handling in subscribe_results()

**Checkpoint**: User Story 3 fully functional

---

## Phase 6: User Story 4 - Research Agent via Taskiq (Priority: P2)

**Goal**: Wire up Taskiq execution so research tasks actually run

**Independent Test**: Submit research query, verify task executes and produces report

### Tests for User Story 4 (TDD - Write FIRST) ⚠️

- [ ] T021 [P] [US4] Contract test for research endpoint in tests/contract/test_research_endpoint.py
- [ ] T022 [P] [US4] Integration test for research graph execution in tests/integration/test_research_graph.py

### Implementation for User Story 4

- [ ] T023 [US4] Create research task function in src/actions/research/__init__.py
  - Decorate with @search_broker.task
  - Call build_graph() with task_id
  - Update _task_store with results
- [ ] T024 [US4] Update run_research endpoint in src/api/routers/research.py
  - Call execute_research_task.kiq(task_id)
  - Return 202 immediately
- [ ] T025 [US4] Update web_search tool in src/actions/research/tools.py
  - Use GoogleSearchClient instead of fake URLs
- [ ] T026 [US4] Add MAX_CONCURRENT_RESEARCH_TASKS check in src/api/routers/research.py
  - Read from settings
  - Return 429 when exceeded

**Checkpoint**: User Story 4 fully functional

---

## Phase 7: User Story 5 - Scraper with HTML Cleaning (Priority: P2)

**Goal**: Add clean_html and output_format parameters to /scraper endpoint

**Independent Test**: Call /scraper with clean_html=true, verify cleaned content

### Tests for User Story 5 (TDD - Write FIRST) ⚠️

- [X] T027 [P] [US5] Contract test for scraper with cleaning in tests/contract/test_scraper.py
- [X] T028 [P] [US5] Integration test for HTML cleaning in tests/integration/test_content_cleaning.py

### Implementation for User Story 5

- [X] T029 [US5] Update ScrapeRequest in src/domain/models/requests.py
  - Add clean_html: bool = False
  - Add output_format: Literal["html", "text", "markdown"] = "html"
- [X] T030 [US5] Update /scraper endpoint in src/api/routers/stateless.py
  - If clean_html=True → use ContentCleaner (strip scripts/styles)
  - If output_format="text" → use html_to_text()
  - If output_format="markdown" → use html_to_markdown()

**Checkpoint**: User Story 5 fully functional

---

## Phase 8: Contract Tests Rewrite (Priority: P2)

**Goal**: Fix all contract tests to import real routers, not placeholders

**Dependencies**: Phase 3 (Serper), Phase 4 (HTML-to-MD), Phase 5 (Sessions)

### Tests Rewrite

- [X] T033 [US5] Rewrite tests/contract/test_stateless.py
  - Import actual stateless router
  - Include router in test app
  - Add assertions for response structure
- [X] T034 [US5] Rename tests/contract/test_analysis.py → tests/contract/test_html_to_md.py
  - Import actual router
  - Test /html-to-md endpoint
  - Verify Markdown response
- [X] T035 [US5] Update tests/contract/test_sessions.py
  - Test Redis error handling
  - Verify 503 responses

**Checkpoint**: All tests verify real functionality

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [ ] T036 [P] Run uv run ruff check src tests
- [ ] T037 [P] Run uv run mypy src
- [ ] T038 Run full test suite: python -m pytest tests/ -q
- [ ] T039 [P] Update AGENTS.md with new technologies
- [ ] T040 Update README.md with new endpoints
- [ ] T041 Verify compliance with Constitution Principles (I-X)

---

## Dependencies & Execution Order

### Phase Dependencies

| Phase | Depends On | Blocks |
|-------|-----------|--------|
| Phase 1: Setup | None | Phase 2 |
| Phase 2: Foundational | Phase 1 | All User Stories |
| Phase 3: US1 (Serper) | Phase 2 | Phase 8 |
| Phase 4: US2 (HTML-to-MD) | Phase 2 | Phase 8 |
| Phase 5: US3 (Sessions) | Phase 2 | Phase 8 |
| Phase 6: US4 (Research) | Phase 3 | None |
| Phase 7: US5 (Scraper) | Phase 2 | Phase 8 |
| Phase 8: Tests | US1, US2, US3, US5 | Phase 9 |
| Phase 9: Polish | All | None |

### User Story Independence

- **User Story 1 (P1)**: No dependencies on other stories
- **User Story 2 (P1)**: No dependencies on other stories
- **User Story 3 (P1)**: No dependencies on other stories
- **User Story 4 (P2)**: Depends on US1 (uses Google search)
- **User Story 5 (P2)**: No dependencies on other stories

### Parallel Opportunities

- Phase 3, 4, 5, 7 can run in parallel after Phase 2
- Within each phase, tasks marked [P] can run in parallel
- US4 (Phase 6) must wait for US1 (Phase 3) completion

---

## Implementation Strategy

### MVP First (User Story 1 + Foundational)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (Serper)
4. **STOP and VALIDATE**: Test Serper independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Phase 1 + 2 → Foundation ready
2. Add Phase 3 (Serper) → Test independently → Deploy (MVP!)
3. Add Phase 4 (HTML-to-MD) → Test independently → Deploy
4. Add Phase 5 (Sessions) → Test independently → Deploy
5. Add Phase 6 (Research) → Test independently → Deploy
6. Add Phase 7 (Scraper) → Test independently → Deploy
7. Rewrite Phase 8 (Tests) → All tests pass
8. Polish Phase 9

---

## Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 40 |
| Completed | 29 |
| Remaining | 11 |

### Completed
| Phase | Tasks | Status |
|-------|-------|--------|
| Setup | T001-T002 | ✅ 2/2 |
| Foundational | T003-T004 | ✅ 2/2 |
| US1 (Serper) | T005-T009 | ✅ 5/5 |
| US2 (HTML-to-MD) | T010-T016 | ✅ 7/7 |
| US3 (Sessions) | T015-T020 | ✅ 6/6 |
| US5 (Scraper) | T027-T030 | ✅ 4/4 |
| Tests Rewrite | T033-T035 | ✅ 3/3 |

### Remaining
| Phase | Tasks | Status |
|-------|-------|--------|
| US4 (Research) | T021-T026 | ⏳ 0/6 |
| Polish | T036-T041 | ⏳ 0/6 |

**New Dependency Added**: `markdownify` library for HTML → Markdown conversion

**Test Results**: 51 passed (all rewritten tests)

**Tests per Story**: Contract + Integration per Constitution VI (TDD)
