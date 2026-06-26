# Experiments Report — anonymous monitoring of RU job & freelance sources

**Date:** 2026-06-19 · **Branch:** `fl-hh-kwork` · **Scope:** Russian-segment job-search and freelance/order sites, automated **anonymously** (no login) for monitoring vacancies/orders relevant to Ivan's ML/CV/Python profile.

Companion per-site articles live in the knowledge base: `own_knowledge_base/wiki/auto-monitor/auto-research-*.md`. This report consolidates the engineering experiments under `experiment_monitoring/`.

---

## 1. Goal & method

Build the **monitoring** stage of the pipeline (monitor → research → score → notify): for each target site, find a **stable, anonymous** way to (a) list newest vacancies/orders and (b) parse an individual card. Method per site:

1. **Research** — LLM web-research via Atomic-Scraper-Service (`POST /api/v1/research/run`) to map APIs / page structure / anti-bot.
2. **Verification** — live, anonymous probing (httpx → Playwright+stealth → RU proxy rotation as needed), in `experiment_monitoring/experiment-<site>/`.
3. **Prototype monitor** — unified collectors + card parsers (`prototype/monitor_proto.py`), run 4× at 15-min intervals + an e2e card-parse pass.
4. **Card-parse test** — field-coverage matrix over sampled cards (`prototype/card_test/`).

**Infrastructure:** Atomic-Scraper-Service — docker (redis :16379, searxng :8080) + pm2 (llama-server :20022 Qwen3.5-9B, scraper-api :8000, taskiq-worker). Proxies: `proxies.txt` = puls RU residential, ports 11000–11099, IP rotates ~10 min (rotation helper: `experiment-hh/proxy_client.py`).

---

## 2. Site coverage (9 researched, 8 automated anonymously, 1 blocked)

| # | Site | Type | Anonymous method (verified) | Anti-bot | Proxy needed | Status |
|---|------|------|------------------------------|----------|--------------|--------|
| 1 | **hh.ru** | jobs | Playwright+stealth headless on HTML (`/search/vacancy?text=…&professional_role=96&area=113&order_by=publication_time`), `data-qa` selectors. Official `api.hh.ru` = **403 anon** (needs free OAuth app token). | DDoS-Guard | no (proxy breaks `area`) | ✅ |
| 2 | **avito.ru** | jobs + услуги | httpx direct; listing JSON in `data-mfe-state`; relevant tag feed `/all/vakansii/tag/python-razrabotchik?s=104` (s=104 = newest). | own firewall (not triggered) | no | ✅ |
| 3 | **superjob.ru** | jobs | httpx direct; date-sorted list from `window.APP_STATE.ids["VACANCY_SEARCH_RESULT"]`; card via JSON-LD `JobPosting` + APP_STATE. Official API needs free key. | Cloudflare (passive) | no | ✅ |
| 4 | **career.habr.com** | jobs | httpx direct; `data-ssr-state` JSON blob; `/vacancies?sort=date`. | none | no | ✅ |
| 5 | **zarplata.ru** | jobs | httpx direct; SSR Redux + `JobPosting` LD; `order_by=publication_time`. **White-label over hh.ru backend** (HH acquired 2020) → ≈ HH with geo. | DDoS-Guard (passive) | no | ✅ |
| 6 | **fl.ru** | orders | httpx RSS `all.xml` (+`category=5`/`31`); numeric id from link; card budget from `Product` LD+JSON. | DDoS-Guard | no | ✅ |
| 7 | **kwork.ru** | orders | httpx `POST /projects` (`X-Requested-With`), `data.pagination.data[]`; `c=41` (Скрипты/боты/Python), `c=11` (Программирование). | QRATOR | no | ✅ |
| 8 | **youdo.com** | orders | httpx internal API `POST /api/tasks/tasks/` `{status:opened,categories:[…]}`; card `GET /api/tasks/task/{id}/`. HTML is JS-challenged, API is not. | ServicePipe (HTML only) | no | ✅ |
| 9 | **rabota.ru** | jobs | **BLOCKED anonymously** — Nuxt SPA, vacancy data loads only after reCAPTCHA v2+v3; official API = OAuth2. | reCAPTCHA + QRATOR | — | ❌ needs OAuth2 or captcha-solver |

**Dropped:** Habr Freelance (`freelance.habr.com`) — permanently closed 2026-02-28 (HTTP 410). Telegram order-channels — deferred to the kurigram fleet path (not web scraping).

---

## 3. Prototype monitor (`prototype/monitor_proto.py`)

8 collectors + card parsers, fully anonymous (direct httpx for 7 sites; headless Playwright+stealth for hh only). CLI: `--runs N` (default 4), `--interval SEC` (default 900), `--smoke` (one cycle). Output JSON to `prototype/results/` — one `run_{n}_{UTC}.json` per pass + an `e2e_details_{UTC}.json` after the final run. Each site is isolated (one failure can't break the others).

### 3.1 Cross-run churn — 4 runs × 15 min (2026-06-19 09:34–10:21 UTC)

New (previously-unseen) items appearing each cycle — this is the dedup/recency validation:

| site | r1 | r2 | r3 | r4 | new@2 | new@3 | new@4 | unique/4 |
|------|----|----|----|----|-------|-------|-------|----------|
| hh | 25 | 25 | 25 | 25 | 1 | 3 | 2 | 31 |
| avito | 30 | 30 | 30 | 30 | 0 | 1 | 0 | 31 |
| superjob | 25 | 25 | 25 | 25 | 1 | 1 | 0 | 27 |
| habr | 25 | 25 | 25 | 25 | 1 | 7 | 1 | 34 |
| zarplata | 30 | 30 | 30 | 30 | 1 | 0 | 1 | 32 |
| fl | 50 | 50 | 50 | 50 | 5 | 2 | 1 | 58 |
| kwork | 24 | 24 | 24 | 24 | 0 | 4 | 0 | 28 |
| youdo | 50 | 50 | 50 | 50 | 0 | 0 | 0 | 50 |

All sites show believable low single-digit churn over the hour — exactly what a monitor needs. **avito** is the key validation: an earlier version (un-filtered `all/vakansii` + non-canonical id) showed **30/30/30 new = 100% turnover** (dedup broken); switching to the relevant tag feed + numeric ids fixed it to 0/1/0. Populated `date` fields (added during fixes) are the prerequisite that makes "new item" detection meaningful on superjob/avito/fl/youdo/habr.

### 3.2 Card-parse coverage (5 cards/site sampled — `prototype/card_test/card_parse_results.json`)

`N/A` = field not applicable to that site.

| site | title | amount | description | company | date | location | skills | url |
|------|-------|--------|-------------|---------|------|----------|--------|-----|
| hh | 5/5 | 1/5 | 5/5 | 5/5 | 5/5 | 0/5 | 0/5 | 5/5 |
| avito | 5/5 | 0/5 | 5/5 | 0/5 | 0/5 | 5/5 | N/A | 5/5 |
| superjob | 5/5 | 1/5 | 5/5 | 5/5 | 5/5 | 5/5 | N/A | 5/5 |
| habr | 5/5 | 0/5 | 5/5 | 0/5 | 5/5 | N/A | 5/5 | 5/5 |
| zarplata | 5/5 | 3/5 | 5/5 | 5/5 | N/A | N/A | N/A | 5/5 |
| fl | 5/5 | 0/5† | 5/5 | N/A | N/A | N/A | N/A | 5/5 |
| kwork | 5/5 | 5/5 | 5/5 | N/A | N/A | N/A | N/A | 5/5 |
| youdo | 5/5 | 5/5 | 5/5 | N/A | 5/5 | N/A | N/A | 5/5 |

Most empties are **genuine** (the item posted no salary / anonymous employer), not parser gaps:
- `† fl amount 0/5` here is genuine (these 5 were "по договорённости"); the budget parser is proven on 5 budget-bearing items (`card_test/fl_budget_evidence.json`, e.g. `5510268 → "7000 RUB"`).
- Real **parser gaps** remaining: `hh skills` (extracted internally, not surfaced in the return dict — trivial), `hh location` (site-optional field), `avito date` (item `time.date` empty on sampled pages).

---

## 4. Cross-cutting findings

- **Stealth Playwright defeats DDoS-Guard / QRATOR with `headless=True` and no proxy** (hh, validated). A proxy can *hurt* — it shifts geo (breaks hh `area=1`, switches zarplata's city subdomain). **Rule: try direct first, proxy only when blocked.**
- **Most RU job/order sites embed the full listing as JSON in the SSR HTML** (`data-mfe-state` / `data-ssr-state` / `APP_STATE` / Redux) **or expose an anonymous internal JSON API** (kwork `POST /projects`, youdo `/api/tasks/`). So **plain httpx usually beats a headless browser** — only hh needed Playwright.
- **JSON-LD vs APP_STATE ordering** (superjob): JSON-LD `ItemList` is relevance/promoted-ordered; the true date-sorted list lives in `APP_STATE` — use the latter for recency monitoring.
- **Canonical/numeric ids + populated dates are mandatory** for dedup and "new item" detection (the avito firehose lesson).

---

## 5. Limitations / known gaps

- **rabota.ru** — blocked anonymously (needs OAuth2 token or a captcha-solver).
- **hh.ru** — HTML works anon via Playwright, but the cleaner `api.hh.ru` path needs a free `dev.hh.ru` OAuth app token.
- **superjob.ru** — its "Python" keyword is loose (matches sysadmin posts mentioning Python); ordering/dates are correct, but strict dev-only results would need a title-level relevance filter.
- **zarplata.ru** is redundant with **hh.ru** (same backend) — monitor one, not both, unless geo-targeting differs.
- Minor parser gaps: hh `skills`/`location`, avito `date` (§3.2).
- Anti-bot postures can tighten; all "passive" verdicts are point-in-time (2026-06-18/19).

---

## 6. Artifact map

```
Atomic-Scraper-Service/experiment_monitoring/
  experiment-hh/  experiment-avito/  experiment-superjob/  experiment-habr/
  experiment-zarplata/ (experiment-rabota-zarplata)  experiment-fl/  experiment-kwork/  experiment-youdo/
      └─ per-site probes + working parser scripts + samples/  (proxy_client.py in experiment-hh)
  prototype/
      monitor_proto.py            # unified 8-site collectors + card parsers (CLI)
      results/  run_{1..4}_*.json + e2e_details_*.json
      card_test/  card_parse_results.json + fl_budget_evidence.json
  EXPERIMENTS-REPORT.md           # this file

own_knowledge_base/wiki/auto-monitor/
  auto-research-{hh,avito,superjob,habr,rabota-zarplata,fl,kwork,youdo}.md   # per-site verified reports
  auto-research-site-landscape.md                                            # RU site survey
own_knowledge_base/15-Auto-Monitor/Organizations/                            # RU out-staff + foreign crypto-friendly seed lists
```

---

## 7. Recommended next steps (monitor → production)

1. **Relevance/scoring layer** — feed each collected item to the LLM agent to score against Ivan's profile (the monitoring stage is now reliable; quality filtering is the next layer). This also subsumes superjob's loose-keyword issue.
2. **Notification** — wire scored hits to a channel (email vs TG bot still undecided given RU TG instability).
3. **Persistence + scheduling** — move dedup state to a DB and run on a real scheduler instead of the prototype's in-process loop.
4. **Close the minor gaps** — surface hh `skills`, fix avito `date`.
5. **Optional escalations** — hh OAuth token (cleaner than Playwright), rabota.ru OAuth2/captcha, kwork/fl authenticated paths for richer fields.
