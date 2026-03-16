# Task List: Smart Scraping API Implementation

## Phase 1: Test Infrastructure & Contracts (Red) [TODO]
- [ ] **T-101**: Setup `pytest-asyncio` and base test configuration in `tests/conftest.py`.
- [ ] **T-102**: Write failing contract tests for `/scraper` and `/serper` endpoints.
- [ ] **T-103**: Write failing contract tests for `/omni-parse` and `/jina-extract` endpoints.
- [ ] **T-104**: Define failing WebSocket connection and handshake tests in `tests/contract/test_ws_lifecycle.py`.

## Phase 2: Domain & Models [TODO]
- [ ] **T-201**: Implement Pydantic models in `src/domain/models/` (Requests, DSL, Config).
- [ ] **T-202**: Implement `ActionRegistry` and `BaseAction` in `src/domain/registry/`.
- [ ] **T-203**: Write unit tests for model validation and registry lookups.

## Phase 3: Infrastructure (External APIs & Browser) [TODO]
- [ ] **T-301**: Implement `ExternalApiFacade` and Jina/OpenAI clients with mock-based tests.
- [ ] **T-302**: Setup Taskiq broker and `BrowserPoolManager` for stateless tasks.
- [ ] **T-303**: Implement `SessionBrowserManager` with isolated context logic.

## Phase 4: DSL Actions Implementation [TODO]
- [ ] **T-401**: Implement `NavigationActions` (Goto, Click, Scroll) with unit tests.
- [ ] **T-402**: Implement `ExtractionActions` (Selector-based, Jina, Full-page screenshot).
- [ ] **T-403**: Implement coordinate-based `InteractionActions` (Click/Fill via full-page coords).

## Phase 5: API & Orchestration (Green) [TODO]
- [ ] **T-501**: Implement FastAPI routers for stateless endpoints to pass contract tests.
- [ ] **T-502**: Implement WebSocket Manager and Redis Pub/Sub routing.
- [ ] **T-503**: Implement Stateful Actor lifecycle with 10-minute inactivity timeout.
- [ ] **T-504**: Verify E2E flows: WS command -> Actor -> Browser -> Result.
