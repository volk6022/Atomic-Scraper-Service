---

description: "Task list for Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration"
---

# Tasks: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Input**: Design documents from `/specs/010-scraper-mlcv-prep/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are REQUIRED per Constitution Principle VI (Test-First) - all functional requirements MUST have failing test cases BEFORE implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create Dockerfile based on Playwright Python image with all browser dependencies (per FR-001)
- [X] T002 Update docker-compose.yml to include api, worker, and redis services with proper networking (per FR-002)
- [X] T003 [P] Configure docker healthcheck for api service to hit `/healthz` endpoint

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests for Foundational (TDD - Red Phase) ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T004 [P] Write failing contract test for `/healthz` endpoint in tests/contract/test_health_endpoint.py
- [X] T005 [P] Write failing integration test for docker-compose in tests/integration/test_docker_compose.py

### Implementation for Foundational

- [X] T006 Create `/healthz` endpoint in src/api/routers/health.py (per FR-003)
- [X] T007 Add Redis connection check to health endpoint
- [X] T008 Add browser pool availability check to health endpoint

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Docker Production Readiness (Priority: P1) 🎯 MVP

**Goal**: Service containerized with Dockerfile, docker-compose, and health endpoint

**Independent Test**: Build Docker image, run docker-compose, verify `/healthz` returns 200

### Tests for User Story 1 (TDD - Red Phase) ⚠️

- [X] T009 [P] [US1] Write failing E2E test for Docker deployment in tests/e2e/test_docker_deployment.py

### Implementation for User Story 1

- [X] T010 [US1] Verify Dockerfile builds successfully with Playwright browsers
- [X] T011 [US1] Verify docker-compose starts all services (api, worker, redis)
- [X] T012 [US1] Verify `/healthz` returns 200 OK within 200ms (per SC-002)

**Checkpoint**: US1 fully functional and testable independently

---

## Phase 4: User Story 2 - Anti-Bot Evasion for Yandex Maps (Priority: P1)

**Goal**: Stealth browser capabilities including User-Agent rotation and proxy integration

**Independent Test**: Send 30+ scrape requests to Yandex Maps, verify at least 80% return valid data

### Tests for User Story 2 (TDD - Red Phase) ⚠️

- [X] T013 [P] [US2] Write failing unit test for stealth browser in tests/unit/test_stealth_browser.py
- [X] T014 [P] [US2] Write failing contract test for proxy integration in tests/integration/test_proxy_integration.py

### Implementation for User Story 2

- [X] T015 [P] [US2] Implement stealth pool wrapper using patchright in src/infrastructure/browser/stealth_pool.py (per FR-004)
- [X] T016 [P] [US2] Implement User-Agent rotation pool in src/infrastructure/browser/user_agent_pool.py
- [X] T017 [P] [US2] Integrate proxy_provider into pool_manager.create_context (per FR-005)
- [X] T018 [US2] Add human-like interaction patterns (mouse jitter, typing delays) to stealth pool

**Checkpoint**: US2 fully functional and testable independently

---

## Phase 5: User Story 3 - Yandex Maps Business Data Extraction (Priority: P1)

**Goal**: Extract structured business data from Yandex Maps based on location parameters

**Independent Test**: Send request with (category, center, radius), verify response contains business cards

### Tests for User Story 3 (TDD - Red Phase) ⚠️

- [ ] T019 [P] [US3] Write failing contract test for Yandex Maps API in tests/contract/test_yandex_maps_api.py
- [ ] T020 [P] [US3] Write failing integration test for Yandex Maps extraction in tests/integration/test_yandex_extraction.py
- [ ] T021 [P] [US3] Write failing E2E test for full extraction flow in tests/e2e/test_yandex_maps_full_flow.py

### Implementation for User Story 3

- [ ] T022 [P] [US3] Create BusinessCard model in src/domain/models/business_card.py (per data-model.md)
- [ ] T023 [P] [US3] Create Yandex Maps extraction endpoint in src/api/routers/yandex_maps.py
- [ ] T024 [US3] Implement YandexMapsExtractAction in src/actions/yandex_maps.py (per FR-006)
- [ ] T025 [US3] Register Yandex Maps action in src/actions/registry.py
- [ ] T026 [US3] Handle scroll-based pagination for collecting all businesses
- [ ] T027 [US3] Apply stealth configuration to Yandex Maps requests

**Checkpoint**: US3 fully functional and testable independently

---

## Phase 6: User Story 4 - Site Content Enrichment (Priority: P2)

**Goal**: Extract clean text from company websites with optional crawling of about/services pages

**Independent Test**: Send company URL, verify response contains cleaned text ≤500 words

### Tests for User Story 4 (TDD - Red Phase) ⚠️

- [ ] T028 [P] [US4] Write failing unit test for content cleaner in tests/unit/test_content_cleaner.py
- [ ] T029 [P] [US4] Write failing contract test for enrichment API in tests/contract/test_enrichment_api.py
- [ ] T030 [P] [US4] Write failing E2E test for enrichment flow in tests/e2e/test_site_enrichment_flow.py

### Implementation for User Story 4

- [ ] T031 [P] [US4] Create EnrichedContent model in src/domain/models/enriched_content.py (per data-model.md)
- [ ] T032 [P] [US4] Create enrichment endpoint in src/api/routers/enrichment.py
- [ ] T033 [US4] Implement SiteEnrichAction in src/actions/site_enricher.py (per FR-007)
- [ ] T034 [US4] Implement content truncation to ~500 words (per FR-008)
- [ ] T035 [US4] Implement optional crawling of about/services pages
- [ ] T036 [US4] Implement HTML to plain text/markdown conversion

**Checkpoint**: US4 fully functional and testable independently

---

## Phase 7: User Story 5 - Per-Domain Rate Limiting (Priority: P2)

**Goal**: Enforce rate limits per domain (default 30/hour for *.yandex.*)

**Independent Test**: Send 35 requests to Yandex Maps within 1 hour, verify subsequent requests rejected

### Tests for User Story 5 (TDD - Red Phase) ⚠️

- [ ] T037 [P] [US5] Write failing unit test for rate limiter in tests/unit/test_rate_limiter.py

### Implementation for User Story 5

- [ ] T038 [P] [US5] Create RateLimitRule model in src/domain/models/rate_limit_rule.py (per data-model.md)
- [ ] T039 [P] [US5] Implement Redis-based token bucket rate limiter in src/infrastructure/rate_limiter/token_bucket.py
- [ ] T040 [US5] Create rate limiting middleware in src/api/middleware/rate_limit.py (per FR-009)
- [ ] T041 [US5] Configure default rate limits: 30/hour for `*.yandex.*`, 1000/hour for fallback
- [ ] T042 [US5] Return 429 with Retry-After header when limit exceeded (per FR-010)

**Checkpoint**: US5 fully functional and testable independently

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T043 [P] Run all tests and ensure they pass (Green phase complete)
- [ ] T044 [P] Verify compliance with Constitution Principles (I-IX)
- [ ] T045 Run quickstart.md validation
- [ ] T046 Update documentation in docs/ (include doc.md in new directories)
- [ ] T047 [P] Run ruff check and mypy type checking
- [ ] T048 Code cleanup and refactoring

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2)
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **US2 (P1)**: Can start after Foundational (Phase 2) - Uses stealth from US1 but can be tested independently
- **US3 (P1)**: Can start after Foundational (Phase 2) - Depends on US2 stealth capabilities
- **US4 (P2)**: Can start after Foundational (Phase 2) - Independent from US1-3
- **US5 (P2)**: Can start after Foundational (Phase 2) - Independent from US1-4

### Within Each User Story

- Tests (MUST be included per TDD requirements) MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- US2 and US3 can run in parallel (both P1, different components)
- US4 and US5 can run in parallel (both P2, different components)
- Models within a story marked [P] can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 + Foundational)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (Docker)
4. **STOP and VALIDATE**: Test US1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 → Test independently → Deploy/Demo (MVP!)
3. Add US2 → Test independently → Deploy/Demo
4. Add US3 → Test independently → Deploy/Demo
5. Add US4 → Test independently → Deploy/Demo
6. Add US5 → Test independently → Deploy/Demo

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 + US2
   - Developer B: US3 + US4
   - Developer C: US5
3. Stories complete and integrate independently

---

## Notes

- **[P]** tasks = different files, no dependencies
- **[Story]** label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- **TDD ENFORCED**: Tests MUST fail before implementation per Constitution Principle VI
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence