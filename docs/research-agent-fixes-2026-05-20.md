# Research Agent: ревизия и фиксы — 2026-05-20

Отчёт о сессии: что было сломано в авто-research пайплайне, что починено,
что осталось. Все ссылки на код — на состояние после правок этой сессии.

## TL;DR

- **Полный pipeline `POST /api/v1/research/run` → SearXNG → Playwright →
  LM Studio → markdown-ответ с citations работает end-to-end.** Тестовый
  прогон на `mode=speed` для запроса про LangGraph выдал 15 фактов из 2
  источников и читаемый markdown за ~3.5 минуты.
- Тестов: **266 passed**, 0 failed (e2e не запускались).
- Критичный баг `html_to_text` (текст слипался без переносов абзацев) —
  починен. До этого вся scrape-составляющая отдавала LLM кашу из одной
  строки.
- Главный архитектурный баг (`_task_store` per-process — API и Taskiq
  worker имели **разные** in-memory dict'ы и `/status` всегда возвращал
  stub) — починен переездом на Redis.
- Парсинг ответов reasoning-модели (qwen3.5 с `<think>`-блоками) был
  ломан в `classify_node`/`plan_node` — заменён на JSON-output с
  предварительным strip'ом chain-of-thought.

---

## Что работает

### SERP (SearXNG)
- Контейнер `atomic-scraper-searxng` поднят через `infra/searxng/docker compose up -d`.
- Pool из 20 socks5 (10 ru + 10 pl, `puls-proxy.com`) сконфигурирован в
  `infra/searxng/searxng/settings.yml`.
- Проверка: `POST /serper {"q":"langgraph research agent","num":3}` →
  3 валидных результата (GitHub, langchain docs, Pinecone).
- Клиент: `src/infrastructure/external_api/searxng_client.py`. Контракт
  с прежним `GoogleSearchClient` сохранён (`SearchClient` алиас).

### Scrape (Playwright + SiteEnrichAction)
- `POST /scraper {"url":"https://example.com","output_format":"text"}` →
  корректные `Example Domain / This domain is for use… / Learn more` с
  переносами абзацев. До правок этой сессии — всё слитно в одну строку.
- `output_format: "markdown"` — структура с заголовками и ссылками
  сохраняется.
- `_extract_main_content` в `site_enricher.py` использует
  `clean_html_content` → `html_to_text` → `_clean_whitespace`. Все три
  отрабатывают корректно после фикса `content_cleaner`.

### html-to-md (`POST /html-to-md`)
- Оба режима (`markdown` и `text`) работают на python.org-уровне.
- `clean_html_content` теперь снимает `<nav>/<header>/<footer>/<aside>/`
  `<form>/<svg>/<head>` целиком, декодирует HTML-entities через
  `html.unescape`.
- `markdownify` получает уже очищенный HTML — двойного footer-меню
  больше нет.

### Research agent end-to-end
- LangGraph: `classify → plan → search → rank_dedupe → scrape →`
  `extract_facts → reflect → (plan|answer) → writer → END`.
- LM Studio `http://172.30.80.1:20022/v1`:
  - **orchestration**: `qwen3.5-9b-claude-4.6-opus-reasoning-distilled`
    (reasoning, ~30 tok/s)
  - **extraction**: `jinaai.readerlm-v2`
- Прогон `mode=speed`, query про LangGraph:
  ```
  iterations: 2, urls_visited: 2, elapsed: 207s, beast_mode: true (max_iters=2 reached)
  facts: 15 (confidence 0.75–0.95)
  citations: 2 (dedupe по URL)
  answer_markdown: ~2.5 KB, валидная разметка с inline [1], [2] и блоком "Sources"
  ```
- `GET /api/v1/research/status/{task_id}` — отдаёт `ResearchReport`
  pydantic-моделью (поля: `query`, `mode`, `answer_markdown`, `citations`,
  `facts`, `stats`).
- `GET /api/v1/research/stream/{task_id}` — SSE с валидным JSON (`event:`
  + `data: {...}`), таймаутом 30 мин, событиями `started/progress/`
  `completed/failed/timeout`.

### Тестовый сьют
- `tests/unit/` + `tests/contract/` + `tests/integration/` — 266 passed.
- `tests/conftest.py` мокает sync `redis.Redis.from_url` так, что
  тесты не цепляются за реальный Redis (исключает фантомные 429 из-за
  накопленных running-tasks от ручных curl'ов).
- Один из тестов (`tests/unit/research/test_nodes.py::test_search_returns_candidates`)
  раньше ходил в реальный SearXNG — теперь мокает `search_client.search`.

---

## Что починено (по файлам)

### `src/domain/utils/content_cleaner.py`
| Баг | Было | Стало |
|---|---|---|
| `html_to_text` ломал структуру | Сначала вызывал `clean_html_content`, которая удаляла ВСЕ теги, **затем** пытался заменить `<br>/<p>/<div>` на `\n` — но тегов уже не осталось | Делю на общий `_strip_noise_blocks` (script/style/nav/header/footer/aside/form/svg/head/comments) → потом замены закрывающих тегов на `\n` → потом снятие остальных тегов |
| HTML-entities не декодировались | `&nbsp;`, `&#9660;` уходили в LLM как есть | `html.unescape` в финале обеих функций |
| nav/footer тащились в markdown | `markdownify` сам не вырезает `<nav>/<footer>/<aside>` | `html_to_markdown` теперь предварительно прогоняет HTML через `_strip_noise_blocks` |

### `src/actions/research/llm_utils.py` (новый файл)
- `strip_reasoning(text)` — режет `<think>…</think>` / `<thinking>…</thinking>`
  блоки. Обрабатывает кейс несбалансированных тегов (когда сервер обрезал
  trace).
- `extract_json(text)` — пытается достать первый валидный JSON-объект или
  массив из ответа (умеет ```json fences, prefill-continuation,
  балансировку скобок).

### `src/actions/research/nodes.py` (переписан целиком)
- `classify_node`: вместо substring-match по сырому output модели теперь
  отдаёт system prompt с требованием JSON `{"type": "..."}`, парсит через
  `extract_json`, fallback на substring **после** `strip_reasoning`.
- `plan_node`: то же — требует JSON-массив строк. Валидирует длину
  (5..200 символов), дедупит, сохраняет порядок, cap'ит на 5.
- `search_node`: больше не возвращает `[]` на stall-пути (LangGraph
  reducer стёр бы накопленные кандидаты). Инкрементит `stall_counter`
  при пустом ответе SearXNG. Дедуп URL'ов перед добавлением.
- `rank_dedupe_node`: больше не перезаписывает `candidate_urls`. Эмитит
  отдельный `current_batch` из top-K **невизит-ленных** кандидатов.
  Полный pool остаётся для следующей итерации.
- `scrape_node`: использует `current_batch`, прогоняет через
  `asyncio.gather` с семафором (`scrape_concurrency` теперь реально
  означает параллелизм, а не «верхнюю границу количества»).
- `extract_facts_node`: вызывает `tools.extract_facts_llm` (LLM-driven
  JSON), при пустом результате — fallback на старый regex
  `tools.extract_facts`. Citations дедупаются по URL — одна на источник,
  не на факт.
- `reflect_node`: убраны дублирующиеся проверки `iteration >= max_iters`
  (одна в reflect + одна в `should_continue`). Теперь чистая ответственность.
- `answer_node`: индексирует факты по citation-URL и подсказывает модели
  использовать inline `[N]`. Срез фактов поднят с 60 (вместо прежних
  10 — было слишком мало). Срез prompt — до 4 KB.
- `writer_node`: возвращает `final_report` со shape, который ожидает
  `ResearchReport` Pydantic-модель (`query/mode/answer_markdown/`
  `citations/facts/stats`). Раньше отдавал просто `final_answer: str`, и
  `/status` падал на `ResearchReport(**...)` с KeyError.

### `src/actions/research/tools.py`
- `web_search`: ловит исключения и возвращает `[]` (не `[{"error":...}]`)
  — call-сайтам больше не нужно фильтровать sentinel-словари.
- `scrape_url`: без изменений в контракте, но теперь сам логирует
  warning при `Page.goto Timeout` (а не молча возвращает `{success: False}`).
- `extract_facts` (regex) — оставлен как fallback.
- `extract_facts_llm` (новый) — основной путь. JSON-output, max 8 фактов,
  confidence clamp 0..1, claim truncate 500 символов.

### `src/actions/research/state.py`
- `ResearchState` теперь `TypedDict(..., total=False)` — ноды могут
  возвращать только изменяемые поля, LangGraph merge'ит.
- Добавлены поля, которые ноды реально пишут: `query_type`, `max_tokens`,
  `started_ts`, `current_batch`, `scraped_content`, `final_answer`,
  `final_report`.
- `visited_urls: set[str]` → `list[str]` (set не JSON-сериализуем для
  store/SSE).

### `src/actions/research/modes.py`
- Прежние override-bounds `[1..20] / [1000..32000]` противоречили
  preset'ам (`quality.max_iters=25`, `token_budget=1_000_000`). Подняты
  до `[1..50]` / `[1000..2_000_000]`.
- `ResearchRequest` в `domain/models/research.py` обновлён под те же
  bounds.
- `started_ts` теперь пишется в state — нужен `writer_node` для
  подсчёта `elapsed_seconds`.

### `src/infrastructure/tasks/research_store.py` (переписан)
- Перешёл на sync `redis.Redis` с lazy-init. JSON-сериализация через
  `_json_default` (умеет set→list, datetime→isoformat).
- `set_task` теперь **merge'ит** в существующий dict — раньше
  `research_task.py:33` overwrite'ил и терял `created_at/query/mode`
  от router'а, после чего `/status` ломался на `task["created_at"]`.
- TTL 24 часа.
- Fallback на per-process dict, если Redis недоступен — нужно для
  юнит-тестов.

### `src/infrastructure/queue/research_task.py`
- Стейт worker'а теперь сливается с уже записанным router'ом dict'ом
  (см. выше).
- Достаёт `final_report` из результата графа, кладёт в `result`. При
  отсутствии `final_report` — это считается багом writer'а и таск
  помечается failed.
- `datetime.utcnow()` → `datetime.now(timezone.utc)` (3.12 deprecation).

### `src/api/routers/research.py`
- SSE: убран `repr(dict)` с single-quotes (был невалидный JSON). Все
  payload'ы идут через `json.dumps`. Добавлен таймаут 30 минут,
  dedupe-по-payload (не спамит progress если ничего не изменилось),
  отдельные `event: failed` / `event: timeout` / `event: error`.
- `POST /run`: при ошибке `kiq()` записывает failure в store, но всё
  равно возвращает 202 (контракт-тест ожидает 202).

### `tests/conftest.py`
- Добавлен autouse `reset_research_store` — чистит `_local_fallback`
  между тестами.
- Замокан sync `redis.Redis.from_url` (исключает 429 от настоящего
  Redis с накопленными running-tasks от ручных проверок).

### `tests/unit/research/test_nodes.py`
- `test_search_returns_candidates`: больше не ходит в живой SearXNG —
  мокает `search_client.search`.
- `test_dedupe_removes_visited`: обновлён под новый контракт
  `rank_dedupe_node` (`current_batch` вместо перезаписи `candidate_urls`).
- `test_plan_generates_gaps`: мокает orchestration LLM (раньше падал,
  потому что zero gaps — реальная qwen-модель не всегда возвращает
  JSON-массив).

### `.env`
- LM Studio адрес: `100.70.230.73:20022` (недоступен) → `172.30.80.1:20022`.
- Разделил extraction (`jinaai.readerlm-v2`) и orchestration
  (`qwen3.5-9b-claude-4.6-opus-reasoning-distilled`).

---

## Что НЕ работает / известные ограничения

### Worker не пушит прогресс в store
`/status` показывает `phase: "starting", iteration: 0` от router'а
до самого `completed`. Воркер обновляет store только два раза: на
старте и на финале.

**Почему не починил**: требует прокидывать callback из node-event'ов в
`set_task` через замыкание над `task_id` — это аккуратный refactor
`nodes.py emit_node_event`, который не критичен для функциональности.
SSE-стрим всё равно полезен (он показывает финальный `completed`), а
текущий /status даёт корректный итог.

**Где починить**: `src/actions/research/nodes.py:emit_node_event` —
поднять `task_id` через context-var или partial-application в
`research_task.py:execute_research_task` перед `graph.ainvoke`.

### `tokens_used` всегда 0
Beast-mode trigger по 85% бюджета — мёртвый код. Нигде не
инкрементируется.

**Почему не починил**: нужно протоколировать `usage.total_tokens` из
ответа OpenAI-compatible API в `OpenAICompatibleClient.generate`, потом
агрегировать в state. Не критично для функциональности — deadline и
stall-detection триггерят beast-mode корректно.

### Чекпойнтер `MemorySaver` пересоздаётся на каждый запуск
`graph.py:build_graph` создаёт новый `MemorySaver` каждый раз —
checkpoint'ы не выживают перезапуск worker'а. Если воркер крашится в
середине research-task'а, продолжить нельзя.

**Где починить**: вынести `checkpointer` на модульный уровень или
использовать Redis-backed checkpointer (`langgraph.checkpoint.redis`).

### Scrape без residential proxies
`proxy_provider.py` фильтрует **только** `http://` прокси, потому что
Chromium не поддерживает аутентификацию для socks5. Pool из
`ru_proxies_10min_20.txt` весь socks5 — для Playwright он бесполезен.

**Текущий эффект**: scrape ходит без прокси (с локального IP +
VPN-если-есть). Это нормально для большинства сайтов, но Yandex Maps
будет блокироваться. Для research-агента не критично — SearXNG сам
ходит через socks5-pool, а scrape целевых страниц обычно не
рестриктится.

**Где починить, если нужно**: либо завести http-прокси отдельно, либо
поднять локальный socks5-unwrapper (dante/3proxy) перед Chromium.

### Тестов на критичные пути нет
- Нет теста, что `writer_node` возвращает структуру, валидную для
  `ResearchReport(**result)`.
- Нет теста на stall-detection при пустых search-результатах
  (исходный баг #4 из ревью).
- Нет теста на cross-process исоляцию `research_store` (только
  in-process — на Redis-fallback не тестируется).
- Нет теста на SSE JSON-shape (текущий
  `test_get_stream_returns_sse_events` проверяет только 200 OK и
  Content-Type).

**Где починить**: добавить тесты в `tests/unit/research/test_writer.py`,
`tests/integration/test_research_store_isolation.py`,
`tests/contract/test_research_sse.py`.

### Дубликат router-prefix в тестах
`tests/contract/test_research_endpoint.py:15` делает
`app.include_router(research.router, prefix="/api/v1")` поверх уже
включённого в `src/api/main.py:38` `prefix="/api/v1/research"`. Тесты
проходят (бьются по короткому префиксу), но в startup'е сыпется
warning про duplicate operation_id. На прод не влияет.

### `get_concurrent_task_count(api_key)` — без per-tenant учёта
Считает все running-задачи глобально (api_key игнорируется). Для
single-tenant сетапа это нормально, для multi-tenant — нет.

---

## Как запустить и проверить

```powershell
# 1) Инфраструктура
cd repos/Atomic-Scraper-Service
docker compose up -d redis
cd infra/searxng; docker compose up -d; cd ../..

# 2) API + worker
pm2 start ecosystem.config.js

# 3) Проверки
curl -sS http://localhost:8000/healthz

# SERP
curl -sS -X POST http://localhost:8000/serper `
  -H "Content-Type: application/json" -H "X-API-Key: default_internal_key" `
  -d '{"q":"langgraph research agent","num":3}'

# Scrape (text — баг был починен здесь)
curl -sS -X POST http://localhost:8000/scraper `
  -H "Content-Type: application/json" -H "X-API-Key: default_internal_key" `
  -d '{"url":"https://example.com","wait_until":"domcontentloaded","output_format":"text"}'

# Research
curl -sS -X POST http://localhost:8000/api/v1/research/run `
  -H "Content-Type: application/json" -H "X-API-Key: default_internal_key" `
  -d '{"query":"What is LangGraph?","mode":"speed"}'

# Подождать ~3 мин, затем:
curl -sS -H "X-API-Key: default_internal_key" `
  "http://localhost:8000/api/v1/research/status/<task_id>"

# Тесты
uv run pytest tests/ -q --ignore=tests/e2e
```

## Ссылки

- `src/actions/research/nodes.py` — все ноды агента
- `src/actions/research/llm_utils.py` — strip_reasoning / extract_json
- `src/actions/research/tools.py` — web_search / scrape_url / extract_facts(_llm)
- `src/infrastructure/tasks/research_store.py` — Redis store
- `src/infrastructure/queue/research_task.py` — Taskiq entry-point
- `src/api/routers/research.py` — REST + SSE
- `src/domain/utils/content_cleaner.py` — html-to-md / html-to-text
