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
Кофестория). Отчёты: `data_750m/REPORT_AC_validation.md`, `REPORT_AC_detailed.md`
(парный разбор: реальный налог A+C +3% время / +28% токены, сконцентрирован в реестр-
охоте на «тёмные» юрлица law/print/auto).

---

## 5. Workstream D — скорость/стоимость + балансный конфиг ✅
Цель — снять токен-налог A+C без потери ИНН/глубины. Факторный прогон на 8 «дорогих»
орг (law/print/auto + контроли).

**Переосмысление по данным инференса** (`llm-inference-experiments/ctx_tps_sweep_report.md`):
активный контекст ресёрча = **15–30k** (p90 29k), НЕ 50–120k. Значит np=3 уже оптимален
(премиса плана о np=1/2 неверна), а `-c 195000` переразмерен ~4× → можно ужать до 108k и
включить q8_0 KV.

**Правки:** soft-law (law не пушит ИНН), cap≤2 на реестр-охоту, q8-профиль
(`ecosystem.llama-deep.config.js`, `-c 108000 -ctk/-ctv q8_0`, VRAM 7608/8192).

**Результаты (3-way, те же 8 орг):**
| конфиг | время | токены | ИНН all | auto | print+med | law | critic |
|---|---|---|---|---|---|---|---|
| A+C (q4,hard) | 111м | 2669k | 6/7 | 2/2 | 3/3 | 1/2 | 7.28 |
| D1 (q4,cap) | 76м | 1947k | 4/7 | 0/2 | 3/3 | 1/2 | 7.24 |
| **D2 (q8,cap)** | **52м** | **1223k** | **5/7** | **2/2** | 3/3 | 0/2 | 6.96 |

Находки: (1) **q8 не только качество — он дешевле** (D2 vs D1: −31% время/−37% токены,
т.к. точная KV-память = меньше холостых ходов; sweep этот агентный эффект не ловил);
(2) **q8 вернул auto-ИНН**, который q4+cap терял → cap=2 поднимать не нужно;
(3) soft-law срезал худшую «нору» (Лигал Лайн −432с/−198k), критик-просадка вся в law.

Инцидент: посреди эксперимента **лёг прокси-пул** (puls SOCKS5 auth rejected = исчерпана
квота трафика); первый D1 был невалиден (SearXNG 0 organic). После докупки +2 ГБ → 17/20
живых, перезапущено валидно. Урок: мониторить квоту прокси на длинных прогонах.

**Балансный конфиг (выбран): q8_0/`-c 108000`/np=3 + soft-law + cap≤2** — vs A+C **−53%
время, −54% токены**, ИНН auto/print/med держится. Отчёт: `data_750m/REPORT_D_experiment.md`.
Прогон всех **132** с этим конфигом → `research_final/` (в работе).

---

## Что сделано / не сделано
| Воркстрим | Статус |
|---|---|
| **E** — Яндекс-парсинг в сервис | ✅ сделано, проверено |
| Ретраи +1 | ✅ сделано |
| Прогон 750m (132) | ✅ сделано |
| **A** — классификация + типовые схемы | ✅ сделано, валидировано (21) |
| **C** — ИНН/реестры | ✅ сделано, валидировано (4%→83%) |
| **D** — скорость (cap, soft-law, q8-профиль) | ✅ сделано, балансный конфиг −53% время |
| **B** — depth-критик + рефразер | ⬜ не начато |
| Гибрид mid-run «уточнение» при submit | ⬜ отложено (категория даёт тип до-ран) |
| Прогон балансного конфига на всех 132 | 🔄 в работе (`research_final/`) |
| Порт в auto-monitor-ml-cv | ⬜ не начато |

## Открытые вопросы / следующее
- **Финальный digest на 132** (по завершении `research_final/`): подтвердить, что
  выигрыши A+C (ИНН 0→83%, deep_dive 90%, problems ×10) держатся при −50% стоимости.
- **B (надёжность глубины):** depth-метрика в критике + чаще рефразер → закрыть
  пустые карты (Лигал Лайн/Кофестория), калибровать ожидания по типу.
- **Коммит балансного конфига:** правка `02_research_orgs.py` (soft-law+cap) +
  `ecosystem.llama-deep.config.js` (q8-профиль) + обновлённые отчёты.
- **Мониторинг квоты прокси** на длинных прогонах (сегодня пул падал по квоте).

## Артефакты
- Код: `src/actions/yandex_maps.py`, `src/api/routers/yandex_maps.py`,
  `src/domain/models/yandex_card.py`, `requests.py`,
  `src/actions/research/org_taxonomy.py`, `org_schemas.py`,
  `src/core/config.py`, `src/actions/research/tools.py`,
  `yandex_enrichment_experiment/01_scrape_yandex.py`, `02_research_orgs.py`
  (soft-law+cap, Workstream D), `ecosystem.llama-deep.config.js` (q8-профиль).
- Данные: `yandex_enrichment_experiment/data_750m/` — research/ (baseline 132),
  research_ac/ (A+C, 21), research_d/ (D1 q4), research_d_q8/ (D2 q8),
  research_final/ (балансный 132, в работе) + отчёты:
  REPORT_run_750m / REPORT_AC_validation / REPORT_AC_detailed / REPORT_D_experiment.
- Закоммичено: `28f865f` (Workstream A+C+E+ретраи, .py+.md). Workstream D (soft-law+cap
  + q8-профиль) и обновления отчётов — ещё НЕ закоммичены.

## Запуск/возобновление
```bash
docker compose up -d redis
pm2 start ecosystem.config.js          # или --only <app>; при router-mode баге:
                                       # pm2 delete llama-server && pm2 start ecosystem.config.js --only llama-server
# ресёрч (идемпотентно, пропускает готовые):
YA_DATA_DIR="$(pwd)/yandex_enrichment_experiment/data_750m" CONCURRENCY=3 \
  uv run python yandex_enrichment_experiment/02_research_orgs.py
```
