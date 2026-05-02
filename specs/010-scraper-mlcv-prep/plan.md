# Implementation Plan: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Branch**: `010-scraper-mlcv-prep` | **Date**: 2026-05-01 | **Spec**: [spec.md](./spec.md)

**Status**: Complete (2026-05-01) | **Tasks**: 48/48 complete

**Input**: Feature specification from `/specs/010-scraper-mlcv-prep/spec.md`

## Summary

This feature prepares the Atomic-Scraper-Service for integration into the auto-monitor-ml-cv pipeline by adding: (1) Docker production readiness with Dockerfile, docker-compose, and health endpoint; (2) anti-bot evasion capabilities including stealth browser, User-Agent rotation, and proxy integration; (3) Yandex Maps extraction action for business data collection; (4) site enrichment for company content extraction; (5) per-domain rate limiting to respect target site Terms of Service.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Playwright, Taskiq, Redis, Pydantic v2, OpenAI  
**Storage**: Redis (for rate limiting, session state)  
**Testing**: pytest, pytest-asyncio, Playwright  
**Target Platform**: Linux server (containerized)  
**Project Type**: Backend web-service (REST API + MCP)  
**Performance Goals**: 10 concurrent requests, 30 req/h per domain limit, health endpoint <200ms  
**Constraints**: Must maintain Stateless/Stateful isolation, TDD required, no frontend  
**Scale/Scope**: 5 user stories, 10 functional requirements, 48 tasks

## Completion Summary

| Phase | Tasks | Status |
|-------|-------|--------|
| Phase 1: Setup (Docker) | T001-T003 | Complete |
| Phase 2: Foundational | T004-T008 | Complete |
| Phase 3: US1 - Docker Production | T009-T012 | Complete |
| Phase 4: US2 - Anti-Bot Evasion | T013-T018 | Complete |
| Phase 5: US3 - Yandex Maps Extraction | T019-T027 | Complete |
| Phase 6: US4 - Site Enrichment | T028-T036 | Complete |
| Phase 7: US5 - Rate Limiting | T037-T042 | Complete |
| Phase 8: Polish | T043-T048 | Complete |

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. Dual-Context Isolation**: This feature adds new actions (Yandex Maps, Site Enrichment) to Stateless API layer - respects split.
- [x] **II. AI Orchestration**: Yandex Maps extraction uses CSS selectors (no LLM needed for business card parsing).
- [x] **III. Resource Lifecycle**: New actions are atomic (stateless) - no WebSocket sessions, so no timeout concerns.
- [x] **IV. Architecture**: New actions will be added to `src/actions/`, endpoints to `src/api/routers/`, infrastructure to `src/infrastructure/`.
- [x] **V. DSL Integration**: New capabilities will be exposed as discrete Actions in the registry.
- [x] **VI. Test-First**: TDD requirements section in spec mandates failing tests before implementation.
- [x] **VII. Backend-Only**: This is a backend-only feature - no UI components.
- [x] **VIII. Production Deployment**: This feature explicitly adds Dockerfile, docker-compose, and `/healthz` endpoint.
- [x] **IX. Anti-Bot Mitigation**: This feature explicitly adds stealth, proxy integration, and rate limiting.

> **Resolution**: Research confirmed patchright (not playwright-stealth) is recommended for Yandex Maps protocol-level stealth. CSS selectors sufficient - no LLM required.

## Project Structure

### Documentation (this feature)

```text
specs/010-scraper-mlcv-prep/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── rest.md
│   └── dsl.md
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

The existing project structure will be extended:

```text
src/
├── api/
│   ├── main.py           # FastAPI app
│   └── routers/
│       ├── stateless.py  # Existing atomic scraping
│       └── health.py    # NEW: /healthz endpoint
├── infrastructure/
│   ├── browser/
│   │   ├── pool_manager.py    # Existing
│   │   ├── stealth_pool.py    # NEW: Stealth browser wrapper
│   │   └── proxy_provider.py  # Existing - integrate into pool
│   └── external_api/
│       └── [existing]
├── actions/
│   ├── registry.py            # Existing
│   ├── yandex_maps.py         # NEW: Yandex Maps extraction
│   └── site_enricher.py       # NEW: Site content enrichment
└── domain/
    └── [existing]

tests/
├── unit/                 # NEW tests per TDD requirements
├── contract/            # NEW contract tests
├── integration/         # NEW integration tests
└── e2e/                 # NEW E2E tests
```

**Structure Decision**: Single project structure at repository root. Existing structure at `src/api/`, `src/infrastructure/`, `src/actions/`, `src/domain/` will be extended with new modules. Tests will follow existing `tests/{unit,contract,integration,e2e}/` pattern.

## Phase 0: Research Results

The following unknowns were resolved before Phase 1 design:

1. **AI/ML for Yandex Maps extraction**: CSS selectors sufficient - no LLM required for parsing business cards.
2. **Stealth library selection**: patchright recommended over playwright-stealth for Yandex Maps protocol-level evasion.
3. **Rate limiter implementation**: Redis-based token bucket implemented.
4. **Playwright proxy format**: Uses object format `{"server": "url"}` not string.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. All Constitution principles are either satisfied or have clear path to satisfaction.

---

*Plan created: 2026-05-01*
*Feature complete: 2026-05-01*
*Next step: Integration with auto-monitor-ml-cv pipeline*

---

## Deliverables

### API Endpoints
- `GET /healthz` - Health check with Redis and browser pool status
- `POST /api/v1/yandex-maps/extract` - Extract business data from Yandex Maps
- `POST /api/v1/enrich` - Extract clean text from company websites

### Key Implementation Files
- `src/api/routers/yandex_maps.py` - Yandex Maps endpoint
- `src/api/routers/enrichment.py` - Site enrichment endpoint
- `src/api/middleware/rate_limit.py` - Rate limiting middleware
- `src/infrastructure/browser/stealth_pool.py` - Stealth browser wrapper
- `src/infrastructure/rate_limiter/token_bucket.py` - Redis token bucket
- `src/actions/yandex_maps.py` - Yandex Maps extraction action
- `src/actions/site_enricher.py` - Site enrichment action

### Tests Created
- `tests/unit/test_content_cleaner.py` (8 tests)
- `tests/unit/test_rate_limiter.py` (9 tests)
- `tests/contract/test_enrichment_api.py` (8 tests)
- `tests/e2e/test_site_enrichment_flow.py` (6 tests)