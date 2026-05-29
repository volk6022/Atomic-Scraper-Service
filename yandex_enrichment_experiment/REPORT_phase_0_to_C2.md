# REPORT: yandex_enrichment_experiment — фазы 0 → C-2

**Период:** 2026-05-25 — 2026-05-26
**Цель эксперимента:** прогнать research-агента по 316 организациям в 2-км радиусе вокруг 59°54'57"N 30°19'49"E (Гражданка/Полюстрово, СПб), получить для каждой ML/CV-релевантные ideas-карточки.

Этот документ — журнал того, что меняли, как замеряли и что показал audit. Использовать как baseline для следующей итерации (план: `~/.claude/plans/clever-meandering-sphinx.md`).

---

## Хронология изменений

### Phase setup (до экспериментов)

- 20 SOCKS5-прокси (puls-proxy) переведены в HTTP-режим (Chromium не умеет SOCKS5 с auth) — `proxies.txt`
- Redis на нестандартном порту 16379 (порт 6379 занят Hyper-V dynamic range) — `.env`
- LLM endpoint: `http://localhost:20022/v1/` (qwen3.5-9b-claude-4.6-opus-reasoning-distilled, Q4_K_S) — `.env`, `EXTRACTION_API_BASE` и `ORCHESTRATION_API_BASE`
- SearXNG-тюнинг: `SEARXNG_MIN_ORGANIC=3`, `SEARXNG_RETRY_DELAY=1.0`, `SEARXNG_MAX_RETRIES=2`, `SEARXNG_TIMEOUT=15.0`

### Эксперимент-скрипты (новые файлы)

- `01_scrape_yandex.py` — 25 категорий через `YandexMapsExtractAction`, haversine-фильтр по радиусу, idempotent кеш по категории. Результат: `data/organizations.json` (316 уникальных орг).
- `01b_dedup.py` — нормализация title, GENERIC_TITLE_PATTERNS для безбрендовых вывесок («Магазин продуктов», «Аптека» и т.п.) → `data/organizations_dedup.json`.
- `02_research_orgs.py` — асинхронный orchestrator: POST `/research/run` → polling `/status` каждые 20s → save `data/research/{oid}.json`. ENV: `LIMIT`, `OFFSET` (добавлен позже), `CONCURRENCY`.

### Фазы оптимизации (в порядке применения)

| Фаза | Что починили | Файлы |
|------|--------------|-------|
| **Singleton fix** | Каждый Action создавал свой `BrowserPoolManager()` вместо экспортируемого singleton'а → N Chromium процессов вместо 1+N контекстов | `src/actions/site_enricher.py:22`, `src/actions/yandex_maps.py:99,270` |
| **Round-robin proxy** | `random.choice` без sticky → коллизии по прокси при concurrent runs | `src/infrastructure/browser/proxy_provider.py:18-32` |
| **Parallel search** | Sequential `for gap in gaps[:3]: await web_search` → `asyncio.gather` + `Semaphore(2)` | `src/actions/research/nodes.py:158-200` |
| **LLM timeout** | Дефолтный 16s в OpenAI SDK → таймауты на plan_node → пустые gaps → пустой SERP. Поставлен `httpx.Timeout(120.0, connect=10.0)` | `src/infrastructure/external_api/clients/openai_client.py` |
| **Worker count** | TaskIQ `--workers 4` | `ecosystem.config.js:14` |
| **Phase A (instrumentation)** | Все `elapsed_ms` в `emit_node_event` были hardcoded literals (200, 300, 50). Заменено на `time.perf_counter()` deltas в 9 эмит-сайтах | `src/actions/research/nodes.py` |
| **Phase B (parallel extract_facts)** | `for doc in scraped_content: await extract_facts_llm(...)` (sequential N×10s) → `asyncio.gather` с `Semaphore(4)` | `src/actions/research/nodes.py` (extract_facts_node) |
| **Phase C (scrape timeout)** | `wait_until="networkidle", timeout=30000` зависал на JS-heavy сайтах → `wait_until="domcontentloaded", timeout=15000` для main, `10000` для about/services | `src/actions/site_enricher.py:45,57,72` |
| **Phase C-2 (proxy + locale)** | research-scrape ходил с локального IP без прокси (вопреки yandex_maps); добавлен `proxy_provider.get_proxy()` + `locale="ru-RU"`, `timezone_id="Europe/Moscow"` | `src/actions/site_enricher.py:21-37` |

### Прочие изменения окружения

- `.env`: `RATE_LIMIT_DEFAULT_PER_HOUR=100000` (был 1000, упёрлись), `MAX_CONCURRENT_RESEARCH_TASKS=10` (был 5, упёрлись при c=6)
- Redis FLUSHDB между прогонами (rate-limiter token bucket в Redis иногда блокировал на час)

---

## Throughput замеры

| Версия | Wall (10 orgs) | sec/org | Median facts | Median ans chars |
|---|---|---|---|---|
| LM Studio (single-stream) | 54 мин | 5.45 мин | ~39 | ~3400 |
| llama-server `-np 4 -cb` | 28 мин | 2.8 мин | ~39 | ~3400 |
| + Phase A + B | (smoke 1 org) | — | — | — |
| + Phase A + B + C | (smoke 1 org СОШ 307: 345s) | — | — | — |
| **+ Phase A + B + C + C-2** | **60 мин** | **6.0 мин** | **~76** | **~5300** |

**Ключевая регрессия по wall**: Phase C-2 удвоил per-task latency. Причина: больше iterations с реальным extract_facts работой (раньше scrape возвращал пусто → ноды отваливались за 0ms; теперь правда работают). Качество субъективно выросло, audit это **не подтвердил** (см. ниже).

**llama-server metrics (последний прогон):**
- `prompt_tokens_total` дельта: 150 018 / 60 мин = 41 t/s aggregate prompt processing
- `tokens_predicted_total` дельта: 131 428 / 60 мин = **36 t/s aggregate decode**
- `n_busy_slots_per_decode`: 2.05 → 2.35 (Phase B даёт прирост ширины батча)
- `requests_deferred`: 0 — слоты ни разу не насыщались (CONCURRENCY=4 < scrape-плечи)
- `predicted_tokens_seconds`: 15.6 t/s per-slot (single-stream bench показал 53 t/s, в реальной нагрузке батчи режут per-slot до 15-16)

---

## Audit-результат (8 ресёрчей через haiku-агентов)

Audited: orgs[0, 5, 10, 15, 20, 25, 30, 35] — каждый 5-й из первых 35 ресёрчей.

| # | Орг | Версия кода | Verdict | Score | Главная проблема |
|---|---|---|---|---|---|
| 0 | ABC (юр) | LM Studio baseline | REWRITE | 1/10 | US OCR boilerplate, не зашёл на abcadvocate.ru |
| 5 | Семишагофф | LM Studio baseline | NEEDS DEPTH | 5/10 | Нашёл основу + 7 fake citations (NetSuite, Shopify, Comarch) |
| 10 | Белорусские продукты | llama-server | REWRITE | 0/10 | **Не та компания** — researched Militzer&Münch (африканская логистика) |
| 15 | Flowers market | llama-server | REWRITE | 2/10 | Industrial-scale ML для 2-локационного флориста, не нашёл сайт/соц |
| 20 | Продукты (на Бронницкой) | c=6 sweep | HALLUCINATION | 3/10 | Не зашёл даже на 2GIS-карточку, generic retail boilerplate |
| 25 | Законное право | c=6 sweep | REWRITE | 2/10 | **urls_visited=0, facts=[], citations=[]** — чистый boilerplate |
| 30 | Fix Food | A+B+C smoke | HALLUCINATION | 1/10 | Drive-thru идеи для 30-местного аниме-кафе, fake citations к fasterlines.com |
| 35 | Агентство Номер Один | **A+B+C+C-2** | REWRITE | 1/10 | Источники: healthcare docs, GitHub crypto. Не нашёл юрист-услуги.рф |

**Сводка:**

| Verdict | Кол-во | % |
|---|---|---|
| REWRITE | 5 | 62% |
| HALLUCINATION | 2 | 25% |
| NEEDS DEPTH | 1 | 13% |
| GOOD | **0** | 0% |

**Тренды найденные audit'ом:**
- **0/8** нашли соцсети (VK, Telegram, Instagram)
- **0/8** нашли hh.ru / вакансии
- **1/8** нашёл сайт (Семишагофф частично — semishagoff.org)
- **0/8** использовали 2GIS / Yandex.Maps карточки как первичный источник
- **5/8** hallucination через несвязанные source (US legal tech, generic retail articles, healthcare docs)
- **Phase C-2 не помог качеству** — Агентство Номер Один (последний прогон) такой же мусор как ABC (первый, до всех оптимизаций)

**Главный вывод:** оптимизации throughput не транслировались в качество. Корневые проблемы:
1. Промпты позволяют уход в boilerplate (`answer_node` пишет generic ML/CV recommendations даже когда facts пустые)
2. plan_node генерирует длинные sub-questions → SearXNG возвращает 0 organic
3. `score=0.8` constant → URL-выбор фактически рандомный
4. Нет передачи контекста между нодами
5. 2GIS / Yandex.Maps reviews игнорируются полностью
6. Hard regression на graf: пустой scrape → answer_node всё равно генерит generic-выхлоп

---

## Состояние данных

`yandex_enrichment_experiment/data/research/` содержит ~37 JSON-ов:
- orgs[0:10] — LM Studio baseline (низкое качество)
- orgs[10:20] — llama-server без A/B/C (низкое качество)
- orgs[20], [21], [22], [23], [25] — c=6 sweep с rate-limit-cap'ом (несколько rewrite/hallucination)
- orgs[30] Fix Food — Phase A+B+C smoke (hallucination)
- orgs[31] СОШ 307 — Phase A+B+C smoke (5/6 scrape success, лучшее на этой итерации)
- orgs[32:42] — Phase A+B+C+C-2 (60 мин, 22.9% scrape success rate, audit показал что качество не выросло)

Все эти ресёрчи **подлежат пересборке** после следующей фазы (structured output + tool calling + ORG_CARD_SCHEMA + reviews в query). Старые JSON-ы оставлены для diff'а.

`yandex_enrichment_experiment/data/sweep/` — снепшоты `/metrics` до/после прогонов c=4 / c=6, raw timeseries.

---

## Кто я был, кто я стану

Сейчас research-агент — **free-form markdown writer** с фиктивным сортированием URL и слабыми JSON-парсерами. Цель следующей фазы — **schema-driven research agent**, где:
- caller передаёт `output_schema` (для эксперимента — ORG_CARD_SCHEMA: сайт(ы), соцсети, вакансии, контакты, отзывы с Я.Карт)
- caller передаёт `language` ("ru" в нашем кейсе, default "en")
- LLM генерирует только то, что в schema, отсутствие данных — empty array, не galлюцинация
- search queries формируются tool_call'ом с ограничением ≤5 слов
- URL-выбор — tool_call с reasons (никаких PDF и github crypto)
- context propagation между нодами через breadcrumbs

`/research` остаётся generalized — никаких org-specific промптов. Специфика — в `02_research_orgs.py` и в передаваемых через API параметрах.

---

## Открытые вопросы / следующие шаги

1. **Photo OCR** для 2GIS / Yandex.Maps карточек — отложено (нет дешёвой vLLM-инфраструктуры для image processing)
2. **Resume-matching post-agent** — отдельный план: после чистой ORG_CARD будет отдельный LLM-агент, имеющий доступ к KB пользователя, оценивающий fit
3. **Phase C-2 регрессия** — после новой схемы посмотреть, нужны ли прокси для site_enricher: возможно `language=ru` в SearXNG + ru system-prompts отдадут локальные сайты, которые scrape без прокси (нам не нужен прокси, мы и так в RU)
4. **Full 316 run** — только после re-audit ≥3/5 GOOD verdict на свежем sample
