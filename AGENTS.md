# Agent Coordination: Atomic Scraper Service

This document defines the agentic roles and coordination strategies for the Smart Scraping LLM API project.

## Agent Personas

### 1. Scraper Orchestrator (Stateless)
- **Responsibility**: Manages high-throughput atomic scraping tasks.
- **Capabilities**: Selects optimal proxies, handles retries, and transforms results into Serper-compatible formats.
- **Integration**: Uses `ScrapeClient` and `SearchClient`.

### 2. Browser Session Actor (Stateful)
- **Responsibility**: Executes interactive DSL commands within isolated browser contexts.
- **Capabilities**: Navigation (goto, scroll), Interaction (click, fill), and Extraction (screenshot, DOM).
- **Coordination**: Communicates via Redis Pub/Sub channels (`cmd:{id}`, `res:{id}`).

### 3. AI Grounding Specialist
- **Responsibility**: Interprets UI elements and provides grounding for autonomous interactions.
- **Capabilities**: Utilizes Omni-Parser for coordinate-based click prediction and Jina for structured data extraction.
- **Provider**: Integrated via `LLMFacade` and specialized infrastructure clients.

## Coordination Protocol

- **State Transitions**: Sessions transition from `STARTING` to `ACTIVE` upon WebSocket connection.
- **Inactivity Monitoring**: A background cleanup worker monitors `last_active` timestamps and terminates idle sessions after 10 minutes.
- **Command Loop**:
    1. Client sends DSL Command via WebSocket.
    2. API Gateway publishes command to Redis.
    3. Session Actor (Taskiq) consumes command, executes in Playwright, and publishes result back to Redis.
    4. API Gateway forwards result to Client.

## Resource Lifecycle
- **Global Pool**: A shared `Browser` instance is reused to minimize startup latency.
- **Isolated Contexts**: Each session (stateless or stateful) gets a unique `BrowserContext` for data isolation.
- **Cleanup**: Automatic disposal of contexts on task completion or timeout.

# Atomic-Scraper-Service Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-16

## Active Technologies

- Python 3.11+ (based on asyncio requirements) + FastAPI, Taskiq (with Redis broker), Playwright, Redis, Pydantic v2, OpenAI, HTTPX (009-smart-scraping-llm-api)

## Project Structure

```text
backend/
frontend/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11+ (based on asyncio requirements): Follow standard conventions

## Recent Changes

- 009-smart-scraping-llm-api: Added Python 3.11+ (based on asyncio requirements) + FastAPI, Taskiq (with Redis broker), Playwright, Redis, Pydantic v2, OpenAI, HTTPX

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
