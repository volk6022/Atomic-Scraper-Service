# Research: Auto-Research Agent

**Branch**: `011-auto-research-agent` | **Date**: 2026-05-11

## Summary

This document captures technical decisions made during planning for the Auto-Research Agent feature.

## Decisions Made

### LangGraph vs Custom Loop

**Decision**: Use LangGraph for orchestration
**Rationale**: LangGraph provides built-in checkpointing, node routing, and state management that aligns with Constitution Principle X. The spec requires loop safety (token budget, iteration cap, deadline, stall detection) - LangGraph's Pregel architecture handles this naturally with node-level control flow.
**Alternatives considered**: Custom while-loop with state machine, LangChain LangChain Agent (less control over graph structure)

### Research Mode Implementation

**Decision**: Mode presets defined as dataclasses with configurable defaults
**Rationale**: Simple, testable, allows user overrides while providing sensible defaults per Constitution Principle VI (testable). Modes: quick (2 iters, 4K tokens), balanced (5 iters, 8K tokens), deep (10 iters, 16K tokens).
**Alternatives considered**: Enum-based mode selection with hardcoded values (harder to test)

### Tool Reuse Strategy

**Decision**: Reuse existing stateless scraper for web search, SiteEnrichAction for URL scraping, LLMFacade for fact extraction
**Rationale**: Per FR-004/FR-005/FR-006 - reuse existing capabilities without external APIs. Aligns with Constitution Principle X(d): "reuse existing scraping capabilities as LangChain tools".
**Alternatives considered**: New dedicated tools (violates reuse principle)

### Async Endpoint Design

**Decision**: POST returns 202 with task_id, GET polls for status/report
**Rationale**: Per FR-002 - return task ID within 1 second, process asynchronously. Uses existing Taskiq infrastructure.
**Alternatives considered**: WebSocket streaming (adds complexity, spec supports optional SSE for progress only)

### Storage for Research Results

**Decision**: In-memory with 24-hour TTL (per spec assumption)
**Rationale**: Simple, leverages Redis TTL. No persistent storage required per spec assumptions.
**Alternatives considered**: PostgreSQL (overkill for 24-hour retention)

### Loop Safety Implementation

**Decision**: State machine with beast_mode flag triggered at 85% token budget threshold
**Rationale**: Per FR-006 and Constitution Principle X(b) - hard loop-safety constraints. Beast-mode routes directly to answer node, skipping further search/scrape.
**Alternatives considered**: Exception-based termination (less graceful), external monitor process (adds complexity)

### Rate Limiting for Concurrent Tasks

**Decision**: Per-API-key counter in Redis, max 5 concurrent tasks
**Rationale**: Per FR-020 - 429 if exceeded. Uses existing Redis infrastructure.
**Alternatives considered**: Per-user (API key is the auth mechanism per existing pattern)

## Technical Dependencies

- LangGraph: `langgraph` package for graph orchestration
- LangChain: `langchain` for tool wrappers
- Taskiq: existing async task queue (already in project)
- LLMFacade: existing AI orchestration (already in project)
- Redis: existing task storage (already in project)

## Unknowns Resolved

No unknowns remain. All technical context items resolved during planning phase.

## Phase 1 Artifacts Required

- `data-model.md`: Entity definitions for ResearchRequest, ResearchTask, ResearchReport, Citation, Fact, ResearchStats
- `contracts/`: API contract for `/api/v1/research/run` and `/api/v1/research/status/{task_id}`
- `quickstart.md`: Developer guide for testing the feature
- Update agent context via `.specify/scripts/bash/update-agent-context.sh opencode`