# Implementation Plan: Prepare Atomic-Scraper-Service for ML/CV Pipeline Integration

**Branch**: `010-scraper-mlcv-prep` | **Date**: 2026-05-01 | **Spec**: [spec.md](./spec.md)

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
**Scale/Scope**: 5 user stories, 10 functional requirements

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. Dual-Context Isolation**: This feature adds new actions (Yandex Maps, Site Enrichment) to Stateless API layer - respects split.
- [ ] **II. AI Orchestration**: [NEEDS CLARIFICATION: Does Yandex Maps extraction require AI/ML calls for parsing, or can it be done with CSS selectors?]
- [x] **III. Resource Lifecycle**: New actions are atomic (stateless) - no WebSocket sessions, so no timeout concerns.
- [x] **IV. Architecture**: New actions will be added to `src/actions/`, endpoints to `src/api/routers/`, infrastructure to `src/infrastructure/`.
- [x] **V. DSL Integration**: New capabilities will be exposed as discrete Actions in the registry.
- [x] **VI. Test-First**: TDD requirements section in spec mandates failing tests before implementation.
- [x] **VII. Backend-Only**: This is a backend-only feature - no UI components.
- [x] **VIII. Production Deployment**: This feature explicitly adds Dockerfile, docker-compose, and `/healthz` endpoint.
- [x] **IX. Anti-Bot Mitigation**: This feature explicitly adds stealth, proxy integration, and rate limiting.

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

## Phase 0: Research Required

The following unknowns must be resolved before Phase 1 design:

1. **AI/ML for Yandex Maps extraction**: Does extraction require LLM-based parsing or can be done with CSS selectors? (Constitution Check item II)
2. **Stealth library selection**: playwright-stealth vs patchright - which provides better evasion?
3. **Rate limiter implementation**: Redis-based token bucket vs in-memory with Redis persistence

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. All Constitution principles are either satisfied or have clear path to satisfaction.

---

*Plan created: 2026-05-01*
*Next step: Phase 0 - Research to resolve unknowns*