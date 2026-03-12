# System Structure & Logic

## 1. Execution Architecture

The system is split into two distinct execution circuits to balance performance and flexibility.

### Circuit A: Stateless Pool
- **Purpose:** High-throughput, low-latency atomic tasks (one-off scrapes, search queries).
- **Worker Management:** 
    - Taskiq workers use a **Global Playwright Instance** (Singleton).
    - Upon each task, a fresh `BrowserContext` is created and closed.
    - This avoids the overhead of launching a full browser process for every request.
- **Proxying:** Uses a server-side round-robin pool defined in `SCRAPER_SERPER_PROXIES`.

### Circuit B: Stateful Actors
- **Purpose:** Complex, multi-step interactive sessions requiring memory and AI orchestration.
- **Worker Management:**
    - Each session triggers a dedicated Taskiq task (the **Actor**).
    - The Actor owns a **Private Playwright Instance**.
    - It maintains state (cookies, local storage, current page) for the session duration.
- **Lifecycle & Safety:**
    - **Inactivity Timeout:** Force-kills the browser if no commands are received for N seconds.
    - **Max Duration:** Hard limit on session lifetime (e.g., 1 hour).
    - **Cleanup:** Ensures no dangling browser processes or memory leaks.

---

## 2. Component Logic

### Action Registry (DSL)
Actions are implemented as discrete classes inheriting from `BaseAction`. They register themselves with a string ID (e.g., `omni_click`). This allows the system to be easily extended with new commands without modifying the core actor loop.

### LLM Facade
A unified interface for AI services:
- **OpenAI:** For structured output and logical decision-making.
- **Jina Reader V2:** For HTML-to-Markdown conversion and schema-based extraction.
- **Omni-Parser:** For visual element detection on screenshots (coordinates).

---

## 3. Data Flow Diagrams

### Sequence: Stateful Session Command
```mermaid
sequenceDiagram
    participant C as Client (WS)
    participant API as FastAPI
    participant R as Redis (Pub/Sub)
    participant A as Actor (Worker)
    participant PW as Playwright

    C->>API: {"action": "goto", "params": {"url": "..."}}
    API->>R: Publish to cmd:{session_id}
    R->>A: Receive command
    A->>PW: page.goto(...)
    PW-->>A: Navigation Success
    A->>R: Publish to res:{session_id}
    R-->>API: Receive result
    API->>C: {"status": "ok", "action": "goto", ...}
```

### Flow: Lifecycle & Timeout
```mermaid
graph TD
    Start(POST /sessions) --> Enqueue[Taskiq: run_stateful_session]
    Enqueue --> Init[Launch Browser + Page]
    Init --> Loop{Wait for Command}
    Loop -- Command Received --> Execute[Execute Action]
    Execute --> Loop
    Loop -- Idle Timeout --> Close[Force Close Browser]
    Loop -- Exit Command --> Close
    Close --> End(Terminate Worker)
```

---

## 4. Entry Points & Orchestration

### run.py
To simplify local development, a `run.py` script is provided at the root. It acts as a process orchestrator that:
1. **Checks Infrastructure:** Verifies Redis is running and reachable.
2. **Environment Setup:** Ensures `.env` exists (auto-creates from `.env.example` if missing).
3. **Parallel Execution:** Spawns two subprocesses:
    - **API Process:** `uvicorn scraper_os.api.main:app`
    - **Worker Process:** `taskiq worker scraper_os.infrastructure.queue.broker:broker`
4. **Lifecycle Management:** Handles `Ctrl+C` to gracefully terminate both the API and the Worker, preventing orphaned browser processes.

---

## 5. Configuration

The system uses **Pydantic Settings** for centralized configuration management. Environment variables are prefixed with `SCRAPER_`.

### Setup
A `.env.example` file is provided in the root directory. Copy it to `.env` to customize your local environment:
- `SCRAPER_REDIS_URL`: Connection string for Taskiq broker and Pub/Sub.
- `SCRAPER_SERPER_PROXIES`: A JSON list of proxy URLs for the stateless pool.
- `SCRAPER_OPENAI_API_KEY`: API key for decision-making and extraction logic.
- `SCRAPER_SESSION_TIMEOUT_SECONDS`: Idle timeout for stateful actors (default: 300s).

Refer to `scraper_os/core/config.py` for all available settings.

