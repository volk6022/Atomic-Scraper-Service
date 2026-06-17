# Tests: tests/contract/

## Files analyzed

- `tests/contract/test_health_endpoint.py`
- `tests/contract/test_scraper.py`
- `tests/contract/test_stateless.py`
- `tests/contract/test_html_to_md.py`
- `tests/contract/test_searxng_search.py`
- `tests/contract/test_sessions.py`
- `tests/contract/test_yandex_maps_api.py`
- `tests/contract/test_yandex_maps_reviews_api.py`
- `tests/contract/test_enrichment_api.py`
- `tests/contract/test_research_endpoint.py`

## Purpose & responsibilities

In-process contract tests запускают FastAPI приложение через `httpx.AsyncClient` поверх `ASGITransport` — без реальной сети, без поднятого uvicorn-сервера. Цель — зафиксировать публичный HTTP-контракт каждого endpoint: путь, метод, формат запроса, схему ответа, статус-коды, поведение middleware (`X-API-Key` auth, rate-limit). Внешние тяжёлые зависимости (Playwright `BrowserPoolManager`, Redis broker, Taskiq, внешние HTTP-клиенты SearXNG/OmniParser, фоновые actions Yandex Maps) подменяются `unittest.mock` (AsyncMock / MagicMock / `monkeypatch.setattr`), а сами actions либо мокируются на уровне `.execute`, либо вызываются как заглушки. `AGENTS.md` фиксирует фактический срез: 28 тестов в `contract/`.

## Endpoint coverage map

| endpoint | контракт-тесты | status codes покрыты | пропущенные кейсы |
| --- | --- | --- | --- |
| `GET /healthz` | `test_health_endpoint.py` (5) | 200; <3000ms SLA | 503 unhealthy не покрыт; в спеке заявлен 503 + `"redis": "disconnected"` |
| `POST /scraper` | `test_scraper.py` (12), `test_stateless.py` (часть) | 200, 422 (missing/invalid url, output_format), 403 | 503/500 на сбое browser pool; rate-limit (429) не покрыт |
| `POST /serper` | `test_searxng_search.py` (9), `test_stateless.py` | 200, 403, 422 (missing/invalid `q`, `num`) | 5xx при недоступности SearXNG backend |
| `POST /html-to-md` | `test_html_to_md.py` (4), `test_stateless.py` | 200, 403, 422 (missing `html`) | format=text vs markdown оба покрыты; нет проверки invalid `format` |
| `POST /omni-parse` | `test_stateless.py` (3) | 200, 403, 422 (missing `base64_image`) | большой/битый base64; ошибки upstream LLM |
| `POST /sessions` | `test_sessions.py` | 200, 403, 503 (Redis ConnectionError/TimeoutError, параметризовано) | 422 (плохой viewport/proxy); 429 rate-limit |
| `POST /sessions/{id}/command` | `test_sessions.py` | 503 (publish/subscribe Redis fail), invalid session id → 503 | 200 happy-path (нет полного контракта успешного command); 404 на отсутствующий session |
| `DELETE /sessions/{id}` | `test_sessions.py` | 503 (param: ConnectionError, TimeoutError) | 200/204 успех; 404 несуществующий |
| `POST /api/v1/yandex-maps/extract` | `test_yandex_maps_api.py` (12) | 200, 422 (missing/empty `query`, `region_id<1`, `target_count` too high), 403, 503 (`YandexCaptchaError`) | 429 (rate-limit), 400 (`invalid_request` per spec) — спека предусматривает иной формат ошибки |
| `POST /api/v1/yandex-maps/reviews` | `test_yandex_maps_reviews_api.py` (10) | 200, 422 (missing oid, non-digit oid, invalid ranking, count too high), 403, 503 (captcha) | 404 для несуществующего business_oid |
| `POST /api/v1/enrich` | `test_enrichment_api.py` (10) | 200, 422 (missing url, invalid url), 403, 500 (browser error) | 413 (`content_too_large`) из спеки 010; 503 |
| `POST /api/v1/research/run` | `test_research_endpoint.py::TestResearchRunEndpoint` (5) | 202, 403 (нет API-key — спека требует 401), 422 (invalid mode, query <3 chars), 429 (>=5 concurrent) | пограничные: `max_iterations`/`max_tokens` валидация |
| `GET /api/v1/research/status/{task_id}` | `TestResearchStatusEndpoint` (3) | 200 running, 200 completed, 404 (unknown id) | 200 failed/degraded из спеки; expired tasks (24h) |
| `GET /api/v1/research/stream/{task_id}` | `TestResearchStreamEndpoint` (1) | 200 + `Content-Type: text/event-stream` | конкретные SSE-события (`node_entered`, `progress`, `completed`); 404; auth |
| `WS /ws/{session_id}` | — | — | **полностью отсутствует контракт-тест** (см. `02-api-websockets.md`) |

## Common fixtures / mocks

- **Транспорт**: во всех файлах используется `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")` — Starlette `TestClient` не применяется, тесты `pytest.mark.asyncio`.
- **Аутентификация**: общий заголовок `X-API-Key: default_internal_key` (значение из `core/config.py`); отсутствие ключа стабильно даёт `403` (а не `401` — расхождение со спекой research-endpoint, который требует 401).
- **Browser pool**: `src.infrastructure.browser.pool_manager.BrowserPoolManager.create_context` → `MagicMock`/`AsyncMock`, возвращает фейковый `BrowserContext` с `new_page` (используется в `test_scraper`, `test_stateless`, `test_enrichment_api`).
- **Actions Yandex**: `src.actions.yandex_maps.YandexMapsExtractAction.execute` и `YandexMapsReviewsAction.execute` патчатся `AsyncMock` с заранее подготовленным результатом или `side_effect=YandexCaptchaError(...)` для 503-кейса.
- **External clients**: `SearXngSearchClient.search`, `orchestration_client.generate` (omni-parse) патчатся через `monkeypatch.setattr`.
- **Taskiq/Redis (sessions)**: `kiq` метод задачи и `publish_command` / `subscribe_results` мокируются `AsyncMock`, `side_effect=ConnectionError/TimeoutError` для 503-кейсов. Реальный Redis не нужен.
- **Research**: `get_task` и `get_concurrent_task_count` патчатся (in-memory store по спеке 011), `asyncio.sleep` мокируется для SSE-теста.
- **Глобальный side-effect**: `asyncio.sleep` подменяется в `test_enrichment_api` (ускоряет crawl-логику).

## External dependencies

- `httpx.AsyncClient` + `httpx.ASGITransport` — единственный путь до приложения; реальные сокеты не открываются.
- `pytest-asyncio` (все тесты `async def`).
- `unittest.mock` (`AsyncMock`, `MagicMock`, `patch`) + `pytest`-fixture `monkeypatch`.
- FastAPI app импортируется как in-process объект; middleware (`rate_limit`, `auth`) исполняются по-настоящему — поэтому тесты на 403 валидны без моков auth.

## Open questions / smells

- **WebSocket `/ws/{session_id}` без контракт-теста** — единственный endpoint из таблицы `AGENTS.md`, не покрытый contract-слоем (тесты есть только в `unit/` для manager).
- **401 vs 403 в research**: `specs/011-auto-research-agent/contracts/api.md` обещает `401 Unauthorized` при отсутствии ключа, но тесты фиксируют `403` (`test_post_run_without_api_key_returns_401` ожидает 403, имя метода вводит в заблуждение). Middleware `auth.py` возвращает 403 — расходимость со спекой.
- **Healthz 503 не покрыт**: спека 010 явно описывает unhealthy-ветку с `"redis": "disconnected"`; тесты проверяют только happy-path и наличие ключей.
- **Sessions happy-path для `/command` и `DELETE`**: контракт-тесты фиксируют только 503-ветки на падении Redis; 200/204 успех не закреплён контрактом — велик риск регрессии формата успешного ответа.
- **Yandex Maps 429 (`rate_limit_exceeded`)** заявлен в `specs/010/contracts/rest.md`, но в тестах не воспроизведён; rate-limit middleware ловится только в research-endpoint.
- **Enrichment 413** (`content_too_large`) из спеки 010 не имеет теста; вместо него есть generic 500 на browser error.
- **Расходимость путей со спекой 010**: спека говорит `POST /scrape/yandex-maps` и `POST /enrich/site`, а реальный код и тесты используют `/api/v1/yandex-maps/extract` и `/api/v1/enrich` (контракт-тесты соответствуют коду, не спеке).
- **`test_command_invalid_session_id`** не проверяет валидацию ID как таковую — просто эмулирует Redis-ошибку и ожидает 503. Реального покрытия "несуществующий session" нет.
- **Дубликат покрытия**: `/scraper` и `/html-to-md` дублируются между `test_scraper.py`/`test_stateless.py` и `test_html_to_md.py`/`test_stateless.py` — стоит консолидировать.
- **Research stream**: проверяется только `Content-Type`, конкретные события (`node_entered`, `progress`, `completed`) из спеки не валидируются.
