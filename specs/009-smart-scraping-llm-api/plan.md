# Implementation Plan: Implement Smart Scraping API with LLM orchestration

**Branch**: `009-smart-scraping-llm-api` | **Date**: 2026-03-16 | **Spec**: [spec.md](spec.md)

## Summary

This feature implements a dual-context web scraping service with enhanced AI capabilities:
1.  **Stateless Pool**: High-throughput atomic scraping, Google search, direct Omni-Parser image analysis, and Jina extraction endpoints.
2.  **Stateful Actors**: Isolated interactive sessions with a rich DSL supporting:
    - Selector-based extraction and filling.
    - Full-page snapshots and coordinate-based interactions (click/fill).
    - AI-orchestrated navigation (Omni-click, Jina-extract).
Utilizes a centralized `LLMFacade` for modular AI provider management.

## Technical Context

**Language/Version**: Python 3.11+ (based on asyncio requirements)
**Primary Dependencies**: FastAPI, Taskiq (with Redis broker), Playwright, Redis, Pydantic v2, OpenAI, HTTPX
**Storage**: Redis (Task queue and Pub/Sub coordination)
**Testing**: pytest, pytest-asyncio
**Target Platform**: Linux server (Docker-compatible)
**Project Type**: web-service (Backend-only)
**Performance Goals**: Atomic scrapes < 2s (excluding site latency); 20+ concurrent sessions on 8GB RAM.
**Constraints**: Fail-fast on blocking; 10-minute inactivity timeout for stateful sessions; Static API Key auth.
**Scale/Scope**: Multi-node horizontal scaling via Redis Pub/Sub.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. Dual-Context Isolation**: Does this feature respect the Stateless/Stateful split? (Yes, explicitly defined in architecture)
- [x] **II. AI Orchestration**: Does it use the LLMFacade for AI calls? (Yes, planned in `infrastructure/llm/facade.py`)
- [x] **III. Resource Lifecycle**: Are timeouts handled if this is a stateful feature? (Yes, 10-minute inactivity timeout implemented in Actor)
- [x] **IV. Architecture**: Does the code fit into the API/Domain/Infrastructure/Actions layers? (Yes, following Clean Architecture)
- [x] **V. DSL Integration**: Is the new capability exposed as a discrete Action? (Yes, CommandPayload and Action Registry planned)
- [x] **VI. Test-First**: Have failing tests been drafted/planned before implementation? (Yes, Sprint 4 includes registry tests)
- [x] **VII. Infrastructure**: Does this require Redis or other services managed via `docker-compose`? (Yes, Redis is required)
- [x] **VIII. Backend-Only**: Confirm no frontend/UI components are being introduced. (Yes, REST and WS only)

## Project Structure

### Documentation (this feature)

```text
specs/009-smart-scraping-llm-api/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/
├── api/                           # [Presentation] REST & WebSockets
│   ├── routers/                   # stateless.py, sessions.py
│   └── websockets/                # manager.py
├── domain/                        # [Domain] Models & DSL
│   ├── models/                    # requests.py, dsl.py
│   └── registry/                  # Action Registry
├── infrastructure/                # [Infrastructure] External logic
│   ├── browser/                   # pool_manager.py, session_manager.py
│   ├── external_api/              # facade.py, clients/ (LLM, Jina, etc.)
│   └── queue/                     # broker.py, workers.py
├── actions/                       # [Actions] DSL Implementations
│   ├── base.py
│   ├── navigation.py
│   └── extraction.py
└── core/                          # [Cross-cutting] Config, logging
    └── config.py

tests/
├── contract/                      # API contract verification
├── integration/                   # Taskiq/Playwright integration
└── unit/                          # Business logic & Actions
```

**Structure Decision**: Clean Architecture with a single Python project structure. Layers are clearly separated into `api`, `domain`, `infrastructure`, and `actions` per the Constitution.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |

