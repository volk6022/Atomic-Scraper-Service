# Scraping and Parsing Yandex Maps (Яндекс.Карты) for Business Data — A Comprehensive Technical Guide (2025/2026)

This report surveys every realistic option for extracting organization (business) data from Yandex Maps, ordered roughly from lowest to highest complexity, with the trade-offs of each path. It targets a use case oriented to Russia / Saint Petersburg, where Yandex Maps is the dominant local-business directory along with 2GIS.

---

## 1. Executive summary and recommendation matrix

| Approach | Setup effort | Operating cost | Reliability | Legal risk | Best for |
|---|---|---|---|---|---|
| **Official Places HTTP API (Geosearch)** | Low | High (annual prepaid contract, RUB) | Very high | None | Address/POI lookup, modest-volume B2B prospecting where saving data is *not* required |
| **Yandex.Cloud Search API + MapKit SDK** | Medium | Medium–High | High | Low | Mobile apps, embedded maps |
| **Third-party "unofficial" APIs (Apify, Bright Data, SerpApi, Oxylabs, Crawlbase, Thordata)** | Very low | Pay-per-result ($2–10 / 1k places) | High | Shifts to vendor; Yandex ToS still implicated | Quick PoCs, one-off datasets, moderate ongoing volume |
| **Direct HTTP scraping of `search-maps.yandex.ru` / internal `fullobjects/1.x`** | Medium | Proxy costs only | Medium | Moderate (ToS) | Cost-sensitive moderate volume, R&D |
| **Headless browser automation (Selenium / Playwright / Puppeteer)** | High | Proxy + compute | Medium (breaks on redesigns) | Moderate | Reviews scraping (only browser sees them), reliable but slow |
| **Hybrid: browser to bootstrap + replay XHR JSON** | High | Lower than full browser | Higher than pure scraping | Moderate | Long-running production scrapers |
| **Self-hosted distributed cluster with proxy rotation + CAPTCHA solver** | Very high | High | High once stable | Highest | Large-scale (>1M orgs), continuous refresh |

**For a Saint Petersburg-focused medical/business directory project**, the realistic stack is: (a) **headless browser + residential proxy pool + replay of internal JSON endpoints**, optionally seeded by the **official Geosearch API** for coordinate-bounded discovery, with results normalized into PostgreSQL + PostGIS. If a managed alternative is acceptable, the **Apify actors** `m_mamaev/yandex-maps-places-scraper` and `zen-studio/yandex-maps-scraper` provide turnkey access to 30–60+ fields including reviews on a pay-per-result basis.

---

## 2. Official Yandex Maps API ecosystem

Yandex offers a family of commercial APIs under `yandex.com/maps-api/`. The relevant products for business-directory extraction are:

### 2.1 Places HTTP API (a.k.a. Geosearch / Organization Search API)
- Endpoint: `https://search-maps.yandex.ru/v1/?apikey=<KEY>&text=<query>&type=biz&lang=ru_RU&results=<N>`
- Knowledge base: "more than 13 million active organizations across Russia, the CIS and Turkey, updated daily" per Yandex's own product page.
- **Hard limits**
  - Up to **50 requests/second** (client+server combined).
  - **Maximum 100 results per query**, ranked by relevance — *you cannot page through every organization in a city*.
  - Total daily limit determined by paid tier; overage billed per 1 000-request bucket, rounded up.
- **Output fields** (officially supported, per docs at `yandex.com/dev/maps/geosearch/doc/concepts/response_structure_business-docpage/`):
  - `id` (business OID), `name`, `address`, `url` (website), `Categories[]`, `Phones[]`, `Hours` (incl. `TwentyFourHours`/`Intervals`), `geometry` (longitude, latitude). Yandex explicitly warns that other undocumented response fields "might not be supported in the future."
- **License model — critical caveat**: Only a **basic license** is offered. The terms forbid **saving or modifying the data**: requests may be cached up to 30 days, but persisting a derivative database of organizations violates the license. (Other Yandex APIs offer "Advanced" licenses permitting storage; the Organization Search API does not.) This is the single largest reason most real projects move off the official API.
- **Pricing**: prepaid **annual** contract in RUB, only via the Developer Dashboard. Exact rouble figures are published in non-public tariff PDFs and quoted via `api-maps@yandex-team.ru`. A free trial is offered only to customers committing to ≥10 M annual requests for any tool and ≥250 k MAU on MapKit; smaller pilots are negotiated case-by-case. Corporate emails are not accepted at registration — a Yandex ID is mandatory.
- **Auth**: API key passed as `?apikey=…` query parameter (no OAuth, no signed requests).
- **Search restrictions worth noting**:
  - You can pass a bounding box (`bbox` / `ll` + `spn`) to bias results, but the API still returns "the ones it considers best matches," not an exhaustive enumeration. Tiling many small bboxes and de-duplicating by `id` is the standard workaround.
  - Supports searches by name, address, phone number, INN/TIN, category, services, hours.

### 2.2 Adjacent official products that *do not* solve directory extraction
- **JavaScript API** (free up to 2.5 M requests/year). Used to embed maps; the bundled `SearchControl` calls Geosearch under the hood and counts against your quota. Not a bulk-extraction surface.
- **Geocoder HTTP API** (`https://geocode-maps.yandex.ru/1.x/`) — address↔coordinates only, no business data.
- **MapKit SDK** (iOS/Android/Flutter) — priced per MAU, free up to 25 000 MAU. The open-source [`yandex/yandex_maps_mapkit`](https://github.com/yandex/yandex_maps_mapkit) repository is the official binding but is targeted at app integration, not server-side scraping.
- **Yandex Cloud Search API** (`yandex.cloud/en/services/search-api`) — general web SERP, not Maps.

**Bottom line on the official API**: best fit when you need a *trustworthy* address-to-business lookup as part of a product (e.g., delivery checkout, B2B prospecting form), not when you need a re-usable database of every clinic in Saint Petersburg.

---

## 3. Unofficial endpoints exposed by the Yandex Maps web app

The public web app (`yandex.ru/maps/`, `yandex.com/maps/`) is a single-page React/BEM application that talks to several internal JSON endpoints. Community scrapers, including the Apify actors and the GitHub projects below, use them:

- `https://yandex.ru/maps/api/search` — receives the user query and bbox, returns ranked organization snippets.
- `https://search-maps.yandex.ru/v1/` (the same Geosearch surface, but the web app calls it with a session token rather than an apikey).
- `https://yandex.ru/maps/api/business/fetchReviews` — paginated reviews (`businessId`, `from`, `count`, `ranking=by_time|by_rating`). Returns up to 50 reviews per page in JSON.
- `https://yandex.ru/maps/api/business/fetchPhotos` — paginated photo URLs.
- The `fullobjects/1.x` snippet flag exposes menu data (used by Apify's `includeMenu` option).
- Each organization page exists at `https://yandex.ru/maps/org/<numeric_business_oid>/` (the `business_oid` is the unique identifier).

These endpoints are **undocumented, unauthenticated for the most part, and rate-limited aggressively by IP fingerprinting**. They are not stable across redesigns — community projects report needing maintenance every 6–12 months.

---

## 4. Data extraction surface — what is accessible and what is not

### 4.1 Accessible (via web scraping)
| Field | Source | Notes |
|---|---|---|
| Organization name | search + org card | Reliable |
| Address (text + components) | search + org card | Includes admin areas, postal code, street, building |
| Geo coordinates (lat/lon) | search JSON | High precision |
| Yandex business OID | URL / search response | Stable identifier, foreign-key candidate |
| Categories (multi-valued) | org card | Yandex rubric tree |
| Phone numbers | org card | One or many; sometimes obfuscated behind a "show phone" click that triggers a JSON request — must be replayed in browser automation |
| Website URL | org card | Often present, sometimes with `?yclid=` (Yandex Direct tracking) |
| Email | org card | **Not always present**; many businesses do not publish an email. Cannot be relied upon |
| Business hours (per day, 24h flag, intervals) | org card | Structured |
| Description, services list (menu, prices) | org card / `fullobjects/1.x` | Restaurants & beauty salons have rich menus |
| Aggregate rating, review count | org card | Float 1.0–5.0, integer count |
| Reviews (text, rating, author handle, timestamp, business reply) | `fetchReviews` JSON | Up to ~all visible reviews (Apify reports 1 000 reviews/30 s); newer reviews easy, deep history paginated |
| Photos (URLs + size templates) | `fetchPhotos` JSON | Hosted on `avatars.mds.yandex.net` with `{size}` templates (XXL, M_height, etc.) |
| Awards/tags (e.g., "Хорошее место") | org card | Boolean tags |
| Social links | org card | VK, Telegram, etc., where the business added them |

### 4.2 Protected / unreliable
- **User profiles** beyond the public alias and avatar — Yandex deliberately limits PII visibility.
- **Exact review counts per author** — only aggregate counts are surfaced.
- **Email addresses** — frequently absent because Yandex never required them.
- **Private booking/menu pricing for some categories** — partially hidden behind partner-only integrations (e.g., Yandex Eda for restaurants is a separate scrape target).
- **Phones marked as click-to-reveal** — require an extra JSON request triggered by a session that already loaded the org page; the simple cURL approach often returns "Загрузка…" placeholders.
- **Historical edits** — only the current state is visible.

---

## 5. Third-party APIs and SaaS aggregators (2025/2026 status)

These services do the proxy management, CAPTCHA solving, and HTML/JSON parsing for you and bill on volume.

| Provider | Product | Pricing model (May 2026) | Strengths | Caveats |
|---|---|---|---|---|
| **Apify – `m_mamaev/yandex-maps-places-scraper`** | "Yandex Maps Places Scraper" | Pay-per-result; ~$5–10 / 1 000 places (varies by run config) | 30+ fields incl. menu, photos, reviews; supports `organizationIds` API-only mode; HTML map output | Closed-source actor; bound to Apify platform |
| **Apify – `zen-studio/yandex-maps-scraper`** | "Unofficial Yandex Maps API" | Pay-per-result | 63+ fields, AI review summaries, menu prices, **no browser** (claims direct API) | Closed-source; Russia/Turkey/CIS focus |
| **Apify – `zen-studio/yandex-maps-reviews-scraper`** | Reviews-only | Pay-per-result, ~$X / 1 000 reviews | 35 fields per review incl. business replies and AI translations; supports new short-share URLs (CPqI…) noted in changelog Feb 2026 | Reviews only |
| **Apify – `parsebird/yandex-maps-reviews-scraper`** | Reviews-only | Pay-per-result | Alternative actor | Smaller scale |
| **Apify – `m_mamaev/yandex-maps-orchestrator`** | Orchestrator | Wraps places scraper | Runs many query/location combos in one job | Adds Apify task layer |
| **Bright Data – Web Unlocker / SERP API** | API + proxies | Per-request, ~$1.5–3 / 1 000 | Yandex SmartCaptcha solver included (`Captcha.setAutoSolve`); enterprise SLA | Designed for Yandex SERP — Maps coverage is via Unlocker (raw HTML, you parse) |
| **Oxylabs Web Scraper API** | "Yandex Search API" | Per-request | Geo-targeting, residential pool | Yandex SERP focus; Maps requires custom URL |
| **SerpApi** | `engine=yandex` | Per-search | Cached results free; clean JSON | Web SERP, not Maps directly |
| **Crawlbase / WebScrapingAPI / SearchApi.io / Thordata** | Generic SERP/Unlocker | Per-request | Decent baseline | Not Yandex-Maps-specialized |
| **RapidAPI – "Yandex Scraper" (omkarcloud)** | API | 50 free / month, then $9 / 1 000 | Search only | Not Maps |

The cheapest *managed* option that is purpose-built for Yandex Maps (places + reviews + photos + menu) is the Apify actors; everything else either gives you raw HTML (Bright Data Unlocker, Oxylabs, Crawlbase) or only covers web search results.

---

## 6. Python and Node.js libraries

### 6.1 Python — actively useful (2025)
- [`arsenyvolodko/yandex-maps-reviews-parser`](https://github.com/arsenyvolodko/yandex-maps-reviews-parser) — Selenium + BeautifulSoup, fetches reviews by `organisation_id` or by name (e.g., `'Санкт-Петербург, ресторан Terrassa'`). Returns `Review` instances with text and rating. Last updated 2024.
- [`artemsteshenko/parser_maps`](https://github.com/artemsteshenko/parser_maps) — Selenium-based, two-stage (`link_parser.py` then `info_parser.py`); takes `city`, `district`, `type_org`. Designed for Moscow but works for SPB by parameter.
- [`erdzhemadinov/PARSING_DISTRIBUTION_CENTRES`](https://github.com/erdzhemadinov/PARSING_DISTRIBUTION_CENTRES) — Selenium across regions, `regions.xlsx` for region codes.
- [`chernyshov-dp/YMapsGrabber`](https://github.com/chernyshov-dp/YMapsGrabber) — 17 ⭐, **archived Feb 2024**. Selenium + Safari driver, collects name/address/site/hours/category-card/menu/rating/reviews. Useful as a reference, not actively maintained.
- [`omkarcloud/yandex-scraper`](https://github.com/omkarcloud/yandex-scraper) — Botasaurus-based; Yandex SERP, not Maps directly.
- [`asluchevskiy/yandex-maps-spider-example`](https://github.com/asluchevskiy/yandex-maps-spider-example) — minimal Scrapy example.
- [`OwlSoul/YandexTransportProxy`](https://github.com/OwlSoul/YandexTransportProxy) — not for businesses, but the **architectural pattern is the gold standard**: Selenium + headless Chromium boots up Yandex.Maps, the proxy server extracts JSON straight from the browser's network cache for the internal `masstransit` API. The README explicitly explains why cURL fails (instant CAPTCHA, hidden AJAX) and why browser-in-the-loop with cache extraction is the durable strategy. Distributed as a Docker image.
- "yandex-maps" PyPI: there are several similarly named packages (`yandex_maps`, `yandex-geocoder`, async transport clients) — none of them parse organization listings.
- `YMRP` (Yandex map resources parser, 2025) — Playwright + BeautifulSoup, pypi-distributed; small but recently updated.

### 6.2 Node.js
- No widely adopted Maps-organizations scraper; community projects are mostly thin wrappers over the JS API (`react-yandex-maps`, `vue-yandex-maps`) for embedding, not scraping.
- A few one-off Puppeteer scripts exist for niche tasks (e.g., extracting traffic-aware route durations from the web interface where the public API doesn't expose them).
- Practical Node.js path: use [`playwright`](https://playwright.dev) directly. Playwright handles three engines (Chromium, Firefox, WebKit), supports auto-waiting, parallel browser contexts, and integrates with proxy rotation and Docker.

### 6.3 Official SDK
- [`yandex/yandex_maps_mapkit`](https://github.com/yandex/yandex_maps_mapkit) — MapKit bindings published by Yandex; for app integration, not data extraction.

---

## 7. Anti-bot defenses and how they affect scraping

Yandex's anti-bot stack — **Yandex SmartCaptcha** (productized at `yandex.cloud/en/services/smartcaptcha` and used across Yandex properties) — is one of the strongest on the public web. Signals it weighs:

- **IP reputation**: datacenter ASNs, known VPN exit nodes, and shared residential proxies get challenged almost immediately. Residential or ISP proxies in Russia have the cleanest reputation.
- **Browser fingerprint**: Selenium's default Chrome flags (`navigator.webdriver=true`, missing `chrome` runtime, mismatched `Accept-Language`) are detected. Tools like `undetected-chromedriver`, `playwright-stealth`, or rebuilt Chromium are required.
- **Behavioral telemetry**: mouse movement velocity, scroll cadence, idle time between actions. Hitting Enter immediately after page load is a giveaway.
- **Request cadence**: bursts of identical-shape requests trigger checks; ~1 request/second per IP is a safe ceiling.
- **Cookie/session continuity**: a session that solves CAPTCHA once gets a long-lived "trusted" cookie (`yandex_login`, `yandexuid`, `Session_id`) that should be persisted and re-used.

**Challenge types delivered by SmartCaptcha**:
- Invisible/silent (most common when reputation is borderline)
- Text (distorted characters)
- Slider / puzzle
- Silhouette ("click the silhouettes in this order")
- Kaleidoscope (rotate fragments)

**Mitigation tiers**:
1. **Avoid triggering it** — residential RU proxies, realistic User-Agent, full TLS/HTTP2 fingerprint, low concurrency, randomized think-times, persistent cookies. Often enough at <1k requests/day.
2. **Solve with a third-party service** — 2Captcha and CapMonster both publish a `yandex` method that takes `sitekey` + `pageurl` and returns a token to inject; cost roughly $1–3 / 1 000 solves. Sample integration code is widely available on captchaforum.com.
3. **Solve with a commercial unlocker** — Bright Data's Browser API / Web Unlocker advertises automatic Yandex SmartCaptcha solving via the `Captcha.setAutoSolve` API and CDP events (`Captcha.detected`, `Captcha.solveFinished`). CaptchaKings, ScrapingBypass, and similar services compete in this niche.
4. **ML-based local solving** — feasible for text variants but Yandex updates the visual prompts regularly; not recommended unless you have an in-house CV team.

---

## 8. Self-hosted / on-premise architecture (recommended for Saint Petersburg medical-business scope)

### 8.1 Component diagram

```
┌──────────────────┐    ┌────────────────┐    ┌────────────────────┐
│ Seed Generator   │──▶ │ Job Queue       │──▶ │ Worker Pool         │
│ (cities,         │    │ (Redis / RabbitMQ)│  │ (Playwright in Docker)│
│  categories,     │    └────────────────┘    │ + proxy rotation    │
│  bbox tiles)     │                          └─────────┬───────────┘
└──────────────────┘                                    │
                                                        ▼
                                          ┌─────────────────────────┐
                                          │ Result Normalizer        │
                                          │ (de-dup by business_oid) │
                                          └──────────┬──────────────┘
                                                     ▼
                                          ┌─────────────────────────┐
                                          │ PostgreSQL + PostGIS    │
                                          │  (or MongoDB)           │
                                          └─────────────────────────┘
```

### 8.2 Recommended database schema (PostgreSQL + PostGIS)

```sql
CREATE EXTENSION postgis;

CREATE TABLE organization (
    business_oid     BIGINT PRIMARY KEY,        -- Yandex stable ID
    name             TEXT NOT NULL,
    address_text     TEXT,
    address_components JSONB,                   -- street, building, region, postal_code
    geom             GEOGRAPHY(POINT, 4326),    -- PostGIS lon/lat
    yandex_url       TEXT,
    website          TEXT,
    description      TEXT,
    rating           NUMERIC(2,1),
    reviews_count    INTEGER,
    first_seen       TIMESTAMPTZ DEFAULT now(),
    last_checked     TIMESTAMPTZ,
    raw              JSONB                       -- full snapshot for re-parsing
);
CREATE INDEX idx_org_geom ON organization USING GIST (geom);

CREATE TABLE phone (
    id            BIGSERIAL PRIMARY KEY,
    business_oid  BIGINT REFERENCES organization,
    type          TEXT,    -- phone | fax | whatsapp
    e164          TEXT
);

CREATE TABLE category (
    business_oid  BIGINT REFERENCES organization,
    rubric_id     INTEGER,
    name          TEXT,
    is_primary    BOOLEAN,
    PRIMARY KEY (business_oid, rubric_id)
);

CREATE TABLE hours (
    business_oid  BIGINT REFERENCES organization,
    day_of_week   SMALLINT,            -- 0..6
    is_24h        BOOLEAN,
    open_time     TIME,
    close_time    TIME,
    PRIMARY KEY (business_oid, day_of_week, open_time)
);

CREATE TABLE review (
    id            BIGSERIAL PRIMARY KEY,
    business_oid  BIGINT REFERENCES organization,
    yandex_review_id TEXT UNIQUE,
    author_alias  TEXT,
    rating        SMALLINT,
    text          TEXT,
    posted_at     TIMESTAMPTZ,
    business_reply TEXT,
    business_reply_at TIMESTAMPTZ,
    fetched_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_review_business ON review (business_oid, posted_at DESC);

CREATE TABLE photo (
    id            BIGSERIAL PRIMARY KEY,
    business_oid  BIGINT REFERENCES organization,
    url_template  TEXT,                -- avatars.mds.yandex.net/.../{size}
    width         INTEGER, height INTEGER
);

CREATE TABLE crawl_log (
    id        BIGSERIAL PRIMARY KEY,
    business_oid BIGINT,
    ts        TIMESTAMPTZ DEFAULT now(),
    status    TEXT,                    -- ok | captcha | banned | http_5xx
    proxy     INET,
    duration_ms INT
);
```

For document-store-friendly teams, **MongoDB** can hold each org as a single denormalized document keyed by `business_oid` with a `2dsphere` index on `location`. PostgreSQL is recommended over MongoDB because geographic queries ("all clinics within 1 km of Nevsky Prospect 28") are far more expressive in PostGIS.

### 8.3 Dockerization
- Base image: `mcr.microsoft.com/playwright/python:v1.45.0-jammy` (or the Node variant). Ships with Chromium, Firefox, WebKit, and all required libs.
- Run worker containers with `--shm-size=2gb` to avoid Chromium crashing.
- One scheduler container (Python with `apscheduler` or `Celery beat`), N worker containers, one Postgres container, one Redis. `docker compose up --scale worker=10`.
- For proxy rotation, integrate a sidecar like [`mitmproxy`](https://mitmproxy.org/) configured with an upstream pool, or use the proxy vendor's API directly (Bright Data, Oxylabs, Soax, Smartproxy all expose RU residential pools).

### 8.4 Horizontal scaling without detection
Tactics that materially help:
1. **One persistent browser profile per proxy IP** for the lifetime of that IP (typically 10–30 minutes). Don't multiplex many proxies through one profile or you'll burn cookies fast.
2. **Geographic-affinity routing**: use RU residential IPs *from Saint Petersburg* if your target queries are SPB-bound. Yandex weighs IP geo against query region.
3. **`yandex.com` vs `yandex.ru`**: the `.com` variant is comparatively under-policed and accepts the `lr=` region parameter (e.g., `lr=2` for SPB) but returns the same business catalog.
4. **Stagger by category**: instead of "every business in SPB," queue by category × district tiles (~50–200 tiles for SPB) and randomize order. Each query returns ≤24 results in the web UI before requiring scroll-load.
5. **Respect the 100-item-per-search cap** — split queries by category or geographic tile to enumerate completely.
6. **Throttle to ~0.5–1 request/sec per IP** and add normal browsing actions (random scroll, hover) on a fraction of pages.
7. **Refresh strategy**: Yandex updates business data continuously. A weekly recrawl of `last_checked < now() - 7d` items, prioritized by category importance, is typical.

---

## 9. Saint Petersburg-specific guidance
- SPB-only URLs accept the slug form `https://yandex.ru/maps/2/saint-petersburg/search/<query>` (region ID `2`). This pre-biases all results and avoids querying Russia-wide.
- The Geosearch API region parameter is the same `lr=2`. For complete category enumeration in SPB, the standard approach is bbox-tiling (4–8 zoom-13 tiles cover SPB), retrieving up to 100 results per tile per category, and de-duplicating by `business_oid`.
- Yandex carries roughly 100–150 k organizations in greater SPB across all categories. The "medical institutions СПб + ЛО" sub-scope of the use case (clinics, dental practices, diagnostic centers, pharmacies) is in the range of 8–15 k organizations — well within reach of a single moderately sized scraping cluster.

---

## 10. Real-world end-to-end implementation recipes

### 10.1 Recipe A — Lowest complexity (one-off dataset, hours of effort)
Use **Apify's `m_mamaev/yandex-maps-places-scraper`** plus **`zen-studio/yandex-maps-reviews-scraper`**:
```python
from apify_client import ApifyClient
client = ApifyClient("YOUR_APIFY_TOKEN")
run = client.actor("m_mamaev/yandex-maps-places-scraper").call(run_input={
    "query": "стоматология",
    "locations": ["Санкт-Петербург"],
    "maxItems": 5000,
    "language": "russian",
    "includeMenu": False,
    "maxPhotos": 5,
})
for item in client.dataset(run["defaultDatasetId"]).iterate_items():
    upsert_to_postgres(item)
```
Cost order-of-magnitude: 5 000 dental practices × ~$0.005–0.01 each ≈ $25–50. Includes phones, addresses, categories, hours, ratings, reviews count, mainPhotoUrl, website. For full review text, pipe the resulting `business_oid` values to the reviews actor.

### 10.2 Recipe B — Medium complexity (self-hosted, ongoing)
Stack: Python + Playwright + undetected-playwright + residential RU proxies + Postgres/PostGIS + Redis.

Key implementation points:
1. **Browser bootstrap**: launch headless Chromium with `playwright-stealth`, set Russian Accept-Language, mount cookies from a persistent profile per proxy.
2. **Search phase**: navigate to `https://yandex.ru/maps/2/saint-petersburg/search/<URL-encoded query>`, intercept the XHR to `/maps/api/search`, JSON-parse the response. Repeat with `?page=N` and bbox shifts.
3. **Detail phase**: for each `business_oid`, intercept the `fullobjects/1.x` response and the org-card HTML in parallel.
4. **Reviews phase**: hit `https://yandex.ru/maps/api/business/fetchReviews?businessId=<oid>&from=0&count=50&ranking=by_time`, paginate.
5. **CAPTCHA handling**: on detection (DOM contains `.CheckboxCaptcha-Anchor` or response status 429 with `<title>` matching SmartCaptcha), enqueue the task back to Redis with a delay, mark the proxy IP cooled-down for 30 minutes, rotate.
6. **De-duplication**: use `business_oid` as primary key; merge new fields into existing rows via `ON CONFLICT (business_oid) DO UPDATE`.

The architecture of `OwlSoul/YandexTransportProxy` (Selenium + Chromium in headless Docker, reading JSON from the browser cache, exposing a clean local API) is the closest open-source reference and is recommended reading before building.

### 10.3 Recipe C — Maximum reliability (commercial scale)
- Use **Bright Data Browser API** or **Browserless.io BrowserQL** as a remote stealth-Chrome endpoint with built-in CAPTCHA solving (`Captcha.setAutoSolve`).
- Cluster N workers behind it (workers can be cheap CPU-only containers since the browser runs remotely).
- All scraping logic stays in Python/Node code; the unlocker handles proxies, fingerprinting, and captcha. Cost is per-session-minute.
- Combine with a 2Captcha fallback for cases the auto-solver misses.

---

## 11. Legal and ethical considerations

### 11.1 Yandex Terms of Service
- The Maps API terms (Organization Search) **explicitly prohibit saving or modifying** data returned by the API. This is the central reason most data-collection projects do not use the official API to build a database.
- The Yandex Maps web application's `robots.txt` and the general Yandex User Agreement prohibit automated access to non-API endpoints. Violation is a breach of contract; in practice Yandex enforces it by IP blocking, CAPTCHA, and (rarely, for very heavy abuse) cease-and-desist letters.
- Yandex offers a paid "Advanced" license for *some* APIs (JavaScript API/Geocoder) that permits storing data; no such option exists for the Organization Search API as of the most recent published tariffs.

### 11.2 Russian Federal Law 152-FZ (Personal Data)
- 152-FZ regulates **personal data of identifiable individuals**. Business directory data (organization name, address, website, opening hours, rating, OID) is *not* personal data — these are facts about legal entities.
- **Reviews are a gray area**: a review author's public alias plus photo plus textual self-disclosure can become personal data in aggregate. The March 2021 amendments to 152-FZ introduced the concept of "personal data made publicly available" (PDD): even data the subject made public requires *specific, separate consent* from them before another operator can disseminate it further. If you re-publish review text together with author handles, you are almost certainly processing PDD without the consent the amendments now require. Mitigations: store reviews but do not re-publish them externally; or hash/strip author identifiers; or rely on legitimate-interest arguments (weaker since 2021).
- **Data localization (Article 18(5))**: if you collect personal data of Russian citizens, the *first* recording, systematization, accumulation, storage, modification, and extraction must occur on servers physically inside Russia. This applies even to foreign operators if the collection is targeted at Russian users or based on Russian-user consent. A scraper running outside Russia that stores review-author handles likely triggers this requirement. Regulator: Roskomnadzor.
- **Direct marketing**: 38-FZ "On Advertising" prohibits unsolicited marketing communications (SMS/email/calls) without prior express consent. Scraping phones from Yandex Maps for cold outreach is technically permissible (organization phones are public), but contacting individuals via those numbers for marketing without consent is sanctionable.
- **Sanctions**: administrative fines under the Russian Code of Administrative Infractions (Article 13.11); 2022 amendments substantially raised them, and 2024 amendments introduced turnover-based fines for repeat offenses. Criminal liability is now possible for disclosing personal data of "protected persons" (state officials).

### 11.3 Practical risk profile
- **For B2B prospecting using only organization-level data (name, address, phone, website, hours, category)**: low legal risk; Yandex ToS is the main concern.
- **For competitive review monitoring storing review text + author handles**: moderate risk under 152-FZ post-2021 amendments; consult Russian counsel if commercializing.
- **For commercial resale of a scraped Yandex Maps dataset**: high risk on multiple fronts (ToS, database-sui-generis rights, 152-FZ if reviews included). Most lawful resellers license from Yandex Business Directory partners or 2GIS instead.
- **Anyone operating from outside Russia and exporting data abroad**: under the 2022–2023 amendments (266-FZ), cross-border transfer of personal data requires prior notification to Roskomnadzor.

### 11.4 Geopolitical considerations
Since Yandex N.V.'s 2024 divestiture of its Russian assets to a Russian investor consortium (≈$5.2 B deal), the Russian Yandex business is operated independently from any non-Russian entity. International payment of the API contract, sanctions exposure (for entities operating under EU/US/UK sanction regimes), and Yandex's continued cooperation with Russian regulators are all factors that may affect whether and how a non-Russian organization can lawfully use the official API.

---

## 12. Final actionable shortlist

For the described use case (SPB-focused, medical/business directory, recurring refresh, MySQL/Mongo/Postgres target), the most defensible plan is:

1. **Discovery layer**: stay off Selenium for discovery. Use bbox-tiled queries against the public `https://yandex.ru/maps/api/search` JSON endpoint via Playwright with one residential RU IP per browser context. ~50 bbox tiles × 5 categories = 250 queries to enumerate every clinic.
2. **Enrichment layer**: for each discovered `business_oid`, fetch the org card and `fullobjects/1.x` payload in a fresh tab. Persist the raw JSON in `organization.raw` so you can re-parse if Yandex changes schema.
3. **Reviews layer**: nightly cron pulls 50–200 newest reviews per org via the reviews JSON endpoint, upserts by `yandex_review_id`. This is the only path that scales — the official Geosearch API does not return reviews at all.
4. **Storage**: PostgreSQL 16 + PostGIS, schema as in §8.2, hosted inside Russia if storing any personal data (review authors).
5. **Anti-bot**: 10–30 RU residential proxies, undetected Playwright, 2Captcha (or Bright Data Browser API) as fallback. Target steady-state ~5 orgs/minute per worker, scale horizontally.
6. **Fallback / acceleration**: when you need a one-shot bulk pull, the Apify actor `m_mamaev/yandex-maps-places-scraper` will deliver the data in hours and the per-result cost is competitive with the engineering time saved.
7. **Legal hygiene**: do not republish review author handles; do not use scraped individual contacts for unsolicited marketing; document a legitimate-interest assessment for any personal data you do retain; if commercializing, license the data from a Yandex Business Directory partner instead of scraping.

This combination provides the best blend of completeness, cost, and survivability against Yandex's evolving anti-bot defenses, while keeping legal exposure within manageable bounds for an internal directory project.