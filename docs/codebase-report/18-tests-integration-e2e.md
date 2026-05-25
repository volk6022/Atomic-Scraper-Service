# Tests: tests/integration/ + tests/e2e/

## Files analyzed

### tests/integration/ (11 files)
- `tests/integration/test_redis.py`
- `tests/integration/test_timeout.py`
- `tests/integration/test_docker_compose.py`
- `tests/integration/test_session_redis_failure.py`
- `tests/integration/test_content_convert.py`
- `tests/integration/test_content_cleaning.py`
- `tests/integration/test_proxy_integration.py`
- `tests/integration/test_auth.py`
- `tests/integration/test_research_graph.py`
- `tests/integration/test_search_client.py`
- `tests/integration/test_yandex_extraction.py`

### tests/e2e/ (5 files)
- `tests/e2e/test_docker_deployment.py`
- `tests/e2e/test_rate_limiting_flow.py`
- `tests/e2e/test_site_enrichment_flow.py`
- `tests/e2e/test_auth_flow.py`
- `tests/e2e/test_yandex_maps_full_flow.py`

### Context
- `tests/conftest.py` — global autouse fixtures (`mock_redis`, `reset_research_store`)
- `pyproject.toml` — `asyncio_mode = "auto"`, registers marker `e2e: live end-to-end tests`
- `AGENTS.md` / `README.md` — Test Suite Status table (99 passed, 31 integration + 23 e2e, 2 of which live)

## Purpose & responsibilities

**integration/** — Multi-component flows assembled against real Python objects but with all external
side-effects mocked: Redis, Playwright pages, httpx clients, proxy provider, browser pool. They
verify that wiring across the layered architecture (router → action → infra → external client)
behaves as a unit. A subset is configuration-validation only (`test_docker_compose.py` reads YAML;
`test_content_*` exercise HTML-cleaning utilities with hardcoded strings).

**e2e/** — Top-of-stack behaviour through the FastAPI app. Mostly run in-process via
`httpx.ASGITransport(app=app)` and mock the deepest call site (action `.execute`, `rate_limiter.consume`).
Two tests are genuinely live: they require `uvicorn` (or `docker compose up`) listening on
`localhost:8000` and, for `test_yandex_maps_full_flow`, residential proxies plus reachable
`yandex.ru/maps`.

## Integration coverage map

| компонент | integration-тесты | что моментально, что в Docker |
| --- | --- | --- |
| Redis client (`infrastructure/queue`) | `test_redis.py` | `ping()` — uses live Redis URL from settings, but `conftest.py` autouse `mock_redis` patches `Redis.from_url`, so it runs without Docker |
| Session inactivity cleanup | `test_timeout.py` | Pure in-process — sets `last_active = now-700s`, calls cleanup, asserts session removed |
| Docker compose config | `test_docker_compose.py` | Reads `docker-compose.yml` as YAML, validates services/healthchecks/volumes — no Docker daemon needed |
| Sessions router under Redis failure | `test_session_redis_failure.py` | Patches `run_session_actor.kiq`, `manager.publish_command`, `manager.subscribe_results` to raise — asserts HTTP 503 graceful degradation |
| HTML → Markdown / Text conversion | `test_content_convert.py` | Hardcoded HTML strings → `html_to_markdown()` / `html_to_text()` — instant |
| HTML cleaning (scripts/styles/comments) | `test_content_cleaning.py` | Hardcoded strings → `clean_html_content()` — instant |
| `BrowserPoolManager.create_context` proxy wiring | `test_proxy_integration.py` | Patches `async_playwright`, `AsyncMock` browser/context — asserts proxy passed as `{"server": url}`; also reads `docker-compose.yml` for mount volumes |
| `X-API-Key` auth across enrich/sessions/research | `test_auth.py` | ASGITransport in-process; mocks `run_session_actor.kiq`; asserts 403 missing/invalid key, 200/500/503 with key, 200 on public `/healthz`, `/docs` |
| LangGraph build for 3 modes | `test_research_graph.py` | Direct `build_graph(mode)` calls for "speed"/"balanced"/"quality" — asserts non-None graph object |
| `SearchClient` (SearXNG) | `test_search_client.py` | `AsyncMock` on `client._client.get`; verifies JSON parsing, URL dedup, retry on 502/empty responses |
| Yandex Maps XHR interception & parsing | `test_yandex_extraction.py` | Fake Playwright `page` (with `page.on('response', cb)` simulator), `_make_response_mock()` factory; patches `pool_manager.create_context`, `proxy_provider.get_proxy`, `asyncio.sleep`; asserts OID dedup, captcha detection |

## E2E coverage map

| user story | e2e-тесты | требует docker compose? | проверяет live HTTP? |
| --- | --- | --- | --- |
| Dockerfile + docker-compose.yml define playwright install, services, healthchecks | `test_docker_deployment.py` | No — file-string checks only (gated with `@pytest.mark.skipif`) | No |
| Per-domain rate-limit middleware emits headers / 429 | `test_rate_limiting_flow.py` | No | No — ASGITransport, `rate_limiter.consume` mocked |
| `X-API-Key` enforced on every protected endpoint | `test_auth_flow.py` | No | No — ASGITransport + parametrized routes; all actions mocked |
| `/api/v1/enrich` returns cleaned text from a real site | `test_site_enrichment_flow.py` (most cases structural); `test_enrichment_returns_clean_text` | **Yes** for the one live case (`docker compose up` or local uvicorn) | Yes — that one test hits `localhost:8000` |
| `/api/v1/yandex-maps/extract` end-to-end against live Yandex | `test_yandex_maps_full_flow.py::test_yandex_maps_endpoint_returns_businesses` (and reviews variant) | **Yes** — needs API on :8000 + `proxies.txt` + residential proxies | Yes — and reaches `yandex.ru/maps/api/search` |

## Live vs structural breakdown

Per README + AGENTS.md the suite is **31 integration + 23 e2e = 54 tests**, of which only **2** open
TCP to `localhost:8000`:

- `tests/e2e/test_site_enrichment_flow.py::test_enrichment_returns_clean_text`
- `tests/e2e/test_yandex_maps_full_flow.py::test_yandex_maps_endpoint_returns_businesses`

Everything else is structural or in-process:

- **Pure config / file reads (~3 tests):** `test_docker_compose.py`, `test_docker_deployment.py`,
  the docker-compose mount check inside `test_proxy_integration.py`.
- **Pure utility (~ a dozen):** `test_content_convert.py`, `test_content_cleaning.py`,
  `test_research_graph.py`, `test_timeout.py`.
- **ASGITransport in-process FastAPI:** `test_auth.py`, `test_auth_flow.py`,
  `test_rate_limiting_flow.py`, `test_session_redis_failure.py`, the structural
  cases in `test_site_enrichment_flow.py` and `test_yandex_maps_full_flow.py`.
- **Fake Playwright objects:** `test_proxy_integration.py`, `test_yandex_extraction.py`.
- **Mocked httpx:** `test_search_client.py`.

## External dependencies

| Dependency | How it appears in this suite |
| --- | --- |
| **Redis** | Never live. `tests/conftest.py` has an autouse `mock_redis` fixture that patches `redis.asyncio.Redis.from_url` and `redis.asyncio.client.Redis.from_url` to return a `MagicMock` with `AsyncMock` `ping`/`publish`/`close`/`pubsub`, and patches `redis.Redis.from_url` to raise `ConnectionError` so the sync research_store falls back to its in-memory dict. `reset_research_store` clears `research_store._local_fallback` before/after each test. No testcontainers, no docker. |
| **Playwright** | Never launches a real browser. `test_proxy_integration.py` patches `src.infrastructure.browser.pool_manager.async_playwright`; `test_yandex_extraction.py` constructs hand-rolled fake `page`/`response` objects with `_make_page_mock()` / `_make_response_mock()`. |
| **httpx** | Used as a real client only in the 2 live e2e tests (with `localhost:8000`). Elsewhere either via `AsyncClient(transport=ASGITransport(app=app))` (in-process) or with `client._client.get` patched (`test_search_client.py`). |
| **Docker** | Read-only — files like `docker-compose.yml` and `Dockerfile` are parsed as YAML/text in `test_docker_compose.py` and `test_docker_deployment.py`. No container is started by the test suite. |
| **Internet / yandex.ru** | Reached only by `test_yandex_maps_full_flow.py::test_yandex_maps_endpoint_returns_businesses` (through the live API on :8000 → real Yandex Maps). |
| **LangGraph / LangChain** | `test_research_graph.py` calls `build_graph()` directly; no LLM calls. |
| **LLM endpoints** (OpenAI-compatible) | Not exercised by the integration/e2e suite. |

## Open questions / smells

- **Live Yandex test is flaky by design.** `test_yandex_maps_endpoint_returns_businesses` depends on
  `proxies.txt` containing residential IPs (AGENTS.md explicitly warns datacenter IPs get blocked at
  the TLS/browser layer). On CI without residential proxies it will return 0 businesses and fail.
  Worth marking it more strictly than just `@pytest.mark.e2e` (e.g. a `live_proxies` marker) or
  parking it behind an env flag.
- **Hardcoded `localhost:8000`** in the two live tests — no fixture/env override. Anyone running
  the API on a different port (or in another container network) has to patch the URL by hand.
- **`test_redis.py` is misleading.** Its name suggests a live Redis check but the autouse `mock_redis`
  fixture means it actually validates the mock, not real connectivity. If a real Redis ping is the
  intent (the AGENTS state-machine notes imply so), the test should opt out of the autouse mock.
- **`asyncio` import in `test_timeout.py`-style tests** is fine, but the cleanup test mutates module
  globals (`session_manager.sessions`) directly — leakage between tests is possible if ordering changes.
- **`@pytest.mark.skipif` in `test_docker_deployment.py`** — the report didn't expose the predicate;
  if it skips on missing `Dockerfile`, the suite will silently shrink instead of failing loudly when
  the file disappears.
- **Only one pytest marker is registered** (`e2e`). Several files would benefit from `slow`,
  `live`, `requires_redis`, or `requires_proxies` markers to make selection of CI vs local sets
  obvious.
- **Mock placement spans both `infrastructure.queue.session_actor.run_session_actor.kiq` and
  `api.routers.sessions.run_session_actor.kiq`** across test files (compare `test_auth.py` vs
  `test_session_redis_failure.py`). A refactor that moves the import would break one set silently.
- **No SearXNG live test.** All `SearchClient` coverage is mocked; the integration with the actual
  SearXNG container in `infra/searxng/` is not exercised here.
