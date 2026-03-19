# Research Findings: Smart Scraping LLM API

## 1. Omni-Parser Integration
**Decision**: Use **Omni-Parser V2.0** with a Set-of-Marks (SoM) approach.
**Rationale**: V2.0 (Florence-2 based) is significantly more accurate for UI grounding. Mapping elements to numeric IDs allows the LLM to provide robust "click ID 5" instructions which are translated back to relative coordinates (0.0-1.0) and then to screen coordinates.
**Alternatives Considered**: Direct coordinate prediction from VLM (less accurate); Playwright Accessibility Tree (faster but fails on canvas/complex UI).

## 2. Jina Reader V2 API
**Decision**: Use the `v1/read` endpoint with `X-Return-Format: markdown` and Pydantic-generated JSON schemas.
**Rationale**: Jina Reader V2 handles both the cleaning of HTML to Markdown and the structured extraction in a single step, reducing latency and cost compared to chaining local tools.
**Alternatives Considered**: Local HTML-to-Markdown libraries + raw LLM extraction.

## 3. Serper-compatible Search
**Decision**: Implement a transformation layer that maps internal scraper/search results to the **Serper.dev JSON structure**.
**Rationale**: Compatibility with Serper allows the system to be a drop-in replacement for existing agentic frameworks like LangChain.
**Alternatives Considered**: Exposing raw provider formats (requires client-side changes).

## 4. Redis Pub/Sub for WebSockets
**Decision**: Use bidirectional channels `cmd:{session_id}` and `res:{session_id}`.
**Rationale**: Bridges the gap between the persistent WebSocket connection in FastAPI and the isolated Actor process in Taskiq. Allows for a stateful command loop without blocking the API server.
**Alternatives Considered**: Shared database polling (high latency); HTTP long-polling.

## 5. Playwright Persistence
**Decision**: Global `Browser` instance initialized in Taskiq `startup` hook; `BrowserContext` per-request.
**Rationale**: Reusing the browser process eliminates the ~1-2s startup penalty for atomic scrapes (SC-001 requirement), while fresh contexts ensure data isolation and proxy flexibility.
**Alternatives Considered**: Launching browser per task (too slow); Persistent context (security risk).
