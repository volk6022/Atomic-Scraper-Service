# Research Agent: Nodes (src/actions/research/nodes.py)

> Срез Wave D / Phase 2. Анализ через `tools/ask_local_llm.py` (см. жёсткие
> правила задания — `.py` не читались напрямую). Контекст подтянут из
> `specs/011-auto-research-agent/spec.md` и
> `docs/research-agent-fixes-2026-05-20.md` (свежий ревизионный отчёт
> после переписывания `nodes.py` целиком 20 мая).

## Files analyzed

- `src/actions/research/nodes.py` — все LangGraph-ноды агента
  (single file, переписан целиком в сессии 2026-05-20 — см.
  research-agent-fixes-2026-05-20.md).

Сопутствующие файлы того же модуля (не анализируются здесь, но упомянуты
для контекста):

- `src/actions/research/graph.py` — компилирует StateGraph, держит
  router `should_continue` (router-функция **не** в `nodes.py`).
- `src/actions/research/state.py` — `ResearchState` (`TypedDict, total=False`).
- `src/actions/research/llm_utils.py` — `strip_reasoning`,
  `extract_json` (созданы в той же сессии).
- `src/actions/research/tools.py` — `web_search`, `scrape_url`,
  `extract_facts`, `extract_facts_llm`.
- `src/actions/research/modes.py` — preset'ы `speed/balanced/quality`.
- Тесты: `tests/unit/research/test_nodes.py` (после правок 2026-05-20).

## Purpose & responsibilities

`nodes.py` содержит **9 async-нод LangGraph**, реализующих цикл
автономного research-агента: classify → plan → search → rank_dedupe →
scrape → extract_facts → reflect → (loop|answer) → writer → END.
Каждая нода — pure-ish функция `(state) -> partial_state_dict`, которую
LangGraph мержит в общий `ResearchState`. Ноды отвечают за:

- оркестрацию LLM-вызовов через `get_orchestration_client()` (LM Studio,
  модель qwen3.5-9b-reasoning-distilled);
- работу с инструментами (`web_search` → SearXNG, `scrape_url` →
  Playwright/SiteEnricher, `extract_facts_llm` → jinaai.readerlm-v2);
- инкрементальный сбор `facts`/`citations`/`visited_urls`;
- контроль завершения (beast-mode по бюджету/deadline/stall);
- сборку итогового `ResearchReport`-совместимого dict в `writer_node`.

## Key classes / functions

### Node-функции (все `async def node(state: ResearchState) -> dict`)

| # | Node | Reads | Writes / merges | LLM / Tool | Early exit / branch |
|---|------|-------|-----------------|------------|---------------------|
| 1 | `classify_node` | `query`, `gaps` | `query_type`, `gaps` | orchestration LLM (JSON `{"type": ...}`); `strip_reasoning` + `extract_json` | fallback к substring-match после strip_reasoning, default `query_type="exploratory"` |
| 2 | `plan_node` | `query`, `facts[:30]`, `gaps` | `gaps` (append + dedupe, cap 5, длина 5..200) | orchestration LLM (JSON array of strings) | при невалидном JSON → `new_gaps=[]`, существующие gaps сохраняются |
| 3 | `search_node` | `gaps[:3]`, `candidate_urls`, `stall_counter` | `candidate_urls` (dedupe URL), `stall_counter` (++ при пустом ответе) | `web_search.ainvoke()` → SearXNG | при `stall_counter >= 2` — пропуск, но **не** возвращает `[]` (LangGraph reducer стёр бы накопленные кандидаты) |
| 4 | `rank_dedupe_node` | `mode`, `candidate_urls`, `visited_urls` | `current_batch` (top-K **невизит-ленных**), `stall_counter` (++ если batch пуст) | `get_mode_preset()` (нет LLM) | НЕ перезаписывает `candidate_urls` — pool остаётся для следующей итерации |
| 5 | `scrape_node` | `current_batch` (fallback `candidate_urls[:concurrency]`), `mode`, `visited_urls` | `visited_urls` (append), `scraped_content` (list) | `scrape_url.ainvoke()` параллельно через `asyncio.gather` + `Semaphore(scrape_concurrency)` | failed scrape → `None`, фильтруется в comprehension `[r for r in results if r]` |
| 6 | `extract_facts_node` | `scraped_content`, `query`, `facts`, `citations` | `facts` (append), `citations` (dedupe по URL — одна на источник) | `extract_facts_llm()` (LLM-JSON, max 8 фактов, confidence clamp 0..1); fallback `extract_facts.ainvoke()` (regex) | двойной try/except; пустой LLM-результат → regex |
| 7 | `reflect_node` | `tokens_used`, `token_budget`, `deadline_ts`, `stall_counter`, `iteration`, `beast_mode` | `beast_mode`, `iteration` (++) | — (чистая логика) | устанавливает `beast_mode=True` при любом из трёх триггеров (см. ниже) |
| 8 | `answer_node` | `query`, `facts[:60]`, `citations` | `answer_draft` | orchestration LLM (markdown с inline `[N]`); `strip_reasoning` на ответе | generic fallback из collected facts при ошибке LLM |
| 9 | `writer_node` | `answer_draft`, `query`, `mode`, `facts`, `citations`, `visited_urls`, `iteration`, `started_ts`/`deadline_ts` | `final_answer`, `final_report` (dict, валидный для `ResearchReport(**...)`) | — | shape: `{query, mode, answer_markdown, citations, facts, stats}` |

### Helper-функции

- `emit_node_event(node_name, kind, data=None, elapsed_ms=None)` — простой
  `logging.info` (НЕ structlog) с событиями `node_entered` /
  `node_exited` / `completed`. **task_id не пропагируется** —
  известное ограничение (см. research-agent-fixes-2026-05-20.md, раздел
  «Worker не пушит прогресс в store»).

### Router-функция

`should_continue` **отсутствует в nodes.py** — она в
`src/actions/research/graph.py`. По спецификации US3 / FR-019 router
проверяет: `beast_mode == True` → `answer_node`; иначе `iteration >=
max_iters` → `answer_node`; иначе `gaps` непуст → `plan_node`; иначе →
`answer_node`.

## Beast-mode (graceful degradation) — US3 / FR-008/009

`reflect_node` устанавливает `beast_mode=True` при **любом** из:

1. `budget_ratio = tokens_used / token_budget >= 0.85`
   (token_budget>0).
   **Smell**: `tokens_used` нигде не инкрементируется → это мёртвый
   код по факту, beast по бюджету **не срабатывает** (известный баг
   из research-agent-fixes-2026-05-20.md).
2. `time.time() > deadline_ts` — основной рабочий триггер.
3. `stall_counter >= 2` — после двух итераций без новых URL.

`iteration` инкрементируется здесь же (не в `plan`/`search`).

## Prompts / structured output

- **classify_node**: system требует `{"type": "factoid|comparative|
  exploratory|decomposable"}`. Парсинг: `strip_reasoning` →
  `extract_json` → fallback substring-match.
- **plan_node**: system `"Respond ONLY with a JSON array of 3-5
  strings… No prose, no numbering"`. Принимает также форму
  `{"questions": [...]}`. Валидация — manual: `isinstance`, length
  bounds 5..200, dedupe, cap 5.
- **extract_facts_node**: основная работа в `tools.extract_facts_llm`
  (вне nodes.py). Из ноды передаётся `scraped_content` + `query`;
  ожидаются объекты `{claim, confidence, source_url}`, max 8.
- **answer_node**: system `"Produce a concise markdown answer with
  inline numeric citations like [1], [2]"`. Срез фактов 60 (поднят с
  10 в фиксах 2026-05-20), срез prompt ~4 KB.
- **Pydantic schemas внутри nodes.py не используются** — manual
  validation через `isinstance/len`. Pydantic-модель `ResearchReport`
  применяется снаружи, в `infrastructure/queue/research_task.py` после
  `writer_node`.

## Token counting

`tiktoken` **не импортируется**. `state["tokens_used"]` инициализируется
0 и не инкрементируется ни в одной ноде — это объясняет, почему
beast-trigger по бюджету мёртв. По плану фикса (см.
research-agent-fixes-2026-05-20.md) нужно протоколировать
`usage.total_tokens` в `OpenAICompatibleClient.generate` и агрегировать в
state — задача не сделана.

## Data flow within slice

`ResearchState` (TypedDict, total=False) аккумулирует:

- monotonically растущие: `candidate_urls`, `visited_urls`, `facts`,
  `citations`, `gaps`, `scraped_content`;
- ephemeral per-iter: `current_batch`, `query_type`, `answer_draft`;
- управляющие: `iteration`, `stall_counter`, `beast_mode`,
  `tokens_used`, `deadline_ts`, `started_ts`, `mode`, `max_tokens`,
  `token_budget`;
- финальные: `final_answer`, `final_report`.

`visited_urls` хранится как `list[str]` (не set) — для JSON-сериализации
в Redis/SSE.

## Mermaid diagram

```mermaid
flowchart LR
    START([START]) --> classify[classify_node<br/>query_type]
    classify --> plan[plan_node<br/>+gaps]
    plan --> search[search_node<br/>+candidate_urls<br/>stall_counter++]
    search --> rank[rank_dedupe_node<br/>+current_batch]
    rank --> scrape[scrape_node<br/>+visited_urls<br/>+scraped_content]
    scrape --> extract[extract_facts_node<br/>+facts<br/>+citations]
    extract --> reflect[reflect_node<br/>iteration++<br/>beast_mode?]
    reflect -->|continue: gaps non-empty<br/>and not beast_mode<br/>and iter < max_iters| plan
    reflect -->|beast_mode OR<br/>iter >= max_iters OR<br/>gaps empty| answer[answer_node<br/>+answer_draft]
    answer --> writer[writer_node<br/>+final_report]
    writer --> END([END])

    search -.->|stall_counter>=2:<br/>skip, return {}| rank
    extract -.->|LLM JSON fails| extract_regex[fallback:<br/>tools.extract_facts<br/>regex]
    extract_regex --> reflect
```

Beast-mode shortcut: НЕ skipping nodes напрямую (граф проходит через
`reflect_node` всегда), но router после reflect выкидывает в `answer`,
минуя plan/search/scrape/extract.

## External dependencies

- **LLM (orchestration)**: `get_orchestration_client()` — LM Studio
  `http://172.30.80.1:20022/v1`, модель
  `qwen3.5-9b-claude-4.6-opus-reasoning-distilled` (с `<think>` блоками).
- **LLM (extraction)**: `jinaai.readerlm-v2` через
  `tools.extract_facts_llm` (вызов снаружи ноды).
- **Tools**: `tools.web_search` (SearXNG via
  `infrastructure/external_api/searxng_client.py`), `tools.scrape_url`
  (Playwright via SiteEnricher), `tools.extract_facts` (regex
  fallback), `tools.extract_facts_llm`.
- **State**: `state.ResearchState`, `state.NodeEvent`.
- **Utils**: `llm_utils.strip_reasoning`, `llm_utils.extract_json`.
- **Modes**: `modes.get_mode_preset` (через rank_dedupe / scrape).
- **stdlib**: `asyncio`, `logging`, `time`, `datetime`.

## Tests covering this slice

- `tests/unit/research/test_nodes.py` — основной (US1 + US3
  TDD-контракт). После 2026-05-20:
  - `test_search_returns_candidates` — мокает `search_client.search`,
    больше не ходит в живой SearXNG.
  - `test_dedupe_removes_visited` — обновлён под `current_batch`-контракт
    `rank_dedupe_node`.
  - `test_plan_generates_gaps` — мокает orchestration LLM (раньше
    падал на нестабильности qwen).
- `tests/unit/research/test_modes.py` (US2).
- `tests/unit/research/test_state_transitions.py` (US1, router
  truth-table — но router живёт в graph.py).
- `tests/integration/test_research_graph.py` (US3/US4, end-to-end на
  FakeChatModel + stub tools).
- `tests/contract/test_research_endpoint.py` (US1, REST/SSE).

Покрытие в целом: 266 passed на момент 2026-05-20.

## Open questions / smells

- **`tokens_used` всегда 0** → beast-mode trigger по бюджету мёртв.
  Нужно протоколировать `usage.total_tokens` в OpenAI-client и
  агрегировать. Сейчас работают только deadline и stall.
- **`emit_node_event` не пропагирует `task_id`** → worker обновляет
  Redis store только дважды (старт/финал), `/status` показывает
  `phase="starting", iteration=0` до самого `completed`. Лечится
  context-var или partial-application в `research_task.py` перед
  `graph.ainvoke`.
- **`logging.info` вместо structlog** — несоответствие FR-021
  (структурные логи на каждой границе ноды) и общим конвенциям проекта
  (CLAUDE.md упоминает structlog).
- **Pydantic schemas не используются в нодах** — вся валидация
  LLM-output manual (`isinstance`, length, dedupe). Структурный output
  можно было бы провалидировать через `pydantic.BaseModel` сразу после
  `extract_json` (повысит read'ability и даст уже-готовые ошибки).
- **`token_budget` достижим только через preset/override**, но
  поскольку `tokens_used` не растёт, override бессмыслен —
  пользователь может задать `max_tokens=1000`, и beast не сработает.
- **Нет explicit cap'а на `scraped_content`** в state — при долгих
  итерациях dict в Redis может разрастаться (нет TTL по содержимому,
  только на ключе задачи).
- **`extract_facts_node` имеет двойной try/except** (LLM → regex) —
  если оба падают, тихо возвращает пустой facts. Желательно
  отдельный warning + увеличить `stall_counter` (текущая логика
  считает только пустой search).
- **Тесты, не покрытые** (известные дыры):
  - что `writer_node` возвращает структуру, валидную для
    `ResearchReport(**result)`;
  - stall-detection при пустых search-результатах;
  - cross-process isolation Redis store;
  - SSE JSON-shape.
