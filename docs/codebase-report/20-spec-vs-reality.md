# Spec vs Reality Reconcile

## Executive summary

Cross-checking specs 009/010/011/013, the constitution v1.5.0, and manifests (README/AGENTS/STRUCTURE/web_interactions) against reports 01–19 yields **9 CRITICAL, 16 MAJOR, 17 MINOR, 6 INFO** discrepancies. Headline problems:

1. **Per-domain rate limiting (FR-009, constitution IX) does not work as designed.** Middleware keys on the inbound `Host` header, so `*.yandex.*` never matches the target URL inside request bodies — quota is effectively shared on `localhost:8000`.
2. **Constitution X(b) loop-safety is partially inert.** `tokens_used` is never incremented, so the 85%-token-budget beast-mode trigger is dead code; only deadline and stall actually flip `beast_mode`. 3 of 4 hard constraints enforced.
3. **Three layers of REST contract drift around scraper/enrich/yandex/research/jina endpoints** — spec 009/010 paths and field names diverge from code in nearly every endpoint; spec 011 says 401 on missing auth, code returns 403; session inactivity timeout in compose (1800 s) contradicts FR-007 (600 s); MCP server hard-codes `BASE_URL` and `API_KEY` and still advertises `/jina-extract`, which no longer exists.

Plus widespread doc drift: STRUCTURE.md/AGENTS.md reference files that do not exist (`base.py`, `ai_actions.py`, `jina_client.py`, `omni_client.py`, `business_card.py`, `middleware/auth.py`); AGENTS.md test-count table is stale (17 vs ~76 unit; 99 vs ~108 total).

## Method

**Inputs compared:**
- Reports 01–19 in `docs/codebase-report/` (single source of truth for code reality — no `.py` files were read directly).
- Specs: `specs/009-smart-scraping-llm-api/{spec,data-model,contracts/{rest,websocket}}.md`, `specs/010-scraper-mlcv-prep/{spec,data-model,contracts/{rest,dsl}}.md`, `specs/011-auto-research-agent/{spec,data-model,contracts/api}.md`, `specs/012-fixing-existing-implementation/spec.md`, `specs/013-fix-impl/{spec,data-model}.md` (013 contracts dir is empty).
- Constitution: `.specify/memory/constitution.md` v1.5.0.
- Manifests: `README.md` (referenced via reports), `STRUCTURE.md`, `AGENTS.md`, `web_interactions.md`.

**Not inspected:** Python source (per task rules) and `*_experiment/`, `.venv/`, `.opencode/`, `node_modules/`, `.pytest_cache/`. All claims about code behavior are sourced from the slice reports 01–19 and cited by report number.

## Discrepancies

### CRITICAL

#### C-01: Rate-limit middleware keys on inbound `Host`, not target domain
**Source spec**: `specs/010/spec.md` FR-009, SC-005; constitution IX(c). Quota must apply to `*.yandex.*` after 30 req/h.
**Reality (report 03)**: `RateLimitMiddleware._get_domain_from_request` strips the inbound `Host` header. Real client traffic always carries `localhost:8000` / LB hostname. The body field (e.g. `EnrichRequest.url`, `YandexMapsExtractRequest.query`) that decides the actual target is never consulted. Routers do not call the bucket directly either.
**Impact**: FR-009 / SC-005 unenforceable in production; all clients sharing the same API host compete for a single bucket; `*.yandex.*` pattern essentially dead.
**Recommendation**: Either parse target URL out of payload in middleware (per-route adapter) or invoke `TokenBucket.consume(domain)` explicitly from `yandex_maps.py` / `enrichment.py` / `site_enricher.py` before issuing the outbound Playwright request.

#### C-02: `tokens_used` is never incremented → constitution X(b) only 3/4 enforced
**Source spec**: constitution X(b), spec 011 FR-008, US3 acceptance scenarios.
**Reality (reports 13, 14)**: `ResearchState.tokens_used` initialised to 0 in `mode_to_initial_state`; no node, no LLM client wrapper, no `usage.total_tokens` aggregation increments it. Beast-mode by 85% token budget is dead branch in `reflect_node`. Wall-clock deadline + `stall_counter` work.
**Impact**: A user submitting `max_tokens=1000` will never see beast-mode for budget reasons; long quality-mode runs (`token_budget=1_000_000`) can spend through huge LLM quotas without the safety brake the constitution mandates.
**Recommendation**: Capture `response.usage.total_tokens` inside `OpenAICompatibleClient.generate`, add `tokens_used += ...` in `extract_facts_node` / `answer_node` / `plan_node`, and re-enable the 85% threshold check.

#### C-03: Session inactivity timeout: spec 600 s vs deployed 1800 s
**Source spec**: `specs/009/spec.md` FR-007 ("10 minutes of inactivity"); constitution III; AGENTS.md repeats "10 minutes".
**Reality (reports 09, 11)**: `docker-compose.override.yml` sets `SESSION_INACTIVITY_TIMEOUT=1800` (30 min). `session_actor` loop compares `last_active` against this env value, not 600.
**Impact**: Resources held 3× longer than the constitution allows; SC-002 ("100% idle sessions cleaned within 60 s of timeout expiry") no longer matches user expectations.
**Recommendation**: Pick one. Either patch compose to 600 + AGENTS.md unchanged, or amend FR-007/constitution + AGENTS.md to 1800.

#### C-04: `/serper` is NOT Playwright→Google, it is SearXNG
**Source spec**: `specs/013-fix-impl/spec.md` FR-001, FR-002 ("performs real Google searches using headless Playwright browser ... proxy rotation"); spec 009 FR-Q4 ("Google Only (via Serper-compatible interface)").
**Reality (reports 01, 10)**: `POST /serper` calls `search_client` singleton which is just a re-export of `SearXngSearchClient`. There is no Playwright Google scraper any more (explicitly noted "the old Playwright-based scraper has been removed" in report 10). Proxy rotation lives inside the SearXNG container (`infra/searxng/searxng/settings.yml`), not in any Python proxy provider.
**Impact**: FR-001/FR-002 of spec 013 are unmet as written. Failure modes (Google blocking) are opaque to Python (only "httpx timeout").
**Recommendation**: Either update spec 013 to reflect the SearXNG pivot (correct since 012/013 era) or re-add a Playwright fallback (`google_playwright_client.py`) chained behind the SearXNG client.

#### C-05: `/jina-extract` no longer exists but is still in specs, MCP server, and docs
**Source spec**: spec 009 contract `rest.md` §5 (`POST /jina-extract`); STRUCTURE.md `jina_client.py`; AGENTS.md "AI Grounding Specialist" persona; web_interactions.md `extract_jina` DSL.
**Reality (reports 01, 10, 19)**: Real endpoint is `POST /html-to-md` (`HtmlToMdRequest`). `jina_client.py` and `omni_client.py` files do not exist. MCP server still advertises `jina_extract` tool that targets `POST /jina-extract` → 404 at runtime.
**Impact**: MCP tool `jina_extract` and `session_extract_jina` are broken. External clients/agents following spec 009 contract will 404.
**Recommendation**: Per spec 013 FR-003 the rename is intentional. Update spec 009/contracts/rest.md, web_interactions.md §4, STRUCTURE.md, AGENTS.md, and `src/mcp_server.py` tool names (`jina_extract` → `html_to_md`) and URL.

#### C-06: WebSocket protocol field-name mismatch (`action` vs `type`) is unvalidated
**Source spec**: `specs/009/contracts/websocket.md` requires `{"action": "...", "params": {...}}` client→server and `{"status", "action", "data"}` server→client. web_interactions.md uses `{"type": "...", "params": {...}}` for `/sessions/{id}/command`.
**Reality (report 02)**: `websocket_endpoint` does `json.loads(data)` and forwards raw bytes; no Pydantic validation, accepts either form silently. Result frames are raw Redis bytes — no `{status, action, data}` envelope guaranteed. Also: no auth on `/ws/{session_id}` — any client knowing a session_id can subscribe to `res:{session_id}`.
**Impact**: Contract violation; silent breakage when an LLM sends "action" instead of "type" (or vice versa) — fail surface depends on action handler's `params.get()` defaults. Plus a real **security** issue (session hijack via session_id guessing).
**Recommendation**: (a) Standardise on one key (`type` is what `Command` Pydantic model uses — report 05). (b) Parse incoming WS frames into `Command` before publishing. (c) Tie WS to an auth handshake (X-API-Key as first frame or query param). (d) Add envelope on the return path.

#### C-07: Auth returns 403 where spec 011 mandates 401
**Source spec**: `specs/011/contracts/api.md`: "401 Unauthorized: Missing or invalid API key"; spec 013 NFR-004; data-model 013 error code `AUTH_FAILED` → 401.
**Reality (reports 03, 17)**: `src/api/auth.py` raises `HTTPException(403, "Could not validate credentials")` with `auto_error=False` on `APIKeyHeader`. Contract test `test_post_run_without_api_key_returns_401` actually asserts 403 — name lies.
**Impact**: REST clients written to spec break; downstream retry/refresh logic mis-fires.
**Recommendation**: Change `auth.py` to raise 401; rename the test; verify all contract tests expect 401.

#### C-08: Worker module list inconsistent between PM2 and docker-compose
**Source spec**: spec 010 FR-002 (consistent compose deployment); constitution VIII.
**Reality (reports 04, 11)**: `docker-compose.yml` worker command loads module `src.infrastructure.queue.tasks` (does not exist — `tasks.py` absent); `docker-compose.override.yml` and `ecosystem.config.js` load the correct list. PM2 list includes `research_task`, compose worker command omits it.
**Impact**: `docker compose up` without the override file fails to import. PM2 vs compose run different background workers → research task fails silently on plain compose.
**Recommendation**: Delete the non-existent `tasks` module reference in `docker-compose.yml`; add `research_task` to the base worker command; verify with `docker compose up -d` from a fresh clone.

#### C-09: No 401/503 on `/healthz`, only happy-path
**Source spec**: spec 010 contracts/rest.md §1 explicitly defines 503 with `"redis": "disconnected"` body shape.
**Reality (reports 01, 17)**: Report 01 notes "`health.py` does not return 503 explicitly in the code we saw — stoit проверить". Contract tests cover only happy-path. If Redis dies, `/healthz` still 200 → LB cannot detect degradation.
**Impact**: Constitution VIII reliability claim is unmet; production deployments cannot rely on healthcheck to drain traffic.
**Recommendation**: Map Redis ping failure / pool unavailability to HTTP 503 with the spec-mandated body; add contract test for the unhealthy branch.

### MAJOR

#### M-01: REST paths drifted from spec 010
**spec 010 contracts/rest.md**: `POST /scrape/yandex-maps`, `POST /enrich/site`.
**Reality (report 01)**: `POST /api/v1/yandex-maps/extract` (+`/reviews` added), `POST /api/v1/enrich`. Tests follow code, not spec.
**Impact**: Any external integration following 010 contract is broken.
**Recommendation**: Update spec 010/contracts/rest.md to current paths; bump spec status from "Complete (48/48 tasks)" to "Amended 2026-05-XX".

#### M-02: `EnrichRequest` field shape diverged from spec 010
**spec 010**: `crawl_pages: ["about","services"]`, response includes `success: bool`, `truncated: bool`, `pages_crawled: [...]`, plus 400 `invalid_url` and 413 `content_too_large`.
**Reality (reports 01, 05, 08)**: `EnrichRequest{url, crawl_about: bool, crawl_services: bool}`; response has `truncated` and `pages_crawled` but no `success`; errors are generic 500.
**Impact**: Different API surface; 413 from spec never returned; 400 invalid_url not implemented (relies on Pydantic 422).

#### M-03: `YandexMapsExtractRequest` shape diverged from spec 010
**spec 010**: `{category, center: {lat,lng}, radius, use_stealth, proxy: {...}}`.
**Reality (report 05)**: `{query, region_id, city_slug, target_count, include_raw}`. No `center/radius` — server enumerates whole city via Yandex Maps URL `https://yandex.ru/maps/{region_id}/{city_slug}/search/{q}/`. Adds undocumented `/reviews` endpoint.
**Impact**: Spec 010 acceptance scenario 1 ("category restaurants, center [59.934,30.306], radius 1000m") cannot be expressed against the live API; clients must know region_id/city_slug instead.

#### M-04: `BusinessCard` entity does not exist; replaced by `YandexOrganization`
**spec 010 data-model §1**: `BusinessCard {name, address, phone, website, geo, category}`; `STRUCTURE.md` lists `business_card.py`.
**Reality (reports 05, 08)**: No `business_card.py`. `YandexOrganization` (in `yandex_organization.py`) carries ~65 fields with `extra="allow"`. Response defaults to `include_raw=True` → bloated payload.
**Impact**: Stricter consumer (ML/CV pipeline downstream) needs to write a translator; spec says nothing about the 60+ extra fields.

#### M-05: Research `max_iterations` vs `max_iters` naming drift
**spec 011 contracts/api.md**: `max_iterations` (1-20), `max_tokens` (1000-32000); data-model identical.
**Reality (reports 05, 13)**: `ResearchRequest` uses `max_iters` (1-50), `max_tokens` (1000-2_000_000). Override bounds intentionally raised on 2026-05-20 to fit `quality` preset (`max_iters=25`, `token_budget=1_000_000`).
**Impact**: Clients following 011 contract get 422 on `max_iterations` field name; numeric bounds no longer match spec.

#### M-06: Mode preset numbers drift from spec 011 data-model
**spec 011 data-model**: speed=2 iters/4K tokens, balanced=5/8K, quality=10/16K.
**Reality (report 13)**: speed=2/30K, balanced=6/100K, quality=25/1M.
**Impact**: SC-002/003/004 latency targets may still hold but token budgets are 100× spec; cost projections wrong; constitution X(a) "iteration limits, search breadth, scrape concurrency, token budgets per mode" is satisfied numerically but spec is stale.

#### M-07: AI actions `click_omni` and `extract_jina` declared but unimplemented
**Source spec**: `CommandType` enum (`dsl.py`) declares both; web_interactions.md §4 "Planned"; spec 009 FR-011/FR-012/FR-013/FR-014/FR-015 mention extraction & coordinate fills.
**Reality (reports 07, 10)**: No `ai_actions.py`, no `jina_client.py`, no `omni_client.py`. `action_registry.get_action(CommandType.CLICK_OMNI)` returns `None`. WS / `/sessions/{id}/command` will fail downstream with no structured error.
**Impact**: MCP `session_click_omni`, `session_extract_jina` always fail; spec 009 functional reqs not met.

#### M-08: WebSocket spec actions vs implemented set diverged
**spec 009 contracts/websocket.md**: `goto`, `click_coord`, `click`, `fill`, `extract`, `screenshot`, `screenshot_full`, `click_full_coord`, `fill_full_coord`, `extract_jina`.
**Reality (reports 05, 07)**: Implemented: `goto`, `scroll`, `click_coord`, `type`, `screenshot`, `yandex_maps_extract`, `yandex_maps_reviews`. Missing: `click` (selector), `fill` (selector), `extract` (selector), `screenshot_full`, `click_full_coord`, `fill_full_coord`. Added not in spec: `scroll`, `type` (CSS-fill), `yandex_maps_*`.
**Impact**: Half the documented DSL surface is absent; `type` overlaps `fill` semantically.

#### M-09: DSL contract requires `execute / validate_params / get_name`, code is functions
**spec 010 contracts/dsl.md**: every action class must implement those 3 methods.
**Reality (report 07)**: Actions are bare async functions registered via `@action_registry.register(...)` decorator. No validation, no class hierarchy.
**Impact**: Malformed `params` reach Playwright and fail with cryptic errors instead of structured 422; refactor to classes will be invasive.

#### M-10: DSL spec actions `apply_stealth`, `site_enrich` absent from `CommandType`
**spec 010 contracts/dsl.md**: registers `yandex_maps_extract`, `site_enrich`, `apply_stealth`, extended `goto`.
**Reality (report 07)**: Only `yandex_maps_extract`/`_reviews` in enum. `site_enrich` is invoked only via REST `/api/v1/enrich`, not via DSL.

#### M-11: `LLMExtractRequest` in 013 data-model vs actual `HtmlToMdRequest`
**spec 013 data-model**: `LLMExtractRequest(html, extraction_schema, prompt)`.
**Reality (report 05)**: `HtmlToMdRequest(html, format, extraction_schema)` — no `prompt`, extra `format` literal.
**Impact**: Spec 013 was supposed to rename `JinaExtractRequest` → `LLMExtractRequest` but real rename went to `HtmlToMdRequest`; the model's `prompt` field is missing.

#### M-12: `extract` LLM facade has no schema validation / structured-output enforcement
**Source**: constitution II ("Unified AI Orchestration Facade ... consistent ... structured output handling"); CLAUDE.md prefill pattern.
**Reality (report 10)**: `LLMFacade.extract` falls back to `{"raw_response": text}` on JSON parse error. No Pydantic validation, no `response_format=json_object`, no assistant prefill.
**Impact**: Random hallucinations propagate into LangGraph nodes; constitution II unmet.

#### M-13: No SSE schema validation; `/research/stream` events do not match spec
**Source**: spec 011 contracts/api.md "Event Stream" lists `node_entered`, `node_exited`, `progress`, `completed` events.
**Reality (reports 01, 14, 17)**: `emit_node_event` uses `logging.info` (not structlog), `task_id` is not propagated → store updates only twice (start/end), so `/status` shows `phase=starting, iteration=0` until `completed`. Contract test only checks `Content-Type: text/event-stream`, not event shapes.
**Impact**: FR-021 ("structured log records at each graph-node boundary") unmet; US4 streaming functionally degraded.

#### M-14: `MemorySaver` recreated per `build_graph()`, no Redis-backed checkpoint
**Source**: spec 011 FR-014 ("Completed reports retrievable for a reasonable period"); SC-005 ("100% produce a final report ... regardless of errors").
**Reality (report 13)**: `MemorySaver()` is instantiated inside `build_graph()` on every call → checkpoints lost across worker restarts. Task store has 24-hour TTL but no in-flight checkpoint survival.
**Impact**: Worker restart mid-research = task lost (status `failed`), violating SC-005 in pathological cases.

#### M-15: Cleanup worker is not scheduled and does not actively kill actors
**Source**: spec 009 FR-007, SC-002 (100% within 60 s).
**Reality (report 11)**: `cleanup_worker` is a regular Taskiq task with no `ScheduleSource` registration; nothing periodically `kiq()`s it. It also removes the manager record but does NOT publish `{"type":"stop"}` on `cmd:{session_id}` — actor only exits when its own 10-second-poll observes inactivity.
**Impact**: SC-002 ("60 s of timeout expiry") cannot be met; idle sessions linger until self-exit.

#### M-16: Error envelope not standardised
**Source**: spec 013 NFR-005 `{error, code, details?}`; data-model 013 lists error codes.
**Reality (reports 01, 04)**: Generic 500 on `Exception` in `enrichment.py` / `yandex_maps.py` with `# noqa: BLE001`. No `@app.exception_handler(...)` registered. Sessions error returns `RedisUnavailableError` with code only sometimes. Default FastAPI `{"detail": "..."}` everywhere else.
**Impact**: Clients cannot reliably switch on error code; downstream retry logic guesses based on HTTP only.

### MINOR

#### MN-01: STRUCTURE.md lists files that do not exist
**Reality**: No `src/api/middleware/auth.py` (real path: `src/api/auth.py`). No `src/actions/base.py`. No `src/actions/ai_actions.py`. No `src/domain/models/business_card.py`. No `src/infrastructure/external_api/jina_client.py`. No `src/infrastructure/external_api/omni_client.py`. (Reports 03, 05, 07, 10.)
**Recommendation**: Rewrite STRUCTURE.md tree to match actual `src/` layout (incl. `src/actions/research/{graph,nodes,modes,state,tools,llm_utils}.py`).

#### MN-02: AGENTS.md test counts stale
**AGENTS.md "Test Suite Status (2026-05-07)"**: unit=17, contract=28, integration=31, e2e=23, total=99 passed.
**Reality (reports 16, 17, 18)**: unit ≈ 76 across 10 files, contract = 10 files (count of files matches "28" approximately by test functions), unit text says "266 passed on момент 2026-05-20" (report 14 cites total). Numbers disagree by source.
**Recommendation**: Re-collect via `pytest --collect-only -q` and update AGENTS.md once.

#### MN-03: AGENTS.md and STRUCTURE.md mention `jina_client.py` / `omni_client.py` as placeholders
**Reality**: not present in `src/infrastructure/external_api/` (report 10).

#### MN-04: `web_interactions.md` documents `extract_jina` as planned, but real DSL handler missing
Same as M-07; doc presents it as "Planned" — minor mismatch with reality where it is also in the `CommandType` enum and the MCP server pretends to support it.

#### MN-05: `web_interactions.md` field is `type`, spec 009 ws contract is `action`
Same root as C-06.

#### MN-06: AGENTS.md says proxies "rotated randomly per Yandex Maps request" — confirmed, but no sticky-per-domain
Spec 010 edge case "Proxy Failure: ... attempt with an alternative proxy or fall back to direct connection" is not implemented (report 09: no blacklist, no retry, no hot-reload).

#### MN-07: STRUCTURE.md does not mention `src/actions/research/`, `src/api/routers/research.py`, `src/infrastructure/tasks/`, `src/infrastructure/queue/research_task.py`, `src/mcp_server.py`
Spec 011 added all of these; STRUCTURE.md is pre-011.

#### MN-08: `.env.example` drift
**Reality (report 12)**: `SEARXNG_*`, `REDIS_HOST`, `REDIS_PORT`, `MAX_CONCURRENT_RESEARCH_TASKS` exist in `Settings` but missing from `.env.example`; `RATE_LIMIT_*` commented out.

#### MN-09: `token_bucket.py` is not a token bucket
Name implies refill semantics; implementation is fixed-window `INCR`+`EXPIRE` (report 12). Either rename to `fixed_window_counter.py` or implement Lua-based refill.

#### MN-10: Default secrets ship as fallbacks
**Reality (report 12)**: `API_KEY=default_internal_key`, `ORCHESTRATION_API_KEY="sk-..."` placeholder defaults — risk of accidentally running prod with placeholders.
**Recommendation**: Make required (no default) and fail fast at startup.

#### MN-11: Repo-root `main.py` is a dead stub
"Hello from atomic-scraper-service!" placeholder; not wired into Dockerfile/compose/PM2 (report 04, 19). Delete.

#### MN-12: `restart_mcp.py` only kills, does not restart
Name lies (report 19).

#### MN-13: `kill_mcp.py` uses deprecated Windows `wmic`
Not portable to Linux CI (report 19).

#### MN-14: MCP server hard-codes `BASE_URL` and `API_KEY`
README's `env: { API_KEY: ... }` is misleading because code never reads `os.getenv` (report 19).

#### MN-15: `markdownify` heavy-dep used for one helper
Could be inlined (report 06).

#### MN-16: `UserAgentPool` static, 10 UAs, Chrome 123/124 etc.
Will look anomalous as versions age out (report 09).

#### MN-17: Three different status vocabularies coexist
`TaskStatus` enum (`pending/success/failed`) for `ScrapeResponse`, `Literal[...]` for `ResearchTaskStatus.status`, plain `str` for `InteractiveSession.status` (report 05).

### INFO

#### I-01: `STRUCTURE.md` "Feature 010 components" table is correct
File names match (yandex_maps.py, content_cleaner.py, etc.); only the file claims missing.

#### I-02: Research-agent fixes 2026-05-20 already addressed several drifts
`visited_urls: list[str]` (was set), override bounds raised, `test_nodes.py` mocked, `current_batch` contract. Reflected in reports 13/14.

#### I-03: SearXNG container exists at `infra/searxng/` and is the right answer for Google search
Pivot from Playwright→SearXNG is documented in `docs/про проблемы с serper.md` and `infra/searxng/README.md`; spec 013 just wasn't updated to follow.

#### I-04: 2-of-2 live e2e tests need residential proxies + uvicorn on :8000
Documented in AGENTS.md (report 18). Not a bug; flag as `requires_proxies` marker.

#### I-05: 013 contracts directory is empty
`specs/013-fix-impl/contracts/` exists but holds nothing. The contracts mentioned in spec text are implicit only.

#### I-06: PM2 deployment exists alongside compose
`ecosystem.config.js` is a parallel deployment path (report 04). Not in spec; not a bug; just an extra surface to keep in sync with compose worker module list (see C-08).

## Constitution compliance matrix

| Principle | Status | Notes |
| --- | --- | --- |
| I. Dual-Context Isolation (Stateless/Stateful) | OK | Stateless routers use shared `pool_manager`; stateful sessions use Taskiq actors with per-session contexts. Reports 01, 09, 11. |
| II. Unified AI Orchestration Facade | PARTIAL | `LLMFacade` exists (report 10). Two roles wired (`extraction`, `orchestration`). But no structured-output / Pydantic validation / prefill — M-12. Jina & Omni clients absent — C-05. |
| III. Resource Lifecycle Governance | PARTIAL | Inactivity loop exists in `session_actor` (report 11) but timeout drifted to 30 min (C-03). Cleanup not scheduled (M-15). |
| IV. Clean Architecture Boundaries | OK | Layers `api / domain / infrastructure / actions / core` respected (reports 05, 06, 09, 10, 12); only tight coupling smell is `research/tools.py` calling `SiteEnrichAction()` directly (bypassing rate-limit middleware) — see M-01/C-01. |
| V. Command-Driven Interaction (DSL) | PARTIAL | Registry exists (report 06) but spec required `execute/validate_params/get_name` classes — implementation uses bare functions (M-09). Half the documented DSL actions are missing (M-07, M-08, M-10). |
| VI. Test-First Implementation | PARTIAL | TDD discipline visible in tests/research/* and tests/contract/* (reports 14, 16, 17). But many subsystems lack unit coverage (`websockets`, `extraction.py`, `interaction.py`, `yandex_maps.py`, `site_enricher.py`, `pool_manager`, `proxy_provider`, `tools.py`, MCP server) — report 16. |
| VII. Backend-Only Focus | OK | No frontend code observed. |
| VIII. Production Deployment Readiness | PARTIAL | Dockerfile + compose + healthcheck present (reports 04, 18) but `/healthz` lacks 503 path (C-09); compose worker module drift (C-08); CORS unset; lifespan startup empty (report 04). |
| IX. Anti-Bot Detection Mitigation | PARTIAL | Stealth recipe + UA pool + proxy file all present (report 09) but rate-limit domain source is wrong (C-01); no sticky-per-domain proxy (MN-06); UA pool small/aging (MN-16); CAPTCHA = hard fail with no retry (report 08). |
| X. Autonomous Research Agent | PARTIAL | Three modes, LangGraph, polling endpoints, SSE stream all present (reports 13, 14). 4 hard loop-safety constraints — **3 of 4 fully enforced** (deadline, stall, iter cap); **token budget 85% trigger is dead code** (C-02). Tool reuse OK (in-house SearXNG, SiteEnricher, LLMFacade — report 15). FR-022 Yandex-only-on-request: tool not implemented in `tools.py` (info, not a bug). |

## Top 10 actionable items (приоритизировано)

1. **Fix rate-limit domain source (C-01).** Move `consume()` call to `yandex_maps.py` / `enrichment.py` / `site_enricher.py` actions, keyed on the outbound URL host, OR have middleware parse target URL from payload for known routes.
2. **Wire `tokens_used` (C-02).** Capture `response.usage.total_tokens` in `OpenAICompatibleClient.generate`, accumulate via state in nodes that call the LLM (`classify`, `plan`, `extract_facts_llm`, `answer`). Restores constitution X(b).
3. **Pick one inactivity timeout (C-03).** Patch `docker-compose.override.yml` to `SESSION_INACTIVITY_TIMEOUT=600` to match spec/AGENTS, or amend FR-007/AGENTS to 1800 and bump constitution III.
4. **Standardise auth code on 401 (C-07).** Fix `auth.py`, rename misleading test, add contract assertions.
5. **Repair `docker-compose.yml` worker command (C-08).** Drop non-existent `src.infrastructure.queue.tasks`, add `research_task`. Verify `docker compose up` from clean clone.
6. **Implement `/healthz` 503 branch (C-09).** Map Redis/pool failures to HTTP 503 with spec body shape; add contract test.
7. **Reconcile `/jina-extract` deletion across spec 009, web_interactions, STRUCTURE, AGENTS, and `src/mcp_server.py` (C-05).** Rename MCP tool to `html_to_md`, update URL.
8. **Schedule the cleanup worker and have it publish STOP on `cmd:{sid}` (M-15).** Either register a Taskiq `ScheduleSource` or run a periodic asyncio loop in the API process; meet SC-002 (60 s).
9. **Add Pydantic validation + envelope on WebSocket frames (C-06).** Parse incoming JSON into `Command` model; wrap outgoing Redis bytes in `{status, action, data}`; add API-key handshake.
10. **Refresh STRUCTURE.md and AGENTS.md (MN-01, MN-02, MN-07).** Match actual tree; recollect test counts via `pytest --collect-only`; remove references to non-existent files; add 011/MCP additions.
