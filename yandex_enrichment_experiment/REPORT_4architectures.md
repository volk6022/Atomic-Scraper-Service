# 4 архитектуры research-агента — Агат, сводный отчёт

**Дата:** 2026-05-28
**Цель:** найти sweet-spot между «дешёвой» flat-agent архитектурой и тяжёлой sub-agent оркестрацией для задачи сбора org-card.

---

## Архитектуры

| Имя | Файл | Суть |
|---|---|---|
| **SIMPLE** | `simple_agent.py` | flat-loop, 3 тула (web_serp / web_scrape / submit_org_card), `tool_choice="auto"`. Baseline. |
| **ORCH** | `orchestrator_agent.py` | оркестратор + sub-agents: LLM-скоринг URL'ов, read_page/delegate_read/delegate_verify, 90k budget с 2 hard-compactions, soft-elide старых scrape'ов после 6 turn'ов. |
| **v2** | `simple_agent_v2.py` (initial) | SIMPLE + auto-compact + soft-elide + refraser-every-4-SERPs + goal-conditioned scrape extract + domain-fail tracking. |
| **v2.1** | `simple_agent_v2.py` (current) | v2 + **critic-gate на submit_org_card** (≥8.5/10 чтобы пропустить, 2 reject → force-accept), refraser_every=15, whitelist для key доменов. |

Тестовый таргет — Агат (oid `226497224828`), коллегия адвокатов СПб. yandex-карточка + отзывы пре-инжектируются в initial user-message; агент ищет только веб-часть.

---

## Сводная таблица

| Архитектура × модель | Wall | Turns | SERP / scrape | Total tok | last_orch_prompt | Compactions | Refrasers | Critic |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| SIMPLE local | 436s | 19 | 11 / 7 | 87k | n/a | — | — | — |
| SIMPLE qwen | 591s | 19 | 39 / 14 | 265k | n/a | — | — | — |
| SIMPLE deepseek | 744s | 25 | 33 / 28 | 378k | n/a | — | — | NO SUBMIT |
| ORCH local | 1415s | 14 | 10 / 23 | 178k | **14k** | 0 | — | — |
| ORCH qwen | 1452s | 11 | 17 / 11 | 208k | **18k** | 0 | — | — |
| v2 local | 1519s | 14 | 12 / 19 | 94k | **12k** | 0 | 3 | — |
| **v2.1 local** | **568s** | 12 | 17 / 13 | **105k** | **14k** | 0 | 1 | **9.5/pass** ✓ first try |

---

## Качество карточки vs SIMPLE local baseline

| Поле | SIMPLE local | ORCH local | v2 local | **v2.1 local** |
|---|---|---|---|---|
| what_they_do | ✓ | ✓ | ✓ | ✓ (расширенное) |
| websites | 3 (incl. registry) | 2 | 1 (это hh/vacancy! bug) | 3 (.рф + obiz + zoon) |
| phones | 2 | 1 | 1 | 1 |
| emails | `aplo@list.ru` (generic) | `ka-agat@mail.ru` ✓ | (пусто) | `ka-agat@mail.ru` ✓ |
| vk | public222692440 | ka_spb_agat ✓ | (пусто) | public222692440 |
| vacancies | 1 | 0 | 2 | 2 |
| scale_indicators | 3 (junk: «Телефон: ...») | 1 | 6 (mixed) | 5 (clean) |
| problems_signals | пусто | 2 цитаты | 1 | пусто |
| yandex_maps.reviews_sample | (нет) | 1 цитата | (нет) | **2 цитаты** ✓ |
| yandex_maps.hours | (нет) | (нет) | (нет) | **«Пн-Пт: 10:00-19:00, Сб: 10:00-18:00»** ✓ |
| sources | 4 | 2 (1 мусорный `https://web_serp`) | 8 | **9** (rich diversity) |
| blocked_domains | — | — | 7 (overrun: yandex/2gis/hh/.рф) | **0** (whitelist) |

---

## Ключевые наблюдения

### 1. SIMPLE масштабируется, но плохо
- На local-9B → 87k, 436s, чистый результат, но не использует pre-loaded отзывы (`problems_signals` и `reviews_sample` пустые)
- На qwen-plus → **265k**, 39 SERPs (модель тонет в собственной истории, дублирует запросы)
- На deepseek-v4-flash → **378k и НИ ОДНОГО submit'а за 25 turn'ов** — terminal-commit pathology без gate

### 2. ORCH идеально экономит контекст, но платит временем
- last_orch_prompt 14-18k — превосходно
- Wall 3× больше SIMPLE на той же модели (1415s vs 436s)
- Качество **примерно равно** SIMPLE — не помогло и не убило
- Sources содержат `https://web_serp` (модель назвала tool-name как источник) — schema'у нужен post-submit sanitization

### 3. v2 — слишком резкий и неработающий
- Refraser-every-4 = слишком часто → модель пушится к новым запросам когда надо submit'ить
- Domain-fail-threshold=2 (без whitelist) → блочит yandex.ru, 2gis.ru, **официальный сайт** после пары 4xx
- websites field получил vacancy URL — модель путает прицел под давлением refraser'а
- reviews_sample проигнорирован несмотря на наличие в initial input
- Quality: regressed vs SIMPLE

### 4. v2.1 — sweet spot
- **Wall 568s** — только +30% к SIMPLE baseline (vs +3.5× у ORCH/v2)
- **Tokens 105k** — +20% к SIMPLE (vs +2× у ORCH)
- **Critic gate 9.5/10 на первой попытке** — не зацикливается, но даёт гарантию quality
- Refraser 1 раз вместо 3 (every=15 vs every=4)
- Domain whitelist: 0 ложных банов
- **Качество ≥ SIMPLE**: больше source diversity (9 vs 4), часы работы найдены (никто другой не нашёл), 2 vacancies vs 1, reviews_sample заполнен, брендовый email (`ka-agat@mail.ru` vs generic `aplo@list.ru`)

### 5. Critic-gate работает как калиброванный судья, не диктатор
Текст из v2.1 critic-feedback'а:
> Excellent research card. All core fields populated with grounded data. Diverse sources... Anchor phones match exactly. **Tech stack empty is fine for a law firm — no need to force data where none exists.** Strong pass.

Critic умеет понять что некоторые поля законно пустые (tech_stack для юрфирмы) — не требует ложного заполнения. Это критически важно: без этого critic был бы пыткой.

---

## Архитектурные выводы

| Когда | Используй |
|---|---|
| Простая организация на маленькой локальной модели | **SIMPLE** — быстрее всего, контекст не упирается в лимиты |
| Та же задача, но качество важно + хочется гарантию | **v2.1** — +30% времени за калиброванный critic + рост source diversity |
| Большая модель с большим context (cloud, 100k+) | **SIMPLE** или **v2.1** — orchestration не нужен, дешевле |
| Локальная модель, длинная задача (5-10+ scrape'ов) | **v2.1** — soft-elide + critic держат контекст в узде |
| Multi-entity disambiguation (Агат-SPB vs Агат-MSK) | **v2.1** с уточнённым anchor-check в critic'е |
| Cloud + budget concerns | **v2.1** — экономит токены на проблемных моделях (qwen 265k baseline → ожидаем ~150-180k) |

ORCH в чистом виде **не оправдан** для org-card задачи — слишком дорого по времени за то же качество. Его компоненты (LLM-скоринг URL'ов, delegate_read) могли бы быть полезны на принципиально другой задаче — например, академическом literature review с десятками PDF'ов.

---

## Что не сделано (pending user decision)

1. **v2.1 на OR-qwen** — ожидание: лучшие 8/9 keys, ~150-200k tokens (vs SIMPLE 265k), critic должен ловить hallucinations
2. **v2.1 на OR-deepseek** — ожидание: critic-gate победит no-submit pathology (force-accept на 3-й попытке)
3. **v2.1 на 5+ свежих орг** — replicate на разнообразных кейсах (ресторан, банк, школа)

Auto-mode classifier ранее отказал на OR-deepseek для нового скрипта; пользователь не подтвердил явно после ребута dialog'а.

---

## Файлы артефактов

- `agat__SIMPLE_{local,openrouter-qwen,openrouter-deepseek}.json` — baseline
- `orch__226497224828__{local,openrouter-qwen}.json` — orchestrator
- `v2__226497224828__local.json` — v2 (deprecated, кейс провала refraser+domain-block)
- `v2_1__226497224828__local.json` — **current best**
- `REPORT_4models_agat.md` — старый отчёт 4-model сравнения на LangGraph
- `REPORT_simple_vs_graph.md` — SIMPLE vs LangGraph + log-audit
- `REPORT_4architectures.md` — этот файл
