# Итерация 2 — типо-зависимый глубокий ресёрч: отчёт о проделанном

**Дата:** 2026-06-07 … 2026-06-08
**Цель:** превратить экспериментальный пайплайн (парсинг Я.Карт → LLM-обогащение)
в типо-зависимый глубокий ресёрч с детерминированным prefill, перенести находки в
код сервиса и проверить на масштабе.

План целиком: `~/.claude/plans/foamy-sleeping-pretzel.md` (5 воркстримов A–E).

---

## 1. Workstream E — порт парсинга Яндекс.Карт в сервис ✅
Было: обе акции ходили через **браузер (Playwright)** — extract (SSR со страницы)
и reviews (observe-and-replay `fetchReviews`, нестабильно). Стало — чистый **httpx + SSR**
(≈7× дешевле, стабильнее).

- **`/card`** (новый эндпоинт + `YandexMapsCardAction` + модель `YandexOrgCard`):
  `socialLinks` (VK/TG/WA + хэндлы), `description`, телефоны, часы, рейтинг — первичный
  источник соц-DM-каналов (в выдаче поиска их нет, в карточке есть).
- **`/reviews`** переписан: браузер → httpx SSR `?page=N&ranking=…`, стоп по
  `since_months`/`max_count`. Браузер остался фолбэком на капчу (`_execute_browser`).
- **`/extract`** → httpx-SSR-first (браузер — фолбэк). Подтверждено: 24-25 орг/вызов.
- Общие httpx-хелперы: `_http_get_html` (ротация прокси, dead-proxy-skip, captcha),
  `_iter_big_blobs`/`_ssr_items_from_html` (скан всех `<script>`-блобов — фикс бага
  «первый блоб не тот»).

**Прокси:** пул `puls-proxy` деградировал (6/20 live, concurrency-cap). Реализован
**in-process dead-proxy-skip** (TTL 120с, бенч только на connect-fail) + короткий
connect-timeout → надёжность без траты бюджета. Прогрев показал 15/20 портов
восстанавливаются со временем.

**Файлы:** `src/actions/yandex_maps.py`, `src/api/routers/yandex_maps.py`,
`src/domain/models/yandex_card.py` (new), `src/domain/models/requests.py`.

---

## 2. Ретраи на интернет-тулах (+1) ✅
- web_serp (SearXNG): `SEARXNG_MAX_RETRIES` 2 → **3** (`config.py`).
- web_scrape: ретрай 1 → **2 попытки** со сменой прокси (`research/tools.py`) —
  подтверждено в логах (`scrape_url attempt 1/2, 2/2`).
- grid extract/reviews (`01_scrape_yandex.py`): → 3 попытки.
- research-launch POST (`02_research_orgs.py`): → 3 попытки.
Результат: **0 провалов на 132 ресёрча**.

---

## 3. Масштабный прогон 750m ✅
Зона: центр СПб, радиус **750м**, сетка **250м / нахлёст 25м** (эфф. 225м).
- Парсинг: 925 вызовов (37×25 кат) → **144 орг**, ~4с/вызов, **0 ошибок**.
- Отзывы: **141/144** (httpx SSR, 6мес/≤50), 0 ошибок.
- Дедуп: 144 → **132 уник**.
- Ресёрч: **132/132 completed, 0 провалов** (mode=quality, concurrency=3,
  отзывы переданы в query агента). Медиана 508с/орг.

### Глубина: НОВЫЙ (132) vs 517-бэкап
| маркер | НОВЫЙ | 517 | Δ |
|---|---|---|---|
| **problems_signals ср/карту** | **3.21** | 0.33 | **×10** |
| карт с соцсетями | **92%** | 81% | +11 пп |
| social ср/карту | 2.44 | 1.52 | +60% |
| employees упомянуты | 27% | 9% | ×3 |
| founded / revenue | 39% / 4% | 25% / 1% | ↑ |
| **inn_ogrn** | 4% | 4% | = (до A+C) |

Заполняемость: what_they_do 100%, social 92%, problems 92%, scale 96%, websites 92%,
phones 87%, emails 58%. Критик медиана 7.5. Стоимость: медиана ~126k токенов / 504с.
Главный вывод: **отзывы→агент дают ×10 по problems_signals** — это «боль клиента»
для персонализации оффера. Отчёт: `data_750m/REPORT_run_750m.md`.

---

## 4. Workstream A+C — классификация + типовые схемы + ИНН/реестры ✅
**Новые модули (сервис):**
- `src/actions/research/org_taxonomy.py` — `classify_archetype()` (13 типов из
  Я.категории), `classify_size()` (micro/mid/chain), `wants_legal_entity()`.
- `src/actions/research/org_schemas.py` — `build_schema()`: база + per-archetype
  **deep_dive** + (C) **legal_entity** (ИНН/ОГРН/оборот/год/сотрудники), только для
  findable-типов.

**Caller (`02_research_orgs.py`):** типовая схема на орг; query несёт строку
«УГЛУБИСЬ во внутреннюю специфику (тип)…» + «ЮРЛИЦО И РЕЕСТРЫ: rusprofile/checko/
list-org…»; size-hint для mid/chain. Override `YA_RESEARCH_DIR` для изолированных прогонов.

### Валидация (21 орг, `data_750m/research_ac/`)
| метрика | A+C | baseline |
|---|---|---|
| **ИНН найден (legal-типы)** | **83% (10/12)** | 4% |
| deep_dive заполнен | 90% карт, 2.8 поля/карту | — |
| токены (медиана) | 194k | 126k (**+54%**) |
| critic | 7.5 | 7.5 |

Полные данные ФНС у части (Принт салон: 12 сотр./64 млн ₽; ЛюбиЗуб: оборот 6.3 млн ₽).
legal_entity корректно пуст у микро-ритейла/еды/бьюти. 2/21 пустых карты (Лигал Лайн,
Кофестория). Отчёт: `data_750m/REPORT_AC_validation.md`.

---

## Что сделано / не сделано
| Воркстрим | Статус |
|---|---|
| **E** — Яндекс-парсинг в сервис | ✅ сделано, проверено |
| Ретраи +1 | ✅ сделано |
| Прогон 750m (132) | ✅ сделано |
| **A** — классификация + типовые схемы | ✅ сделано, валидировано (21) |
| **C** — ИНН/реестры | ✅ сделано, валидировано (4%→83%) |
| **B** — depth-критик + рефразер | ⬜ не начато |
| **D** — скорость (контекст-дисциплина, per-batch llama, np) | ⬜ не начато |
| Гибрид mid-run «уточнение» при submit | ⬜ отложено (категория даёт тип до-ран) |
| Прогон A+C на всех 132 | ⬜ не сделано (валидация на 21) |
| Порт в auto-monitor-ml-cv | ⬜ не начато |

## Открытые вопросы / следующее
- **D (скорость):** снять +54% налог токенов — элизия prefill/скрейпов
  (`RESEARCH_SOFT_ELIDE_AFTER_TURNS`, `RESEARCH_SCRAPE_BUDGET_CHARS`), per-batch
  llama-профили (short np=3 / deep np=1-2).
- **B (надёжность глубины):** depth-метрика в критике + чаще рефразер → закрыть
  2/21 пустых карты, калибровать ожидания по типу.
- Прогнать A+C на всех 132 для полной per-type статистики.

## Артефакты
- Код: `src/actions/yandex_maps.py`, `src/api/routers/yandex_maps.py`,
  `src/domain/models/yandex_card.py`, `requests.py`,
  `src/actions/research/org_taxonomy.py`, `org_schemas.py`,
  `src/core/config.py`, `src/actions/research/tools.py`,
  `yandex_enrichment_experiment/01_scrape_yandex.py`, `02_research_orgs.py`.
- Данные: `yandex_enrichment_experiment/data_750m/` (organizations/reviews/research/
  research_ac + 3 отчёта).
- Все изменения НЕ закоммичены (по умолчанию).

## Запуск/возобновление
```bash
docker compose up -d redis
pm2 start ecosystem.config.js          # или --only <app>; при router-mode баге:
                                       # pm2 delete llama-server && pm2 start ecosystem.config.js --only llama-server
# ресёрч (идемпотентно, пропускает готовые):
YA_DATA_DIR="$(pwd)/yandex_enrichment_experiment/data_750m" CONCURRENCY=3 \
  uv run python yandex_enrichment_experiment/02_research_orgs.py
```
