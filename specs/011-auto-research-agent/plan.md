# Implementation Plan: Auto-Research Agent

**Branch**: `011-auto-research-agent` | **Date**: 2026-05-11 | **Spec**: `specs/011-auto-research-agent/spec.md`
**Input**: Feature specification from `/specs/011-auto-research-agent/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add an autonomous research agent to the Atomic-Scraper-Service using LangGraph orchestration. The agent accepts natural-language research queries, conducts multi-step web research using existing scraping tools, and produces structured markdown reports with cited sources. Exposed via REST endpoints (`/api/v1/research/run`, `/api/v1/research/status/{task_id}`) with async Taskiq processing. Supports three research modes (speed, balanced, quality) with configurable depth/time tradeoffs and guaranteed completion via loop-safety constraints (token budget threshold, iteration cap, deadline, stall detection).

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, Taskiq, Playwright, Redis, Pydantic v2, LangGraph, LangChain  
**Storage**: Redis (task queues), in-memory with 24-hour retention (per spec)  
**Testing**: pytest  
**Target Platform**: Linux server (Docker container)  
**Project Type**: web-service (REST API)  
**Performance Goals**: Task ID response <1s (SC-001), speed <2min, balanced <5min, quality <20min (SC-002/003/004)  
**Constraints**: Max 5 concurrent tasks per API key (FR-020), 85% token budget triggers beast-mode (FR-006)  
**Scale/Scope**: Single service, 10s-100s of concurrent users expected based on rate limits

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. Dual-Context Isolation**: Research agent runs as a stateless Taskiq worker, not a stateful session
- [x] **II. AI Orchestration**: Uses LLMFacade for query classification, fact extraction, and answer synthesis
- [x] **III. Resource Lifecycle**: Deadline enforcement and iteration caps ensure bounded execution; no long-running state
- [x] **IV. Architecture**: New research endpoints in `src/api/routers/research.py`, domain models in `src/domain/models/research.py`, LangGraph in `src/actions/research/`
- [x] **V. DSL Integration**: Research agent is exposed as a discrete Action (ResearchRunAction) registered in action registry
- [x] **VI. Test-First**: TDD contracts defined in spec.md - test files must be created RED before implementation
- [x] **VII. Backend-Only**: Pure REST API, no frontend components
- [x] **VIII. Production Deployment**: Uses existing Dockerfile, docker-compose, and `/healthz` endpoint
- [x] **IX. Anti-Bot Mitigation**: Reuses existing stealth browser, proxy rotation, and rate limiting from stateless pool
- [x] **X. Autonomous Research Agent**: LangGraph orchestration with loop safety constraints and tool reuse per Principle X

## Project Structure

### Documentation (this feature)

```text
specs/011-auto-research-agent/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

The project uses the existing single-project structure:

```text
src/
├── api/
│   ├── routers/
│   │   ├── research.py      # NEW: /api/v1/research endpoints
│   │   ├── stateless.py
│   │   ├── sessions.py
│   │   └── ...
│   ├── middleware/
│   └── main.py
├── domain/
│   ├── models/
│   │   ├── research.py      # NEW: request/response models
│   │   ├── dsl.py
│   │   └── ...
│   └── research/
│       ├── __init__.py      # NEW: LangGraph state graph definition
│       ├── nodes.py         # NEW: graph nodes
│       ├── state.py         # NEW: graph state
│       ├── tools.py         # NEW: LangChain tool wrappers
│       ├── modes.py         # NEW: mode presets
│       └── prompts.py       # NEW: per-node prompts
├── infrastructure/
│   ├── external_api/
│   │   └── facade.py        # LLMFacade for AI calls
├── actions/
│   ├── research.py          # NEW: ResearchRunAction
│   └── ...
└── core/
    └── config.py

tests/
├── contract/
│   └── test_research_endpoint.py  # NEW: API contract tests
├── integration/
│   └── test_research_graph.py     # NEW: graph integration tests
└── unit/
    └── research/
        ├── test_modes.py           # NEW: mode preset tests
        ├── test_nodes.py           # NEW: node transformation tests
        └── test_state_transitions.py  # NEW: router truth table tests
```

**Structure Decision**: Uses existing `src/` and `tests/` directories following established patterns. New files follow naming conventions of existing codebase (snake_case modules, PascalCase classes).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. All Constitution principles satisfied:
- I. Dual-Context Isolation: Research agent runs as stateless Taskiq worker
- II. AI Orchestration: Uses LLMFacade for all AI calls
- III. Resource Lifecycle: Deadline and iteration caps ensure bounded execution
- IV. Architecture: Follows API/Domain/Infrastructure/Actions layers
- V. DSL Integration: Exposed as ResearchRunAction in action registry
- VI. Test-First: TDD contracts defined, test files to be created RED before implementation
- VII. Backend-Only: No frontend components
- VIII. Production Deployment: Uses existing Dockerfile/docker-compose/healthz
- IX. Anti-Bot Mitigation: Reuses existing stealth, proxy, rate limiting
- X. Autonomous Research Agent: LangGraph with loop safety, tool reuse
