# 4-model comparison on Агат (oid 226497224828)

**Target:** Коллегия адвокатов «Агат», 6-я Красноармейская ул., 3, СПб
**Date:** 2026-05-27
**Pipeline:** /research/run via atomic-scraper-service (Phases 1-6), mode=quality, language=ru, output_schema=ORG_CARD_SCHEMA

---

## Configuration per variant

| Variant | Provider | Model | Notes |
|---|---|---|---|
| A | local llama-server (port 20022) | `qwen3.5-9b-claude-4.6-opus-reasoning-distilled` Q4_K_S | baseline (the existing audit result) |
| B | OpenRouter | `qwen/qwen3.5-plus-20260420` | named-function `tool_choice` unsupported → plan/select_urls nodes fail through except path |
| C | OpenRouter | `deepseek/deepseek-v4-flash` | both `response_format=json_schema` and named `tool_choice` work in pre-flight probes |
| D | Anthropic via Agent tool | `claude-haiku` (subagent w/ WebSearch + WebFetch) | bypasses the LangGraph pipeline entirely — model gets the query and produces ORG_CARD JSON itself |

---

## Speed

| Variant | Wall (s) | Iterations | URLs visited | Facts collected | Citations |
|---|---:|---:|---:|---:|---:|
| A — local qwen3.5-9b | **1461.5** | 5 | 12 | 111 | 12 |
| B — OR qwen3.5-plus | **101.9** | 2 | 0 | 0 | 0 |
| C — OR deepseek-v4-flash | **1237.9** | 12 | 22 | 242 | 22 |
| D — haiku subagent | **45.0** | — (1-shot) | 12 tool calls | — | 5 |

---

## Structured_output filled top-level keys

| Variant | what_they_do | scale | tech_stack | vacancies | social | contacts | yandex_maps | problems | sources | _other_ |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| A | ✓ | ✗ | ✗ | ✗ | vk×2 | 2 phones, 1 email | ✗ | ✗ | 10 | — |
| B | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | invented its OWN keys (name, categories, address, yandex_maps_rating, yandex_maps_review_count) — schema ignored |
| C | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 5 | — |
| D | ✓ | ✗ | ✗ | 1 (hh.ru) | telegram (vague) | 1 phone | rating+hours | ✗ | 5 | — |

---

## Quality findings

### A — local qwen3.5-9b — HALLUCINATION 3/10 (per prior haiku audit)
- ✓ real phone +7 (812) 715-21-11
- ✓ real email ka-agat@mail.ru, 2 real VK pages
- ✗ second phone `+7 926 555-28-048` is from a different Moscow «Юридическая компания Агат»
- ✗ entity mixing: 3 different addresses cited in facts (6-я Красноармейская, 3-я Красноармейская, Невский 81)
- many sources (otzovik.com, dostupnoepravo.ru) attached to wrong-entity reviews

### B — OpenRouter qwen3.5-plus — UNUSABLE
- Pipeline incompatibility: named `tool_choice` returns 400 → `plan_node` and `select_urls_node` fall back to empty
- `search_node` got 0 queries → 0 candidates → 0 URLs → 0 facts (101s spent mostly on classify + answer_node retries)
- `response_format=json_schema` also not strict — model returned its own keys (`name`, `description_services`, …) instead of ORG_CARD_SCHEMA
- **Conclusion:** this model cannot drive the current pipeline. Would need fallback to `tool_choice="auto"` + json_object for both `generate_structured` and `generate_with_tools`.

### C — OpenRouter deepseek-v4-flash — REWRITE 4/10 (schema-fill failure)
- Pipeline WORKED end-to-end (12 iters, 22 URLs, 242 facts) — 16× more facts than the local 9B
- But `answer_node` filled only `sources` (5 entries). Lost `what_they_do`, `contacts`, `social`, `vacancies` etc despite having data in the facts list.
- Sources mostly correct (zoon.ru СПб card, aplo.fparf.ru registry, rusprofile КА СПБ «Агат» at the right address, Yandex.Maps card) — these are AUTHORITATIVE
- One mis-source: `ag-pravo.ru/o-kompanii/arkhangelsk` (Архангельск, completely different entity)
- Verdict: the LLM is competent at retrieval (242 facts, no entity hallucinations in citations) but the final schema-fill prompt under-constrained it. Same failure mode as БКФ in the previous audit.

### D — haiku subagent — GOOD 8/10
- Fastest by far (45s vs 1238-1461s) and most accurate
- Found the canonical site: `адвокаты-агат.рф` (the Russian punycode domain `xn----7sbabaikd9cyb8be6i.xn--p1ai`)
- Found the hh.ru employer ID (`3913923`) for vacancies
- Found `aplo.fparf.ru` registry entry — authoritative federal source for advocate bar associations
- Found `2gis.ru/spb/firm/70000001060946001` (matches the right СПб entity)
- Correct phone +7 (812) 715-21-11; no Moscow contamination
- Hours filled: «Пн-пт 10:00–19:00; сб 10:00–18:00»
- Weak spots: no email, vague "telegram: Present (mentioned in search results)" instead of a URL, no scale data
- BUT no hallucinations, no entity mixing

---

## Summary

| Dimension | A (local 9B) | B (OR qwen3.5-plus) | C (OR deepseek-v4-flash) | D (haiku) |
|---|---|---|---|---|
| Wall time | 1462s | 102s | 1238s | **45s** |
| Pipeline compat | ✓ | **✗** | ✓ | n/a |
| Schema obedience | partial (4 keys) | none (own schema) | partial (1 key) | **partial+correct (7 keys)** |
| Authoritative sources | mixed | none | aplo+rusprofile+zoon | aplo+hh+2gis+zoon+.рф |
| Entity disambiguation | **fail** (MSK contamination) | n/a | partial (Архангельск slip) | **clean** |
| Best for | volume of facts | nothing here | retrieval breadth | extraction quality |

**Per-org cost:** my measurement is throughput only. User to check OpenRouter dashboard for $/run on B and C.

---

## Files

- `agat__A_local-qwen3.5-9b.json` — raw service output, 56 KB
- `agat__B_openrouter-qwen3.5-plus.json` — raw, ~10 KB (mostly empty)
- `agat__B_run.log` — pipeline trace
- `agat__C_openrouter-deepseek-v4-flash.json` — raw, ~135 KB (242 facts, 22 citations)
- `agat__C_run.log` — pipeline trace
- `agat__D_haiku.json` — haiku's direct JSON answer
- `REPORT_4models_agat.md` — this report

---

## Recommendation

1. **B (qwen3.5-plus)** — incompatible with current pipeline. Skip unless we add a "tool_choice='auto' + JSON-object fallback" code path.
2. **C (deepseek-v4-flash)** — fastest competent option for the LangGraph pipeline; schema-fill is the bottleneck, NOT retrieval. Same failure mode as the local 9B on БКФ. Fix is upstream in `answer_node` prompt, not in the model.
3. **D (haiku)** — by far the best speed × quality. Suggests: replacing the multi-node LangGraph for "simple org card" tasks with a single-LLM call against haiku/sonnet is a viable alternative architecture.
4. **A (local 9B)** — same quality tier as C but 18% slower. Local-only advantage = no $.
