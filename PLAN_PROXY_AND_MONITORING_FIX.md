# План: SOCKS5-proxy через локальный конвертер + progress-tracking для Research Agent

Дата: 2026-05-25
Автор плана: ассистент (по результатам ревью двух sub-агентов)

> **Не применять до явного апрува.** Это план фиксов после боевых тестов.

---

## 1. Где сейчас используются прокси (аудит endpoints)

| Endpoint | Источник прокси | Идёт ли через `proxies.txt` |
|----------|-----------------|------------------------------|
| `POST /api/v1/yandex-maps/extract` | `proxy_provider.get_proxy()` (auto) | **Да** (но см. баг ниже) |
| `POST /api/v1/yandex-maps/reviews` | `proxy_provider.get_proxy()` (auto) | **Да** |
| `POST /scraper` | `request.proxy` от клиента | Нет (если клиент не передал) |
| `POST /sessions` + WS `/ws/{id}` | `request.proxy` от клиента | Нет |
| `POST /api/v1/enrich` (`SiteEnrichAction`) | **Не передаётся** (`pool_manager.create_context(user_agent=..., stealth=True)` без `proxy=...`) | **Нет** ❌ |
| `POST /api/v1/research/run` → `web_search` | SearXNG (свой пул прокси) | Косвенно через SearXNG |
| `POST /api/v1/research/run` → `scrape_url` | `SiteEnrichAction` (то же что `/enrich`) | **Нет** ❌ |
| `POST /serper` | SearXNG | Косвенно через SearXNG |
| `POST /omni-parse`, `/html-to-md` | — (нет HTTP-выхода) | N/A |

**Принципиальный вывод:**

- Yandex Maps **должен** работать через `proxies.txt` (auto), но из-за бага SOCKS5+Chromium не работает (Chromium не поддерживает SOCKS5 auth — см. comment в [proxy_provider.py:21](src/infrastructure/browser/proxy_provider.py:21)).
- `SiteEnrichAction` (используется и в `/enrich`, и внутри research-агента) **не получает прокси вообще** — `pool_manager.create_context(...)` вызывается без `proxy=...`. Это значит, что research-агент скрейпит конечные сайты с DC IP сервера.

---

## 2. Yandex Maps — Вариант C: локальный HTTP→SOCKS5 конвертер

### Цель

Запустить локально HTTP-прокси, который принимает HTTP CONNECT/обычные запросы и пересылает их в апстрим SOCKS5 (с аутентификацией). Тогда Chromium через Playwright цепляется к локальному HTTP-прокси (без auth), а тот делает работу с SOCKS5+auth.

### Архитектура

```
Chromium (Playwright) ─HTTP─► localhost:18080 (gost-proxy)
                                     │
                                     └─SOCKS5+auth─► np.puls-proxy.com:11000-11019
```

### Реализация

**Вариант C.1 — Docker-контейнер с `gost`:**

```bash
# Один контейнер на каждый upstream порт, или один gost с пулом
docker run -d --name gost-proxy \
  -p 18080:18080 \
  ginuerzh/gost \
  -L=http://:18080 \
  -F=socks5://efea0cd216087051c2e6__cr.ru%3Bsessttl.10:fc6a3125b4c606fa@np.puls-proxy.com:11000
```

(Точку с запятой в username нужно URL-encode как `%3B`.)

**Вариант C.2 — Несколько локальных HTTP-прокси (один на каждый upstream порт):**

Запустить `gost` с 20 listener'ами или 20 контейнеров. Сохранить адреса в `proxies.txt` как:

```
http://localhost:18000
http://localhost:18001
...
http://localhost:18019
```

`proxy_provider` тогда работает без правок (фильтр `startswith("http://")` пропускает всё).

### Изменения в коде

1. `proxy_provider.py:18-30` — оставить как есть (фильтр на http:// уже верный).
2. `pool_manager.py:36-38, 57-58, 74-75` — без изменений.
3. Добавить compose-сервис `gost-proxy` в `docker-compose.yml`.
4. `proxies.txt` — заменить на локальные адреса.

### Стоимость

- Один контейнер, ~5MB RAM, ~1ms overhead per request.
- Один failure point вместо 20 — но проще диагностировать.

---

## 3. Site Enricher — пробросить прокси в research-агент

[site_enricher.py:35-37](src/actions/site_enricher.py:35) сейчас:

```python
context = await self.pool_manager.create_context(
    user_agent=user_agent, stealth=True
)
```

Добавить:

```python
from src.infrastructure.browser.proxy_provider import proxy_provider

proxy = proxy_provider.get_proxy() or None
context = await self.pool_manager.create_context(
    user_agent=user_agent, stealth=True, proxy=proxy
)
```

Это автоматически закроет дыру и для `/enrich`, и для research-агента (`scrape_url` -> `SiteEnrichAction`).

---

## 4. Research Agent — progress-tracking через `graph.astream()`

### Проблема (см. отчёт sub-агента)

[research_task.py:36-38](src/infrastructure/queue/research_task.py:36) вызывает `set_task(...)` только **после** `graph.ainvoke()`. Во время выполнения Redis не обновляется → `/status` всегда показывает `phase:"starting"`, `iteration:0`. Финальный результат при этом приходит корректно.

### Фикс

Заменить `await graph.ainvoke(initial_state, config=...)` на `astream` с записью между узлами:

```python
final_state = None
async for chunk in graph.astream(initial_state, config={"configurable": {"thread_id": task_id}}):
    for node_name, node_state in chunk.items():
        set_task(task_id, {
            "phase": node_name,
            "iteration": node_state.get("iteration", 0),
            "updated_at": _now_iso(),
        })
        final_state = node_state

# После цикла — записать финальный результат как сейчас
set_task(task_id, {
    "status": "completed",
    "result": final_state.get("final_report"),
    "updated_at": _now_iso(),
})
```

### Файл / строки

- `src/infrastructure/queue/research_task.py:30-50` — заменить блок `ainvoke` на цикл `astream`.

---

## 5. Порядок применения (после боевых тестов)

1. **(Перед фиксами)** Прогнать эксперимент `yandex_enrichment_experiment` на HTTP-прокси из `proxies.txt` (текущая замена SOCKS5→HTTP — проверить, поддерживает ли puls-proxy HTTP на тех же портах).
2. Если шаг 1 успешен с прямой HTTP-схемой → вариант C не нужен; оставить как есть.
3. Если puls-proxy НЕ держит HTTP на 11000-11019 → реализовать вариант C (gost).
4. Применить фикс site_enricher (раздел 3).
5. Применить фикс progress-tracking (раздел 4).
6. Прогнать smoke-тест: `/api/v1/research/run` → poll `/status` каждые 5s, убедиться что `phase` меняется.

---

## 6. Research Agent на слабом LLM — корневая причина пустых отчётов

**Эмпирика (smoke 3 орг в quality mode):**
- LLM `qwen3.5-9b-claude-4.6-opus-reasoning-distilled` на 30 TOPS GPU: ~20-30с на простой LLM-вызов.
- `OpenAICompatibleClient` (openai_client.py:8) создаёт `AsyncOpenAI(...)` **без явного `timeout=`**.
- Реальные таймауты в логах worker'а: `plan_node LLM failed: Request timed out` через ~16с; `answer_node LLM failed: Request timed out` через ~16с.
- Это OpenAI SDK retry behavior на медленный endpoint — ReadTimeout где-то по дороге.

**Каскадный эффект:**
1. `classify_node` стартует с `gaps = [исходный_query]` (см. [nodes.py:75-78](src/actions/research/nodes.py:75)). Исходный query — это 1.5КБ промпт пользователя.
2. `plan_node` должен сгенерировать короткие саб-вопросы — но LLM таймаутится → `gaps` остаются с 1.5КБ оригиналом.
3. `search_node` (nodes.py:164) идёт в `web_search(query=gap, k=3)` — где gap = 1.5КБ.
4. SearXNG получает GET с `q=<1.5КБ урла>&language=en` → Google не находит ничего → `empty organic (got 0, need ≥3)`.
5. После 3 attempts → `web_search failed` → `urls_visited: 0` → `facts: []` → "No facts collected".

**Фикс LLM timeout:**

`src/infrastructure/external_api/clients/openai_client.py:8` — заменить:

```python
self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
```

на:

```python
self.client = AsyncOpenAI(
    base_url=base_url,
    api_key=api_key,
    timeout=httpx.Timeout(120.0, connect=10.0),
    max_retries=2,
)
```

Это даст агенту нормально работать на 30 TOPS endpoint (`120с` запас даже для длинных reasoning ответов).

**Альтернатива без правок кода**: обойти research-агент полностью — прямой POST к LLM с уже собранным контекстом из Яндекса (title, categories, address, phones, rating, services). Качество идей будет на основе общих знаний модели по категории бизнеса. См. раздел 7.

---

## 7. Стратегия "Direct LLM" (без research-агента)

**Идея**: на 316 организациях, где у нас уже есть из Yandex API полный контекст (title, categories, address, services, rating), web-поиск + scrape бесполезны для большинства мелких бизнесов (как ABC, Эверест, Ателье — у них нет узнаваемого онлайн-следа). Модель `qwen3.5-9b` сама знает специфику отрасли "автомойка/детейлинг" или "адвокатские услуги" не хуже, чем итоговый research-отчёт по 0 фактов.

**Пайплайн:**
```
organizations_dedup.json
  └─► для каждой орг:
       прямой POST http://100.70.230.73:20022/v1/chat/completions
       system: "ты ML/CV-консультант B2B-аутрича в РФ..."
       user: "Бизнес [TITLE], [CATEGORIES], адрес [ADDR], услуги [SERVICES]. Дай 5-10 идей ML/CV-автоматизации с (а) задачей (б) технологией (в) метрикой."
  └─► save: ideas/<oid>.json
```

**Параметры:**
- Без web_search и без scrape — нет проблем с SearXNG rate-limit/пустыми результатами.
- Один LLM-вызов на орг = ~30-60с (вместо ~110с в research-агенте).
- Полный прогон 316 орг = ~3-5 часов вместо ~10-20.
- Качество для мелких безбрендовых бизнесов = такое же или лучше (research всё равно ничего не находит).

**Расширения** (опционально):
- Для организаций с узнаваемым брендом (Wildberries, Дикси, банки) — отдельно запустить research-агент.
- Использовать `extract` метод фасада для structured output (Pydantic-схема `IdeaList`).

---

## 8. Открытые вопросы

- Поддерживает ли puls-proxy HTTP-схему на портах 11000-11019? Если нет — выкатывать вариант C сразу.
- В session_actor [session_actor.py:33,71](src/infrastructure/queue/session_actor.py:33) прокси приходит из запроса клиента — нужно ли так же подсовывать `proxy_provider.get_proxy()` как fallback?
- SearXNG имеет свой пул прокси (в `infra/searxng/`). Стоит ли его тоже подружить с `proxies.txt`, или текущая раскладка норм?
