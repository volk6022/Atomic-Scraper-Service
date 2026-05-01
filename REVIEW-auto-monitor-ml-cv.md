# Atomic-Scraper-Service — Readiness Review for `auto-monitor-ml-cv`

**Reviewer**: Claude (auto-monitor-ml-cv project)
**Date**: 2026-05-01
**Reviewed commit/state**: working tree at `C:\Users\bhunp\Documents\auto-monitor-ml-cv\repos\Atomic-Scraper-Service`
**Consumer project**: `auto-monitor-ml-cv` — ML/CV client-acquisition pipeline (см. `wiki/ml-cv-client-pipeline.md`, `.specify/memory/constitution.md` v1.0.0)

---

## TL;DR

Каркас годный (FastAPI + Playwright + Taskiq/Redis + MCP, разработан через Speckit), архитектурно чистый, но реализация наполовину «заглушечная». Для использования в наших US6 (Yandex Maps по геосетке СПб) и US7 (enrichment сайтов компаний) нужны доработки L-уровня в апстрим. Docker практически не готов. Локальный запуск через `uv` работает, MCP-сервер запускается через stdio.

**Вердикт**: «из коробки» сервис **НЕ годится** ни под US6, ни под US7. Перед интеграцией в наш пайплайн (фича 002+) необходима preparatory-итерация контрибьюшенов в upstream — оценка 13 пробелов с приоритезацией ниже.

---

## 1. Структура и стек

| Аспект | Значение |
|---|---|
| Язык | Python 3.11+ (`requires-python = ">=3.11"`, `.python-version`) |
| HTTP framework | FastAPI |
| Browser automation | Playwright 1.58 (`playwright = "^1.58.0"`) |
| Task queue | Taskiq + Redis 7 |
| MCP | fastmcp 3.1 (stdio) |
| LLM client | openai 2.28 |
| Package manager | uv (`uv.lock` коммитнут) |
| Process manager | PM2 (`ecosystem.config.js`) |
| Speckit | Да: `.specify/` + `specs/009-smart-scraping-llm-api/` |

**Слои**:
- `src/api/` — REST endpoints + WebSocket
- `src/domain/` — Pydantic-модели + DSL для интерактивных сессий
- `src/infrastructure/` — browser pool, queue, LLM client
- `src/actions/` — DSL handlers
- `src/mcp_server.py` — stdio MCP-сервер

**Точки входа**:
1. HTTP API: `uv run python -m src.api.main` (порт :8000)
2. Worker: `uv run taskiq worker src.infrastructure.queue.broker:broker src.infrastructure.queue.tasks`
3. MCP: `python -m src.mcp_server` (stdio)
4. PM2: `pm2 start ecosystem.config.js` запускает оба процесса (api + worker)

**Внимание**: `main.py` в корне репозитория — пустой stub.

---

## 2. Docker готовность

| Проверка | Статус | Деталь |
|---|---|---|
| Dockerfile | ❌ ОТСУТСТВУЕТ | `.dockerignore` ссылается на несуществующий `Dockerfile*` |
| docker-compose.yml | ⚠ МИНИМАЛЬНЫЙ | Поднимает только Redis. Нет api/worker/playwright-сервисов |
| Healthcheck в коде | ❌ НЕТ | В роутерах нет `/healthz` или `/health` |
| EXPOSE | — | (нет Dockerfile) |
| Volumes | — | (нет описания в compose для приложения) |

**Вывод**: prod-deploy требует написания Dockerfile с нуля (база `mcr.microsoft.com/playwright/python:v1.58`) и расширения compose с api+worker.

---

## 3. Локальный запуск через `uv` / npm

| Проверка | Статус | Деталь |
|---|---|---|
| `pyproject.toml` | ✅ | Корректный, deps зафиксированы |
| `uv.lock` | ✅ | Коммитнут — `uv sync` детерминирован |
| `.env.example` | ✅ | Минимальный, есть |
| README инструкция запуска | ⚠ ЧАСТИЧНО | Документирует через PM2; `uv run` не упомянут явно |
| Установка Playwright browsers | ❌ НЕ В README | Нужен `uv run playwright install chromium` |
| npm/Node-компоненты | — | Нет (Python-only сервис; n8n тут не задействован) |

**Минимальный путь локального запуска (для нашего MVP)**:
```bash
cd repos/Atomic-Scraper-Service
uv sync
uv run playwright install chromium
docker compose up -d redis        # либо нативный redis-server
cp .env.example .env              # заполнить ключи
uv run python -m src.api.main     # терминал 1
uv run taskiq worker src.infrastructure.queue.broker:broker src.infrastructure.queue.tasks  # терминал 2
```

---

## 4. API / MCP контракты

**REST endpoints** (из `src/api/routers/`):
- `/scraper` (stateless) — принимает URL + опционально DSL-actions, возвращает **сырой HTML** из `page.content()`.
- `/jina-extract` — дёргает `extraction_client.extract(...)` (см. пробелы ниже).
- DSL-сессии для интерактивных сценариев.

**MCP tools** (из `src/mcp_server.py`):
- Аналогичные scrape/session инструменты, экспонированные через fastmcp 3.1.

**Что принимает на входе**:
- Произвольный URL ✅
- DSL-операции (goto, click, scroll, click_coord) ✅
- Селекторы CSS — через DSL ✅
- Конфиг под конкретный таргет (Я.Карты) — ❌ нет

**Что возвращает**:
- Raw HTML — да
- Структурированный JSON — только для DSL-результатов (зависит от actions)
- Markdown / clean text — ❌ нет

**Rate-limit / concurrency**:
- Concurrency — через Taskiq workers ✅
- Per-domain rate-limit — ❌ нет (нужен middleware с token-bucket в Redis)

---

## 5. Anti-bot / stealth

| Проверка | Статус | Деталь |
|---|---|---|
| playwright-stealth / patchright | ❌ НЕТ | `BrowserPoolManager` запускает чистый `chromium.launch(headless=True)` |
| User-Agent rotation | ❌ НЕТ | Хардкод дефолтного UA Playwright |
| Human emulation (mouse jitter, typing delays) | ❌ НЕТ | DSL поддерживает только примитивные клики/скроллы |
| Proxy rotation | ⚠ ЧАСТИЧНО | `proxy_provider.py` читает `proxies.txt`, но **не интегрирован** в `pool_manager.create_context` — proxy подаётся только если клиент явно передаст в `request.proxy` |
| Retry на бан-ответы | ❌ НЕТ | Нет специальной логики для 429/блокировок |

**Вывод**: Я.Карты, LinkedIn, Habr Freelance забанят сервис в течение нескольких минут.

---

## 6. Тесты и качество

| Аспект | Статус |
|---|---|
| pytest каркас | ✅ `tests/{contract,integration,unit}` + `conftest.py` |
| pytest-asyncio | ✅ |
| ruff | ✅ в deps |
| Реальное покрытие | ⚠ ПОВЕРХНОСТНОЕ (~12 тестовых файлов) |
| Integration-тесты против реальных сайтов | ❌ НЕТ |
| CI (`.github/workflows`) | ❌ ОТСУТСТВУЕТ |

---

## 7. Готовность к US6 (Yandex Maps по геосетке СПб)

**Что нужно от сервиса**: принять (категория, центр, радиус) → вернуть список карточек с name/address/phone/website/geo, обходя anti-bot защиту Я.Карт, ≤30 запросов/час без прокси.

**Пробелы**:
1. Нет stealth — забанят (см. §5).
2. Нет специализированного экстрактора Я.Карт: DSL не знает о виджетах карты, карточках организаций, пагинации скроллом.
3. Нет per-domain rate-limit (требование constitution 30 req/h к `*.yandex.*`).
4. Proxy не интегрирован в pool — даже если положить `proxies.txt`, Я.Карты будут из одного IP.

**Можно ли «из коробки»**: ❌ нет.

---

## 8. Готовность к US7 (enrichment сайтов компаний)

**Что нужно от сервиса**: для каждого URL выкачать главную + 1-2 страницы (about/services), вернуть очищенный текст ≤500 слов для последующей персонализации холодных писем.

**Пробелы**:
1. `/scraper` отдаёт сырой HTML — нет text-cleanup, нет markdown-конвертации (trafilatura/readability), нет truncate до 500 слов.
2. `jina_client.py` упомянут в `STRUCTURE.md`, но **физически отсутствует** в `src/infrastructure/external_api/`. Реальные файлы там: `openai_client.py`, `facade.py`, `search_client.py`. `/jina-extract` дёргает `extraction_client.extract(...)` — метод не определён.
3. Нет crawl-логики «главная + about/services» — только одиночный URL.
4. Нет дедупликации по домену.
5. Нет respect для robots.txt.

**Можно ли «из коробки»**: ❌ нет, требуется новый action `site_enricher`.

---

## 9. Speckit

✅ Да, проект разработан через Speckit:
- `.specify/{memory, scripts, templates, extensions}` присутствует
- `specs/009-smart-scraping-llm-api/{spec, plan, tasks, data-model, contracts/{rest,websocket}, research, quickstart, checklists}` — полный Speckit-набор для текущей фичи
- `.opencode/command/speckit.*.md` — slash-commands для opencode

**Следствие для нашего контрибьюшена**: PR должны идти через тот же Speckit-flow (`/speckit.specify` → `/speckit.plan` → `/speckit.tasks` → `/speckit.implement`), что совместимо с нашей `auto-monitor-ml-cv` constitution v1.0.0.

---

## 10. Список рекомендованных контрибьюшенов в upstream

Приоритезация под наш MVP roadmap (фича 002 = Yandex+enrichment+n8n+HH+Telegram).

| # | Задача | Файл / новый модуль | Сложность | Use-case | Прио |
|---|---|---|---|---|---|
| 1 | Stealth-режим браузера (playwright-stealth или patchright) + UA-rotation + human emulation | `src/infrastructure/browser/pool_manager.py`, новый `stealth_pool.py` | L | US6, US7 | P0 |
| 2 | Yandex Maps action: bbox/center+radius+category → список карточек | новый `src/actions/yandex_maps.py` + endpoint `/scrape/yandex-maps` | L | US6 | P0 |
| 3 | Dockerfile (база `mcr.microsoft.com/playwright/python:v1.58`) | новый `Dockerfile` | M | prod-deploy | P0 |
| 4 | Расширение `docker-compose.yml`: api + worker + redis + healthcheck | `docker-compose.yml` | M | prod-deploy | P0 |
| 5 | `/healthz` endpoint | новый `src/api/routers/health.py` | S | docker healthcheck | P0 |
| 6 | Site enricher: crawl главная + about/services, html→text (trafilatura/readability), truncate ≤500 слов | новый `src/actions/site_enricher.py` + endpoint | M | US7 | P1 |
| 7 | Реализация `jina_client.py` / `extraction_client` (либо удаление упоминаний, если не нужно) | `src/infrastructure/external_api/jina_client.py` | M | US7 | P1 |
| 8 | Per-domain rate-limiter (token bucket в Redis), дефолт 30/h для `*.yandex.*` | новый middleware | S | US6 ToS | P1 |
| 9 | Интеграция `proxy_provider` в `pool_manager.create_context` (а не только через явный `request.proxy`) | `src/infrastructure/browser/pool_manager.py` | S | US6 | P1 |
| 10 | Реальный `search_client` (Serper API или DuckDuckGo HTML) вместо мока «example.com» | `src/infrastructure/external_api/search_client.py` | M | US6 опц. | P2 |
| 11 | Bump `requires-python` до `>=3.12` (или согласовать downgrade у нас до 3.11) | `pyproject.toml` | S | совместимость | P2 |
| 12 | GitHub Actions CI: `uv sync` + `pytest` + `ruff check` | новый `.github/workflows/ci.yml` | S | качество | P2 |
| 13 | Документация `uv run` запуска + `playwright install chromium` в README | `README.md` | S | DX | P2 |

**Итого**: 5 задач P0, 4 задачи P1, 4 задачи P2.

---

## 11. Ключевые файлы для изучения

```
repos/Atomic-Scraper-Service/
├── pyproject.toml                              # Python 3.11+, uv-managed
├── uv.lock
├── docker-compose.yml                          # ⚠ только Redis
├── ecosystem.config.js                         # PM2: api + worker
├── .env.example
├── README.md
├── STRUCTURE.md                                # ⚠ упоминает несуществующие модули
├── main.py                                     # ⚠ пустой stub
├── src/
│   ├── api/
│   │   ├── main.py                             # FastAPI app entry
│   │   └── routers/
│   │       └── stateless.py                    # ⚠ возвращает raw HTML
│   ├── infrastructure/
│   │   ├── browser/
│   │   │   ├── pool_manager.py                 # ⚠ без stealth
│   │   │   └── proxy_provider.py               # ⚠ не интегрирован
│   │   └── external_api/
│   │       ├── openai_client.py
│   │       ├── facade.py
│   │       └── search_client.py                # ⚠ возвращает мок
│   ├── domain/                                 # Pydantic + DSL
│   ├── actions/                                # DSL handlers
│   └── mcp_server.py                           # fastmcp stdio
├── tests/{contract,integration,unit}/          # ⚠ поверхностное покрытие
├── specs/009-smart-scraping-llm-api/           # Speckit feature (предыдущая итерация)
└── .specify/                                   # Speckit infrastructure
```

---

## 12. Рекомендованный план интеграции в `auto-monitor-ml-cv`

**Не трогаем фичу 001** (`001-mvp-lead-outreach`) — она использует только 2GIS API и Atomic-Scraper не требует. ✅

**Перед фичей 003** (multi-source collectors с Я.Картами/enrichment) запустить отдельную preparatory-фичу:

```
/speckit-specify atomic-scraper readiness for ml-cv pipeline
  (Docker + Yandex Maps stealth + site enrichment)
```

Структура preparatory-фичи (черновик):
- **US1 (P1)**: Docker readiness — задачи #3, #4, #5
- **US2 (P1)**: Stealth + per-domain rate-limit — задачи #1, #8, #9
- **US3 (P1)**: Yandex Maps extractor — задача #2
- **US4 (P2)**: Site enricher + text cleanup — задачи #6, #7
- **US5 (P3)**: Real search client + CI + docs — задачи #10, #12, #13
- **US6 (P3)**: Python version alignment — задача #11

**Дорожки контрибьюшена**:
1. Upstream PR в `volk6022/Atomic-Scraper-Service` для каждого P0/P1 — через Speckit-flow проекта.
2. Локальный fork в `repos/Atomic-Scraper-Service` (можем держать наш ветку до merge upstream).
3. Интеграционный код-клиент в нашем `src/auto_monitor/enrichment/` — фича 003.

---

## 13. Open questions для апстрима

1. Готов ли maintainer (`volk6022`) принимать PR по Yandex Maps action и stealth-режиму? — нужно открыть discussion перед PR.
2. Какая рекомендованная база для Dockerfile: `playwright/python` или `python:3.12-slim` + ручная установка browsers?
3. Лицензия неизвестна без проверки `LICENSE` файла — для коммерческого использования в нашем пайплайне нужно подтвердить совместимость.

---

**Конец отчёта.**
