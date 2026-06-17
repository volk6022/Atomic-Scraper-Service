# Atomic Scraper Service

PROJECT_SIZE: БОЛЬШОЙ (52 файла с кодом в `/src`, исключая `__init__.py` и тесты)
ДОМЕН: Backend | Автоматизация | AI-Агенты
СТЕК: Python 3.12, FastAPI, Playwright, Redis, Taskiq, LangGraph, OpenAI API, Docker, playwright-stealth, markdownify
КЛЮЧЕВЫЕ ТЕГИ ДЛЯ РЕЗЮМЕ: Web Scraping, Browser Automation, FastAPI, AI Agent, LangGraph

---

## Что делает проект

Сервис автоматически собирает структурированные бизнес-данные из интернета (Яндекс.Карты, произвольные сайты, Google) и запускает AI-агента для глубокого автономного исследования тем — заменяя дни ручного сбора данных несколькими минутами автоматической обработки.

Дополнительно: обходит anti-bot защиты (Yandex SmartCaptcha, Cloudflare) через пул стелс-браузеров с ротацией прокси и эмуляцией человеческого поведения; поддерживает интерактивные браузерные сессии по WebSocket-команды через DSL.

---

## Проблема и решение

### Контекст и проблема

Компании, занимающиеся продажами или аналитикой рынка, регулярно сталкиваются с задачей: найти и структурировать данные о тысячах организаций из Яндекс.Карт (название, адрес, телефон, сайт, координаты, отзывы), обогатить эти данные текстом с сайтов компаний, а затем провести исследование по каждой. Вручную это занимает несколько дней работы аналитика на каждые несколько сотен организаций. Главный барьер — современные сайты активно блокируют скрейперов: Яндекс применяет SmartCaptcha и детектирование headless-браузеров, при этом требует прокси жилого класса (datacenter IP блокируются мгновенно).

Отдельная проблема для исследователей — разрозненность: чтобы получить ответ на сложный вопрос («какие компании занимаются промышленной автоматизацией в Поволжье?»), нужно вручную искать, открывать десятки страниц, извлекать факты и синтезировать отчёт. Без инструмента это 2–4 часа на один запрос.

### Решение

Atomic Scraper Service — единый HTTP-сервис (FastAPI), который предоставляет несколько специализированных эндпоинтов:

- **`/yandex-maps/extract`** — перехватывает XHR-ответы Яндекс.Карт через браузер-прокси с residential IP и возвращает структурированный список организаций (65+ полей на каждую)
- **`/enrich`** — берёт URL сайта компании и возвращает чистый структурированный текст (главная + страницы «О нас» и «Услуги», максимум 500 слов)
- **`/serper`** — Serper-совместимый Google Search через stealth Playwright (без API-ключей Google)
- **`/research/run`** — LangGraph-агент, который автономно планирует подзапросы, ищет, скрейпит, извлекает факты и синтезирует структурированный отчёт в 3 режимах (`speed` / `balanced` / `quality`)
- **`/sessions`** + **WebSocket DSL** — интерактивные сессии браузера для сложных сценариев автоматизации

### Измеримый результат

- Производительность: Redis-based rate limiting с token bucket — 30 req/hour для `*.yandex.*`, 1000/hour для остальных доменов, горизонтально масштабируется через worker-процессы Taskiq
- Масштаб: 194 автоматических теста (unit / contract / integration / e2e), ~4 700 строк продакшн-кода
- Экономия времени: Research Agent в режиме `speed` (2 итерации) против `quality` (25 итераций + reflection-цикл) — [NEEDS VERIFICATION по реальному времени задач]
- Точность Yandex Maps extraction: поддерживает 65+ полей на организацию включая координаты и отзывы — [NEEDS VERIFICATION по % успешных извлечений]

---

## Технический стек

### Языки и фреймворки

| Компонент | Технология | Зачем |
|-----------|-----------|-------|
| REST API | FastAPI 0.135+ | Асинхронный HTTP-сервер, Pydantic-валидация |
| Браузерная автоматизация | Playwright 1.58 + playwright-stealth 2.0 | Headless Chromium с обходом bot-detection |
| Task Queue | Taskiq 0.12 + taskiq-redis 1.2 | Фоновые задачи (Research Agent, сессии) |
| AI-граф | LangGraph 0.3 + LangChain-OpenAI 0.3 | State machine для исследовательского агента |
| LLM-клиент | OpenAI SDK (OpenAI-compatible API) | Orchestration (GPT-4o) + Extraction (Jina Reader) |
| Очередь / Pub/Sub | Redis 7 | Task broker + координация WebSocket-сессий |
| HTML → текст | markdownify 1.2 | Конвертация страниц в чистый Markdown |
| Веб-сервер | Uvicorn 0.30 | ASGI-сервер |
| HTTP-клиент | httpx 0.28 | Async HTTP для внешних запросов |

### Инфраструктура и деплой

Docker Compose: три сервиса — `redis` (Redis 7 alpine), `api` (FastAPI + Playwright), `worker` (Taskiq background worker). Базовый образ — `mcr.microsoft.com/playwright/python:v1.58.0` (включает Chromium + все системные зависимости). Healthcheck для каждого сервиса. Монтируется `proxies.txt` в read-only режиме. PM2 поддерживается через `ecosystem.config.js`.

### Внешние интеграции

| Интеграция | Тип | Назначение |
|-----------|-----|-----------|
| OpenAI API (или совместимые) | LLM Orchestration | Reasoning, planning в Research Agent |
| LM Studio / Jina Reader v2 | LLM Extraction | Структурированное извлечение контента из HTML |
| Яндекс.Карты | Web Service | Бизнес-данные через XHR-перехват |
| SearXNG (self-hosted, опционально) | Metasearch | Альтернативный Google-поиск без API-ключей |
| Redis | Queue + Pub/Sub | Taskiq broker + координация сессий |
| Residential proxies | HTTP proxy | Обход geo-block и anti-bot для yandex.ru |

---

## Архитектура

### Компоненты системы

```
┌───────────────────────────────────────────────────────────────────┐
│  Presentation Layer: FastAPI REST API + WebSocket + MCP Server    │
│  /scraper  /serper  /enrich  /yandex-maps  /research  /sessions  │
└──────────────────────┬────────────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────────────┐
│  Domain Layer: Pydantic models, DSL, Action Registry              │
│  CommandType enum → action_registry → function pointer            │
└──────────────────────┬────────────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────────────┐
│  Actions Layer: DSL command implementations                        │
│  navigation.py │ interaction.py │ extraction.py                   │
│  yandex_maps.py │ site_enricher.py │ research/ (LangGraph)        │
└──────────────────────┬────────────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────────────┐
│  Infrastructure Layer                                              │
│  browser/: pool_manager, stealth_pool, user_agent_pool, proxy     │
│  queue/: broker, session_actor, research_task, cleanup_worker     │
│  external_api/: facade, openai_client, search_client              │
│  rate_limiter/: token_bucket (Redis)                              │
└──────────────────────┬────────────────────────────────────────────┘
                       │
               ┌───────▼────────┐
               │  Redis (Queue  │
               │  + Pub/Sub +   │
               │  Rate Limit)   │
               └────────────────┘
```

### Ключевые алгоритмы и паттерны

**LangGraph Research Agent (State Machine с Reflection Loop):**

```
classify → plan → search → rank_dedupe → scrape → extract_facts → reflect
                    ↑_____________________________________|  (если gaps остались)
                                                          ↓
                                                       answer → writer
```

Агент поддерживает 3 режима: `speed` (2 итерации, быстро), `balanced` (6 итераций), `quality` (25 итераций + stall-detection). Stall detection: если за 2 подряд итерации новых фактов не появилось — досрочный выход.

**Token Bucket Rate Limiter (Redis):** Per-domain правила через fnmatch-паттерны. `*.yandex.*` = 30 req/hour, по умолчанию 1000 req/hour. Middleware перехватывает все запросы до обработчика.

**Anti-Bot Evasion:** `playwright-stealth` отключает headless-индикаторы. Human Emulator генерирует случайные движения мыши (5–15 шагов с jitter), задержки при печати (50–150ms), random-scroll. Ротация User-Agent из пула реальных браузерных строк.

**Actor Model (Taskiq):** Каждая browser-сессия = отдельный Taskiq-task (SessionActor). Получает DSL-команды через Redis Pub/Sub. Автоматическое закрытие через 10 минут неактивности. Не требует постоянного WebSocket-соединения.

**Yandex Maps XHR Interception:** Браузер загружает страницу Яндекс.Карт, перехватывает XHR `/maps/api/search`, парсит JSON-ответы через несколько fallback-путей (`data.items`, `items`, `data.geo.items`). Фильтрует только бизнес-объекты (oid/permalink/seoname).

**Dual LLM Strategy:** два отдельных клиента с разными моделями — Extraction (Jina Reader / LM Studio, оптимизирован для структурирования HTML) и Orchestration (GPT-4o или аналог, для reasoning и планирования). Клиенты OpenAI-compatible, модели взаимозаменяемы.

### Поток данных

```
[HTTP Request]
      ↓
[Auth Middleware: X-API-Key]
      ↓
[Rate Limit Middleware: Redis token bucket]
      ↓
[FastAPI Router]
      ↓
[Action: yandex_maps / site_enricher / research / stateless]
      ↓
[BrowserPoolManager] ← [StealtPool + UserAgentPool + ProxyProvider]
      ↓
[Playwright Page: goto / intercept XHR / screenshot / extract]
      ↓
[ContentCleaner: strip noise → HTML→text/markdown → truncate 500w]
      ↓
[LLM Facade] (если нужно структурировать)
      ↓
[JSON Response]
```

Для Research Agent поток асинхронный: POST → 202 Accepted + task_id → GET /status/{id} (polling) → результат из Redis.

---

## Метрики кода

| Показатель | Значение |
|-----------|---------|
| Файлов с кодом (в `/src`, без `__init__.py`) | 52 |
| Строк кода в `/src` | ~4 700 |
| Строк тестового кода | ~5 800 |
| Всего тестов | 194 (unit / contract / integration / e2e) |
| Наличие тестов | Да (полная иерархия) |
| Покрытие тестами | ~75–80% (22 теста не проходят из-за отсутствия `X-API-Key`) |
| Тип архитектуры | Многослойный монолит + Queue-based background tasks |
| Документация | README + STRUCTURE.md + AGENTS.md + 5 спецификаций в `specs/` |
| CI/CD | Нет |

---

## Бизнес-ценность и целевые клиенты

### Кому это нужно

**Отделы продаж и лидогенерации (B2B, СМБ):** компании, которые строят базы потенциальных клиентов из Яндекс.Карт по категориям («кафе в Казани», «автосервисы в Новосибирске»). Без инструмента — ручной сбор через парсер Excel или дорогие SaaS (2ГИС API, Контур.Компас).

**Аналитики данных и маркетологи:** обогащение CRM-базы текстом с сайтов компаний для последующей сегментации или передачи в LLM-пайплайн персонализации.

**Исследователи и консультанты:** автономный агент закрывает потребность в глубоком исследовании темы без ручного поиска — 3 режима под разные требования к глубине.

**Разработчики, строящие AI-агентов:** MCP-сервер позволяет Claude Desktop использовать все инструменты сервиса напрямую без доп. интеграции.

### Боль, которую закрывает

Раньше: аналитик тратил полдня на сбор 200 организаций из Яндекс.Карт вручную, ещё день — на обогащение сайтов текстом, ещё 2–3 часа — на исследовательский отчёт по теме. Итого 2–3 дня рутинной работы. Сервис покрывает все три задачи через HTTP API, доступный из любого скрипта или n8n-пайплайна.

### Альтернативы на рынке

| Альтернатива | Ограничение |
|-------------|-------------|
| 2ГИС API / Контур | Платные, лицензионные ограничения, нет кастомизации |
| Apify / Bright Data | Дорого ($100+/мес), нет Research Agent, нет кастомного DSL |
| Ручной сбор | Медленно, не масштабируется, требует человека |
| Простые скрейперы (Scrapy, requests+BS4) | Блокируются anti-bot без доп. инфры |

### Потенциальный ROI

Типичный сценарий B2B: лидогенерация 1 000 организаций из Яндекс.Карт — при ручном сборе 8–12 часов работы аналитика. С сервисом — [NEEDS VERIFICATION по реальному времени задачи, оценочно 30–60 минут]. Экономия при ставке аналитика 1 500 ₽/час = 10 500–16 500 ₽ на одну кампанию.

---

## Формулировки для резюме

### Bullet points для резюме

- Разработал production-ready web scraping сервис на FastAPI + Playwright с anti-bot evasion (stealth browser, residential proxy rotation, human emulation), обеспечив извлечение 65+ полей бизнес-данных из Яндекс.Карт через XHR-перехват
- Реализовал LangGraph-агента автономного исследования с reflection-циклом (plan → search → scrape → extract → reflect), поддерживающего 3 режима глубины (speed / balanced / quality) и stall-detection для предотвращения бесконечных итераций
- Спроектировал многослойную архитектуру (Presentation / Domain / Infrastructure / Actions) с Redis-based token bucket rate limiting (per-domain правила через fnmatch), Taskiq task queue и Actor Model для stateful browser-сессий
- Автоматизировал сбор и структурирование бизнес-данных из веба через 6 REST-эндпоинтов + WebSocket DSL + MCP Server для Claude Desktop, покрыв 194 автоматическими тестами (unit / contract / integration / e2e)
- Реализовал dual-LLM стратегию: отдельные клиенты для extraction (Jina Reader LM) и orchestration (GPT-4o), оба через OpenAI-compatible API с возможностью замены модели без изменения кода
- Настроил Docker Compose инфраструктуру (API + Taskiq worker + Redis) с healthcheck, read-only proxy mount и Playwright в базовом образе Microsoft

### Короткое описание для секции «Проекты»

**Atomic Scraper Service** — высоконагруженный сервис автоматизированного сбора и структурирования веб-данных с AI-оркестрацией: извлечение бизнес-данных из Яндекс.Карт, обогащение сайтов компаний текстом и автономный LangGraph-агент для deep research. Стек: Python 3.12, FastAPI, Playwright, Redis, Taskiq, LangGraph. Ключевое достижение: обход anti-bot защит (stealth browser + residential proxy + human emulation) без дополнительных SaaS-сервисов.

### Кейс для портфолио

ПРОБЛЕМА: Аналитики данных и отделы продаж тратят дни на ручной сбор организаций из Яндекс.Карт и обогащение данных с сайтов компаний — современные anti-bot системы блокируют простые скрейперы, а коммерческие API (2ГИС, Контур) стоят от $100/мес с лицензионными ограничениями.

РЕШЕНИЕ: Разработан микросервис с API на FastAPI, который автоматизирует весь пайплайн: извлечение структурированных бизнес-данных из Яндекс.Карт через XHR-перехват в stealth-браузере, обогащение сайтов компаний чистым текстом через markdownify, поиск в Google без API-ключей, плюс автономный LangGraph Research Agent с reflection-циклом для синтеза исследовательских отчётов.

РЕЗУЛЬТАТ: 6 REST-эндпоинтов + WebSocket DSL + MCP Server для Claude Desktop; 194 автоматических теста; per-domain rate limiting через Redis token bucket; Docker-деплой с тремя сервисами (API, Taskiq worker, Redis); поддержка residential proxies и ротации User-Agent для обхода bot-detection.

---

## Демонстрируемые навыки

| Категория | Навыки |
|-----------|-------|
| Языки | Python 3.12, asyncio/await |
| AI / LLM | LangGraph, LangChain, OpenAI API, prompt engineering, structured output |
| Бэкенд | FastAPI, Pydantic, WebSocket, SSE, MCP (Model Context Protocol) |
| Браузерная автоматизация | Playwright, playwright-stealth, XHR interception, human emulation |
| Очереди задач | Taskiq, Redis Broker, Actor Model, Pub/Sub |
| Базы данных / Кэш | Redis (token bucket, Pub/Sub, task state) |
| Инфраструктура | Docker, Docker Compose, Dockerfile (playwright base image) |
| Тестирование | pytest, pytest-asyncio, unit / contract / integration / e2e |
| Паттерны | Clean Architecture, Layered Architecture, Actor Model, State Machine, Facade, Registry |
| Инструменты | uv (package manager), ruff (linter), markdownify |

### Hard skills (для ATS-систем)

Python, FastAPI, Playwright, Redis, Docker, LangGraph, LangChain, OpenAI API, asyncio, Taskiq, Pydantic, pytest, Web Scraping, Browser Automation, REST API, WebSocket, MCP, AI Agent, LLM Integration, Rate Limiting, Token Bucket

### Soft skills и подходы, видные из кода

- **Structured testing** (194 тестов в 4 уровнях) → TDD-подход и зрелость к quality assurance
- **Clean Architecture + Layered design** → опыт проектирования масштабируемых систем
- **Specs-driven development** (5 детальных спецификаций в `specs/`) → документирование требований до реализации
- **Dual LLM strategy** → понимание trade-off между моделями (cost vs quality)
- **Docker + health checks** → DevOps практики и production mindset

---

## Ограничения и зоны роста

- **Нет CI/CD**: отсутствуют GitHub Actions — тесты запускаются только локально, нет автоматической проверки при пуше
- **Незавершённые фичи (spec 013)**: `/serper` (реальный Google Search через Playwright) и Research Agent Taskiq wiring находятся на ~70% готовности; 22 теста из 194 не проходят из-за отсутствия `X-API-Key` заголовков в старых тестах
- **Нет docstrings**: большинство публичных функций и классов без документации — осложняет IDE-подсказки и onboarding новых разработчиков
- **GPU / residential proxies обязательны для Yandex**: без качественных residential proxy Яндекс блокирует datacenter IP, что создаёт внешнюю зависимость для полной функциональности
- **Session timeout захардкожен**: 10 минут неактивности — нет per-session конфигурации
- **Масштабируемость браузер-пула**: единственный глобальный процесс Chromium — горизонтальное масштабирование требует запуска нескольких инстансов всего сервиса (Docker Compose replicas), а не просто worker'ов
- **Research Agent без стриминга прогресса**: результат доступен только по completion, нет SSE-стриминга промежуточных шагов (заявлено в spec 013 как planned)
