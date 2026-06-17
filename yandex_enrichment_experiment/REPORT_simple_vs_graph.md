# SIMPLE 2-tool agent vs LangGraph pipeline — Агат + Школа 306

**Date:** 2026-05-27
**Goal:** find where the multi-node LangGraph pipeline loses to a flat agent loop with the same models.

---

## Setup

**SIMPLE-agent** (`simple_agent.py`): single LLM in a chat loop with 3 tools — `web_serp(query, k)`, `web_scrape(url)`, `submit_org_card(card)`. No graph, no classify/plan/select stages. `tool_choice="auto"`. Max 25 turns. Same target query as the pipeline, same ORG_CARD_SCHEMA inlined into the `submit_org_card` tool params.

**LangGraph pipeline**: existing /research/run with classify→plan→search→select_urls→scrape→extract_facts→reflect→answer→writer.

Both hit same SearXNG (port 8080), same SiteEnrichAction / httpx scrape.

---

## Results — Агат (oid 226497224828)

| Approach | Model | Wall | Turns | SERP / Scrape | Tokens | Keys filled | Quality |
|---|---|---:|---:|---|---:|---:|---|
| LangGraph | local qwen3.5-9b | 1462s | — | — / 12 | — | 4/9 | HALLUCINATION 3/10 (MSK phone leak) |
| LangGraph | OR qwen3.5-plus | 102s | — | 0 / 0 | — | 0 (invented schema) | UNUSABLE (named tool_choice 400) |
| LangGraph | OR deepseek-v4-flash | 1238s | — | — / 22 | — | 1/9 (sources only) | REWRITE 4/10 |
| haiku 1-shot subagent | claude-haiku | **45s** | — | 12 calls | — | 7/9 | GOOD 8/10 |
| **SIMPLE** | local qwen3.5-9b | **436s** | 19 | 11 / 7 | 87k | **7/9** | **GOOD** (real ka-agat@mail.ru, .рф site, hh.ru/3913923, no MSK) |
| **SIMPLE** | OR qwen3.5-plus | 591s | 19 | 39 / 14 | 265k | **8/9** | **GOOD** (rusprofile ИНН/ОГРН, hours, 8 sources) |
| **SIMPLE** | OR deepseek-v4-flash | 744s | 25 | 33 / 28 | 378k | **0** (no submit) | INCOMPLETE — hit max_turns, but retrieval was perfect (28 right URLs) |

---

## Key observations

### 1. The graph is the bottleneck, not the model
On the **same** local qwen3.5-9b model:
- LangGraph: 1462s, 4/9 keys, MSK contamination
- SIMPLE: **436s, 7/9 keys, no contamination**

3.4× faster wall and dramatically cleaner output — same SearXNG, same scrape backend. All the difference is in HOW we drive the LLM: in SIMPLE the model itself decides search→scrape→submit ordering; in LangGraph we enforce a rigid sequence with separate LLM call per node.

### 2. OpenRouter qwen3.5-plus is the strongest model when freed
In LangGraph: it failed completely (named `tool_choice` 400'd → empty graph).
In SIMPLE with `tool_choice="auto"`: **all 8 schema keys filled, most authoritative source coverage** (rusprofile with ИНН/ОГРН, fparf.ru registry, 2 versions of the official site). Same model, opposite verdict — purely an API-compat issue.

### 3. Deepseek-v4-flash has a "no terminal commit" pathology
In LangGraph: `answer_node` filled only `sources` (no `what_they_do`, no contacts).
In SIMPLE: kept making excellent retrieval calls (28 scrapes of right URLs: yandex.maps/reviews, vk.com/ka_spb_agat, 2gis, hh.ru/vacancy/85842993, rusprofile, адвокаты-агат.рф/kontakty) but **never called submit_org_card** in 25 turns. Same model, same pattern: it's reluctant to commit.

Fix: add to system prompt "if turn ≥ 8 and you still haven't submitted, you MUST submit now with whatever you have" + tighten `max_turns` to 12.

### 4. Haiku is the speed champion (45s, 8/9 keys)
Already known from the 4-model compare. Confirms: **simpler architecture + capable model = much better than complex pipeline + weaker local model**.

---

## Log audit findings (Школа 306, 8-iter LangGraph run, 1278s)

From the haiku log-auditor on the captured pm2 trace:

**Failure breakdown:**
- `scrape_node`: **62.5% failure rate** (5/8 iters had all-URL scrape failures). Two patterns:
  - `net::ERR_TUNNEL_CONNECTION_FAILED` on `sc306.admiral.gov.spb.ru/*` subpages — picked **repeatedly** across iterations because no domain blacklist after failure
  - Pydantic `string_too_short` validation on Yandex.Maps URLs + word_count overflow on hh.ru pages (4862 words vs 600 cap)
- `search_node`: SearXNG returns 0 organic on **8/8 iterations** for one particular query — appears to be **the raw initial context pasted as a search query** (full 3KB text). plan_node didn't sanitize properly.
- `extract_facts_node`: iters 5 & 8 extracted **0 facts** (because 0 scrapes succeeded those iters)
- `answer_node`: surprisingly OK for Школа 306 — 75% schema filled with high-confidence data, no hallucination

**Iteration efficiency:**
- iter 1–4 productive (8→28→15→23 facts)
- iter 5 wasted (0 facts)
- iter 6: 7 facts
- iter 7: 25 facts
- iter 8 wasted (0 facts)
- **Early-stop at iter 6 would have saved ~6 min with 76% of final facts**

**Top 5 concrete prompt/state fixes (per haiku auditor):**
1. **plan_node**: enforce query sanitization — strip raw context, ≤8 tokens, no `категории:` field markers. The whole 3KB query is bleeding into one of the proposed SERP queries.
2. **select_urls_node**: domain-failure blacklist — after 2 timeouts on a domain, deprioritize all URLs from that domain. Currently re-picks `sc306.admiral.gov.spb.ru` every iteration.
3. **scrape_node**: graceful truncation + skip-on-validation-error instead of raising. Yandex.Maps and hh.ru hit Pydantic limits → silent loss.
4. **reflect_node**: stop after 2 consecutive 0-fact iterations. Currently only `budget_ratio ≥ 0.85` or `stall_counter ≥ 2` triggers beast_mode — neither fires when iterations are "active but useless".
5. **select_urls_node**: explicitly deprioritize aggregators (hh.ru listing pages, superjob, rubrikator).

---

## My own graph analysis (independent of haiku auditor)

10-point list submitted earlier in conversation. Convergence with haiku's findings:

| My finding | Haiku auditor finding | Convergent? |
|---|---|---|
| #2 anti-loop in plan_node | #1 query sanitization in plan_node | YES (both targeting plan_node garbage output) |
| #3 entity anchor in breadcrumbs | (no equivalent) | only my analysis caught the MSK contamination pattern |
| #6 `required` in schema for answer_node | (Школа 306 wasn't a schema-fill failure case — Школа got 75%) | partial |
| #7 failed_urls tracking | #2 domain blacklist after 2 timeouts | YES |
| #8 beast_mode trigger on stagnation | #4 stop after 2 zero-fact iters | YES |
| #10 yandex_maps shortcut node | (no equivalent) | only mine |

**Combined top-priority fixes (consensus):**
1. **plan_node**: sanitize queries; anti-repetition state; ban context-leak
2. **select_urls_node**: domain failure tracking → blacklist after N=2 timeouts
3. **reflect_node**: early stop when extract_facts == 0 for 2 consecutive iters
4. **scrape_node**: truncate large pages before `EnrichedContent` validation, don't raise on size limit
5. **state**: add `entity_anchor` breadcrumb to prevent multi-entity mixing (the Агат/Фермерские/БКФ failure mode)

---

## Recommendation

**Short term (1-2 hours of work):**
- Apply the 5 consensus fixes above to LangGraph

**Medium term (1 day):**
- A/B the LangGraph against `simple_agent.py` on the same 6 orgs (Школа 306, Пятёрочка, Фермерские, Агат, БКФ, Dolphinwolf)
- The data here strongly suggests SIMPLE wins on quality AND speed for org-card tasks

**Architectural recommendation:**
The multi-node LangGraph adds value when:
- task needs heavy parallel processing (extract_facts across N docs concurrently)
- task has multiple distinct LLM stages with different system prompts
- task needs state machines / loops with conditional branches

For **single-org card extraction**, the graph adds friction:
- 8 LLM calls per iter × 8 iters = 64 LLM calls, vs SIMPLE's 19 turns
- model loses target identity between LangGraph stages (no shared "anchor" except `state["query"]`)
- each node's system_prompt re-bootstraps the task → re-introduces ambiguity

For the production "316 orgs" run, **SIMPLE-agent on OR qwen3.5-plus** (590s × 316 = 52 hours single-threaded, ~13h with 4 concurrent) **may be both faster AND higher-quality** than the current LangGraph pipeline on local 9B (1450s × 316 = 127h, ~32h with 4 concurrent).

User to measure $ cost on OpenRouter dashboard for B/C.

---

## Files

- `agat__SIMPLE_local.json` — 87k tokens, 7 keys, 436s
- `agat__SIMPLE_openrouter-qwen.json` — 265k tokens, 8 keys, 591s
- `agat__SIMPLE_openrouter-deepseek.json` — 378k tokens, 0 keys (no submit), 744s
- `agat__SIMPLE_*.run.log` — stdout for each
- `log_capture_school306.events.txt` — 65KB curated event log for Школа 306 that haiku audited
- `log_capture_school306.pm2-err.log` — raw 1MB pm2 stderr from same run
- `REPORT_4models_agat.md` — prior 4-model compare (LangGraph + haiku)
- `REPORT_simple_vs_graph.md` — this report
