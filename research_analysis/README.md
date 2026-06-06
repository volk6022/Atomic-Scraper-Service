# W2+W3 — анализ 517 ресёрчей (итерация 1)

Цель: понять проблемы агента и проставить флаги (мультифилиал/гос/контакт) на
существующих 517 ресёрчах. Источник: `yandex_enrichment_experiment/data_backup.zip`.

## Состав

| скрипт | GPU | что делает |
|---|---|---|
| `stats_517.py` | нет | детерминированная статистика (тулы, успешность, поля, контакты). **Сделано** → `results/stats_517.{json,png}`, `REPORT_stats_517.md` |
| `analyze_research.py` | **да** | per-research LLM-анализ (W2 проблемы + W3 флаги) одним проходом → `analysis/{oid}.json` |
| `summarize_analyses.py` | tally — нет; темы — да | сводка: списки мультифилиал/гос/сети + статистика тегов; опц. LLM-тематическая сводка |

## Порядок запуска (когда GPU свободна; mode single-GPU = последовательно)

```bash
# 0. smoke на 3 ресёрчах — проверить парсинг JSON от модели
LIMIT=3 uv run python research_analysis/analyze_research.py

# 1. полный проход (≈3–5 ч на 517; идемпотентно, можно прерывать/докатывать)
uv run python research_analysis/analyze_research.py

# 2. сводка + W3-списки (быстро, без GPU) + опц. тематическая сводка (GPU)
uv run python research_analysis/summarize_analyses.py
RUN_LLM_SUMMARY=1 uv run python research_analysis/summarize_analyses.py
```

ENV: `LIMIT=N`, `OIDS=a,b,c`, `INCLUDE_AGENT_SOURCE=1` (вложить исходник агента в
систему — точнее, но дольше/дороже по токенам).

## Что вернёт LLM на каждый ресёрч (analysis/{oid}.json → `analysis`)
- `overall` (good/partial/poor), `problems[]` (issue/evidence/severity),
- `root_cause_tags[]` (no_website, serp_weak, scrape_blocked, schema_gap,
  only_mobile_phone, over_search, no_email_anywhere, sparse_web_presence, …),
- `missing_fields[]` — поля, которые стоило заполнить,
- **W3:** `multi_branch`, `is_chain_or_brand`, `is_government`, `contact_quality`.

## Итоги stage-2 (`results/`)
- `analysis_summary.json` — overall/contact_quality/теги/missing.
- `multi_branch_orgs.json`, `government_orgs.json`, `chains_brands.json` —
  списки name+oid для будущей фильтрации (по плану: не ресёрчить повторно).
- `themes_summary.md` — тематическая сводка проблем (если включён LLM-проход).

## Уже известно из детерминированной статистики (см. REPORT_stats_517.md)
Успешность 96.7%; serp/scrape сбалансирован; **email лишь 15.5%, только-телефон 80%,
соцсети 81% (VK/Instagram/Telegram)** — основной канал охвата = соцсети.
