# Infrastructure: Browser (src/infrastructure/browser/)

## Files analyzed

- `src/infrastructure/browser/__init__.py`
- `src/infrastructure/browser/pool_manager.py`
- `src/infrastructure/browser/stealth_pool.py`
- `src/infrastructure/browser/user_agent_pool.py`
- `src/infrastructure/browser/proxy_provider.py`
- `src/infrastructure/browser/session_manager.py`

Cross-referenced: `STRUCTURE.md`, `AGENTS.md`, `README.md`, `Dockerfile`, `specs/010-scraper-mlcv-prep/spec.md` (FR-004, FR-005).

## Purpose & responsibilities

This slice owns all interaction with the headless browser layer (Playwright + Chromium). It is the only place in the codebase that calls `playwright.async_api.async_playwright()` and `browser.new_context(...)`. It implements:

- A single shared `Browser` process reused across every stateless request and every stateful session (the "global pool" pattern mentioned in `AGENTS.md` Resource Lifecycle).
- Per-request `BrowserContext` isolation so cookies/storage from one scrape never bleed into another.
- Anti-bot evasion required by **FR-004**: rotating User-Agent, fixed locale/timezone/viewport, `navigator.webdriver` removal, Chromium launch flags that hide automation fingerprints.
- Proxy injection required by **FR-005**: read `proxies.txt`, hand a random URL to the context.
- In-memory inactivity tracking for stateful sessions (heartbeat-style `last_active` map consumed by the cleanup worker in `src/infrastructure/queue/cleanup_worker.py`).

## Key classes / functions

### pool_manager / stealth_pool / user_agent_pool

**`BrowserPoolManager`** (`pool_manager.py`) — module-level singleton wrapper used by API startup (`api/main.py`) and by actions that need a browser.

- `get_browser(proxy=None, headless=True) -> Browser` — lazily starts Playwright + launches Chromium on first call; subsequent calls return the cached instance.
- `create_context(stealth=True, proxy=None, **kwargs) -> BrowserContext` — creates a fresh context per call. When `stealth=True` it delegates configuration to `StealthBrowserPool`. The proxy URL string is wrapped as `{"server": url}` because Playwright forbids changing the proxy after context creation (called out in `AGENTS.md`).
- `available_contexts() -> int` — counter used by `/healthz`.
- `close()` — closes the browser and stops Playwright; wired to FastAPI shutdown.

**`StealthBrowserPool`** (`stealth_pool.py`) — owns the stealth recipe.

- Launch args: `--disable-blink-features=AutomationControlled`, `--no-sandbox`, `--disable-setuid-sandbox`, `--disable-web-security`, `--disable-features=IsolateOrigins,site-per-process`.
- Context defaults: `viewport=1920x1080`, `locale="en-US"`, `timezone_id="America/New_York"`, `color_scheme="light"`, `permissions=["geolocation"]`.
- Navigator override via `context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")` injected on every new page.
- Picks a UA from `UserAgentPool` and passes it as `user_agent=...` to `new_context`.

**`UserAgentPool`** (`user_agent_pool.py`) — pure in-memory rotator.

- Hardcoded `USER_AGENTS` list (~10 entries covering Chrome 123/124, Firefox 124/125, Edge 124 on Windows/macOS/Linux).
- `get_random() -> str` is plain `random.choice` — no weighting, no exclusion of recently used UAs.
- Constructor accepts a custom list to override the default.

### proxy_provider

**`ProxyProvider`** (`proxy_provider.py`) — loads proxies from disk once at construction.

- Default path: `"proxies.txt"` (relative to CWD; the Docker bind mount lands it at `/app/proxies.txt`). Override via constructor argument.
- Format: one proxy per line, scheme `http://user:pass@host:port` (per `README.md` and `AGENTS.md`).
- Parsing is `strip()` + drop-empty; no regex/validation.
- `_load_proxies()` guards with `Path.is_file()` — explicitly NOT `exists()`, because Docker Desktop on Windows can materialise the mount target as a directory when the file is missing on the host (`AGENTS.md` Proxy wiring note).
- `get_proxy()` returns a random entry via `random.choice` on every call, or an empty/falsy value when the list is empty.
- **Missing**: no sticky-session-per-domain, no health-check, no failure-blacklist, no round-robin, no async refresh — the file is read once and never reloaded.

### session_manager

**`SessionManager`** (`session_manager.py`) — purely in-memory map for inactivity tracking. **Does not** create or own browser contexts (those live in the per-session Taskiq actor at `src/infrastructure/queue/session_actor.py`).

- State store: `Dict[str, Dict[str, Any]]` keyed by `session_id`, holding at minimum a `last_active` timestamp.
- `update_activity(session_id)` — heartbeat, called by the WebSocket handler / command router on each DSL command.
- `is_active(session_id) -> bool` — `now - last_active < settings.SESSION_INACTIVITY_TIMEOUT` (the 10-minute idle window described in `AGENTS.md`).
- `close_session(session_id)` — pops the entry; the actual browser context termination happens in the session actor.
- **No** Redis backing, **no** built-in background sweeper, **no** explicit STARTING/ACTIVE/IDLE/TERMINATED state machine in this file — those concerns are split between `cleanup_worker.py` (which polls `is_active`) and the session actor (which holds the real Playwright resources).

## Data flow within slice

```
FastAPI startup
  └─ BrowserPoolManager.get_browser()   # one Chromium for the whole process
         │
         ├─ stateless request (yandex_maps / enrichment / DSL action)
         │     └─ pool.create_context(stealth=True, proxy=ProxyProvider.get_proxy())
         │            └─ StealthBrowserPool applies UA + launch flags + init script
         │                   └─ context.new_page() → action runs → context.close()
         │
         └─ stateful session (POST /sessions)
               └─ Taskiq session_actor.create_session(session_id)
                       ├─ pool.create_context(stealth=True, proxy=...)   # held for the session
                       └─ SessionManager.update_activity(session_id)     # heartbeat
                              ▲
                              │ each WS/REST command refreshes timestamp
                              │
                       cleanup_worker (periodic) ──► SessionManager.is_active()
                                                          └─ if idle: session_actor terminates context
                                                                       SessionManager.close_session()

FastAPI shutdown
  └─ BrowserPoolManager.close()  # closes Browser + stops Playwright
```

Proxy is injected at `new_context` time and cannot be changed afterwards; this is why `ProxyProvider.get_proxy()` is called by the caller (action / actor) and the dict is forwarded into `create_context(proxy=...)`.

## Mermaid diagram(s)

```mermaid
flowchart TD
    A[FastAPI startup] --> B[BrowserPoolManager.get_browser]
    B --> C[Chromium process - shared singleton]
    D[stateless request] --> E[pool.create_context stealth=True]
    F[stateful session_actor] --> E
    G[ProxyProvider.get_proxy] --> E
    H[UserAgentPool.get_random] --> S[StealthBrowserPool config]
    S --> E
    E --> P[BrowserContext - per request/session]
    P --> Pg[Page navigator.webdriver=undefined]
    Z[FastAPI shutdown] --> X[pool.close]
    X --> C
```

```mermaid
stateDiagram-v2
    [*] --> STARTING: POST /sessions (actor spawning)
    STARTING --> ACTIVE: WS connected + first command
    ACTIVE --> ACTIVE: update_activity on each command
    ACTIVE --> IDLE: no command for > SESSION_INACTIVITY_TIMEOUT (~10 min)
    IDLE --> TERMINATED: cleanup_worker calls close_session
    ACTIVE --> TERMINATED: explicit DELETE /sessions/{id}
    TERMINATED --> [*]
```

## External dependencies

- **Playwright** (`playwright.async_api`) — Chromium driver, sole owner of the browser process. Installed in Docker via `uv run playwright install --with-deps chromium` (Dockerfile L9).
- **File system** — `./proxies.txt` (bind-mounted read-only into `/app/proxies.txt` per `docker-compose.yml` per `AGENTS.md`).
- **Python `random`** — UA and proxy selection.
- **`src/core/config.py`** — `SESSION_INACTIVITY_TIMEOUT`, headless mode, proxy file path overrides.
- **No direct Redis dependency** in this slice — Redis-backed session/task coordination lives in `src/infrastructure/queue/` (`session_actor.py`, `cleanup_worker.py`).

## Tests covering this slice

- `tests/unit/test_stealth_browser.py` — FR-004 stealth capabilities (mocked Playwright).
- `tests/integration/test_proxy_integration.py` — FR-005 proxy pool integration.
- `tests/integration/test_session_redis_failure.py` — touches session/cleanup contract under Redis failure.
- `tests/contract/test_sessions.py` — session lifecycle endpoints (uses SessionManager indirectly).

No dedicated unit test for `ProxyProvider` or `UserAgentPool` was located under `tests/`.

## Open questions / smells

1. **Two browser instances possible.** `BrowserPoolManager` keeps its own `Browser`, and `StealthBrowserPool` exposes its own `launch()`. If both are used, two Chromium processes spin up. Confirm only one is wired in `api/main.py`; otherwise consolidate.
2. **Proxy can be overridden at context level after being set at launch level.** `get_browser(proxy=...)` plus `create_context(proxy=...)` interact in a subtle way; the comment in `AGENTS.md` suggests only context-level is correct.
3. **No context pooling.** Despite the name `pool_manager`, every request gets a fresh `BrowserContext`. Under load this is memory-heavy. The class name overpromises.
4. **`ProxyProvider` lacks failure handling.** No blacklist on connection error, no rotation away from a dead IP, no reload from disk. The Yandex Maps note in `README.md` warns datacenter IPs are silently useless — there is no signal back to the operator.
5. **`UserAgentPool` is static and small (~10 entries).** Versions are pinned at Chrome 123/124, Firefox 124/125 — will look anomalous as those age out.
6. **`SessionManager` is in-memory only.** A second API replica would have its own session map; horizontal scaling of stateful sessions requires a Redis-backed implementation, which is hinted at in docs but not present here.
7. **No sticky-session per domain** in `ProxyProvider`. Yandex/Google flows that need IP continuity across multiple requests can land on different IPs and trip anti-bot.
8. **`proxies.txt` is read only at construction.** Hot-reload (e.g. for a rotating residential provider that emits a refreshed list) is not supported.
9. **Stealth fingerprint is shallow.** Only `navigator.webdriver` is patched; common detection vectors (`navigator.plugins`, `chrome.runtime`, WebGL vendor, permission query) are not addressed — Yandex/Cloudflare-grade detectors will still fire.
