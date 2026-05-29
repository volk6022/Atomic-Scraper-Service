# Требования к web-GUI для ревью ресёрчей организаций (`review_app`)

> Самодостаточный документ для агента-исполнителя. Контекст диалога не предполагается —
> всё необходимое описано ниже. Цель: собрать локальный web-сайт для ревью больших
> JSON-артефактов research-агента, с ручным редактированием любых полей и перезапуском
> ресёрча с уточнениями оператора.

---

## 1. Контекст и назначение

Research-агент по каждой организации (идентификатор `oid`) производит большой JSON-артефакт.
Оператор гоняет такие ресёрчи большими батчами: первый батч — 500+ организаций, целевая
нагрузка — порядка **1000 ресёрчей в сутки**. Все артефакты имеют **одинаковую структуру**.

Нужен локальный (один пользователь, на личном ПК) web-сайт, который:
1. подаёт огромный объём вложенной информации в **структурированном, удобно-читаемом виде**;
2. позволяет **править руками вообще любое поле** артефакта;
3. позволяет **перезапустить ресёрч** по организации, передав агенту **дополнительные
   уточнения свободным текстом**.

### Ключевые пути (существующий код, не переписывать без причины)
- Агент: `yandex_enrichment_experiment/simple_agent_v2.py`
  - точка входа: `async def run_agent(model_key: str, oid: str) -> dict`
  - в нём же определена JSON-схема карточки: `ORG_CARD_SCHEMA` (переиспользовать для валидации правок)
- Батч-раннер (образец импорта агента через `importlib` + идемпотентного прогона):
  `yandex_enrichment_experiment/03_research_all.py`
- Артефакты ресёрчей: `yandex_enrichment_experiment/data/research/{oid}__local.json`
- Источник организаций: `yandex_enrichment_experiment/data/organizations_filtered.json`
  (ключ `kept_orgs`), отзывы: `data/reviews/{oid}.json` — нужны агенту при re-run, он сам их читает.

---

## 2. Структура артефакта (что ревьюим)

Каждый файл `data/research/{oid}__local.json` — объект с полями верхнего уровня:

- `model`, `model_id`, `oid` — идентификация прогона.
- `anchor` — «якорь» организации (ground truth): `name`, `oid`, `address`, `city`,
  `categories[]`, `yandex_phones[]`, `yandex_site`, `yandex_url`.
- `elapsed_s`, `turns`, `tool_call_counts{web_serp,web_scrape,submit_org_card}`,
  `refraser_runs`, `submit_attempts`, `compactions`, `blocked_domains_at_end[]` — метрики прогона.
- `critic_events[]` — оценки критика: `{score, verdict, missing[], wrong[], feedback}`.
- `tokens{main{...}, aux{...}, grand_total}` — расход токенов.
- **`submitted_card`** — главный результат, по схеме `ORG_CARD_SCHEMA`:
  - `what_they_do` (str)
  - `scale_indicators[]` (str)
  - `tech_stack[]` (str)
  - `vacancies[]` → `{title, url, platform∈{hh.ru,superjob.ru,career_page,other}}`
  - `social{vk[], telegram[], instagram[], youtube[], linkedin[], habr[]}`
  - `contacts{phones[]→{number,context}, emails[]→{address,context}, websites[]}`
  - `yandex_maps{rating, reviews_count, reviews_sample[], hours}`
  - `problems_signals[]` (str)
  - `sources[]` → `{url, what_it_provided}`
  - возможен служебный флаг `_force_submit: true` (агент не сабмитнул сам — карточка собрана из seed).
- `queries_history[]` — поисковые запросы агента.
- `visited_urls[]` — посещённые URL.
- **`trace[]`** — пошаговый трейс: записи с `turn`, `role`
  (`assistant`/`tool`/`critic`/`refraser`/`note`/...), `tool_calls`/`tool_name`/`args`,
  `result_preview`, `elapsed_s`, `main_prompt_tokens`. Может быть длинным (десятки записей).

---

## 3. Стек (зафиксирован, не менять)

- **Backend:** Python 3.12, **FastAPI**, **Jinja2**, **uvicorn**.
- **Интерактив:** **HTMX** (server-rendered, без отдельного JS-билда). Allowed Alpine.js
  для мелкой клиентской логики (табы, сворачивание).
- **Редактор Raw JSON:** клиентский виджет (CodeMirror или аналог), вендорить локально в `static/`.
- **БД:** **PostgreSQL**, доступ через **SQLAlchemy 2 (async)** + **asyncpg**. Карточка
  целиком хранится в **JSONB**; для фильтров/поиска/сортировки — извлечённые скалярные колонки.
- **Валидация правок:** `jsonschema` против `ORG_CARD_SCHEMA` из `simple_agent_v2.py`.
- **Re-run агента:** внутрипроцессный asyncio-воркер с `asyncio.Semaphore(1)` (на машине
  один GPU — прогоны сериализуются).

Весь этот стек уже присутствует в зависимостях корневого проекта `auto-monitor`
(`fastapi`, `jinja2`, `python-multipart`, `sse-starlette`, `sqlalchemy[asyncio]`, `asyncpg`,
`alembic`, `uvicorn`). Для приложения внутри эксперимента добавить недостающее
(`jsonschema`) в `pyproject.toml` репозитория Atomic-Scraper-Service либо в отдельный venv.

> Запрещено: SPA/React/Svelte, Streamlit/Gradio. Решение принято осознанно: один язык
> (Python) нужен чтобы кнопка re-run напрямую импортировала и вызывала `run_agent(...)`,
> а server-rendered HTMX — минимум сборки для одного локального пользователя.

---

## 4. Модель данных (PostgreSQL)

Таблица `research_cards` (одна строка = один ресёрч):

| Колонка | Тип | Источник из JSON | Назначение |
|---|---|---|---|
| `oid` | text | `oid` | часть уникального ключа |
| `model_key` | text | суффикс файла (`local`) | часть уникального ключа |
| `name` | text | `anchor.name` | список + поиск |
| `address` | text | `anchor.address` | отображение/фильтр |
| `categories` | text[] | `anchor.categories` | фильтр |
| `critic_score` | numeric | `critic_events[-1].score` | сортировка/фильтр качества |
| `critic_verdict` | text | `critic_events[-1].verdict` | бейдж |
| `turns` | int | `turns` | метрика |
| `elapsed_s` | numeric | `elapsed_s` | метрика |
| `tokens_total` | int | `tokens.grand_total` | метрика |
| `compactions` | int | `compactions` | метрика |
| `submit_attempts` | int | `submit_attempts` | метрика |
| `forced_submit` | bool | наличие `submitted_card._force_submit` | флаг «агент не сабмитнул» |
| `review_status` | text | оператор | `new`/`reviewed`/`flagged`/`edited`, default `new` |
| `operator_notes` | text | оператор | свободная заметка ревьюера |
| `card` | jsonb | `submitted_card` | **редактируемая** карточка |
| `trace` | jsonb | `trace` | трейс |
| `anchor` | jsonb | `anchor` | детальный вид |
| `critic_events` | jsonb | `critic_events` | детальный вид |
| `queries_history` | jsonb | `queries_history` | детальный вид |
| `visited_urls` | jsonb | `visited_urls` | детальный вид |
| `tokens` | jsonb | `tokens` | детальный вид |
| `tool_call_counts` | jsonb | `tool_call_counts` | детальный вид |
| `source_file` | text | путь к файлу | связь с файлом |
| `file_mtime` | timestamptz | mtime файла | идемпотентность ingest |
| `created_at` | timestamptz | — | аудит |
| `updated_at` | timestamptz | — | аудит |
| `edited_at` | timestamptz | — | когда оператор правил вручную |

**Индексы:** `UNIQUE(oid, model_key)`; btree(`critic_score`); btree(`review_status`);
GIN(`card`); GIN(`name` `gin_trgm_ops`) (требует `CREATE EXTENSION pg_trgm`).

v1: схему создавать bootstrap-DDL скриптом (`schema_sql.py`); alembic — позже.

---

## 5. Хранилище и синхронизация (важно)

- **Postgres — источник истины** для ревью и ручных правок.
- **JSON-файлы остаются артефактом агента** и держатся в синхроне: при ручной правке
  обновляется и строка в PG, **и** файл `data/research/{oid}__local.json` (требование
  «данные в 2 экземплярах»).
- **Ingest (`ingest.py`):** сканирует `data/research/*.json`, upsert по `(oid, model_key)`.
  Идемпотентность: пропускать файл, если `file_mtime` не изменился **И**
  `review_status != 'edited'` (нельзя затирать ручные правки оператора). Запускается
  вручную и автоматически после каждого re-run.

---

## 6. Функциональные требования (v1)

### 6.1. Список карточек (`GET /`, `GET /cards`)
- HTMX-таблица с пагинацией (по умолчанию `page_size=50`).
- Колонки: name, categories, бейдж critic-score, verdict, turns/tokens, бейдж `review_status`, дата.
- Фильтры: категория, минимальный `critic_score`, `review_status`, `forced_submit`,
  текстовый поиск по `name`/`what_they_do`.
- Сортировка по score и по дате.
- **Производительность:** рендер ≤ 0.5 с на тысячах строк (за счёт индексов + пагинации,
  фильтрация на стороне SQL, не в Python).

### 6.2. Детальная карточка (`GET /cards/{oid}`)
Секции (рекомендуется табами/сворачиванием, т.к. объём большой):
- **Карточка** (структурировано): `what_they_do`, `scale_indicators`, `tech_stack`,
  `vacancies`, `social`, `contacts` (phones/emails/websites), `yandex_maps`, `problems_signals`.
- **Источники:** `sources[]` (url + what_it_provided) и `visited_urls[]` — всё кликабельными ссылками.
- **Trace:** сворачиваемый таймлайн (turn, роль, tool, args, result_preview, elapsed_s);
  критик-события выделять.
- **Queries history** и **Метрики/токены**.
- **Raw JSON:** вкладка с редактором (см. 6.3).
- Панель действий: «Перезапустить ресёрч» (см. 6.4), смена `review_status`, заметка оператора.

### 6.3. Ручное редактирование любых полей
- **Inline-правка** частых полей карточки через HTMX-формы (`POST /cards/{oid}/edit`),
  `hx-swap` обновляет затронутую секцию.
- **Raw JSON** (`POST /cards/{oid}/raw`): полный JSON карточки в редакторе; перед сохранением
  валидировать `jsonschema` против `ORG_CARD_SCHEMA`. Невалидный JSON → ошибка показывается
  inline, ничего не сохраняется.
- Любое сохранение: обновить `card` (JSONB) в PG, выставить `review_status='edited'`,
  `edited_at=now()`, **и переписать файл** `data/research/{oid}__local.json` (синхрон 2 копий,
  `ensure_ascii=False, indent=2`).

### 6.4. Перезапуск ресёрча (`POST /cards/{oid}/rerun`)
- Форма с полем `operator_context` (свободный текст уточнений; пустой = обычный прогон).
- Кладёт задачу в очередь `agent_runner` (asyncio + `Semaphore(1)`); статусы:
  `queued → running → done | error`.
- UI поллит статус (`GET /cards/{oid}/rerun-status`, HTMX `hx-trigger="every 3s"`); бейдж
  статуса в карточке и в списке.
- По завершении: записать новый JSON-файл (перезаписать `oid`), затем re-ingest этого `oid`
  в PG. Карточка/trace/метрики **заменяются целиком**; `review_status` сбрасывается в `new`.

### 6.5. Озвучка текста через TTS-нейросеть (обязательно)
- Оператору требуется **озвучивать текст карточки голосом** через TTS-нейросеть.
- **В дизайне сайта обязательна отдельная кнопка** для запуска озвучки (например «🔊 Озвучить»).
  Кнопка размещается рядом с текстовыми блоками, которые имеет смысл слушать — как минимум
  у `what_they_do`; желательно также возможность озвучить произвольный выделенный/собранный
  текст карточки.
- Поведение: по нажатию кнопки текст уходит на TTS-нейросеть, в ответ приходит аудио, которое
  проигрывается прямо в браузере (HTML5 `<audio>`); во время генерации — индикатор загрузки,
  кнопки play/pause/stop.
- Backend-маршрут `POST /cards/{oid}/tts` (или `/tts` с телом-текстом): принимает текст,
  обращается к TTS-движку, возвращает аудиопоток/файл (например `audio/mpeg` или `audio/wav`).
- **TTS-движок вынести за абстракцию** (отдельный модуль/клиент `tts.py` с конфигом через env:
  адрес эндпоинта, модель/голос, ключ), чтобы можно было подключить локальную или внешнюю
  TTS-нейросеть, не трогая UI. Конкретный движок — на выбор исполнителя/оператора; интерфейс
  фиксируем: `synthesize(text: str) -> bytes (audio)`.
- Кэширование аудио и озвучка длинных трейсов — вне v1 (по желанию).

### 6.6. Требуемая правка агента (`simple_agent_v2.py`, ~10 строк)
- Добавить параметр `operator_context: str = ""` в `run_agent(...)`.
- Пробросить его в `build_user_message(...)` как дополнительный блок, например
  «ДОПОЛНИТЕЛЬНЫЕ УКАЗАНИЯ ОПЕРАТОРА: …», либо в system-сообщение.
- Параметр опционален → существующий `03_research_all.py` продолжает работать без изменений.

---

## 7. Требования к UX/дизайну

- **Плотность и читаемость:** оператор просматривает много карточек подряд — список должен
  быть сканируемым (бейджи статусов/score цветом), детальная карточка — без «стены текста»
  (секции, сворачивание, моноширинный шрифт для trace/raw).
- **Кликабельность всех URL** (sources, visited_urls, vacancies, websites, social) — открывать
  в новой вкладке.
- **Отдельная кнопка озвучки (TTS)** в дизайне обязательна — рядом с текстовыми блоками
  карточки (как минимум `what_they_do`); по нажатию текст озвучивается голосом и
  проигрывается во встроенном аудиоплеере (см. 6.5).
- **Видимость деградаций:** `forced_submit`, низкий `critic_score`, пустые ключевые поля
  (`what_they_do`, `contacts`) — визуально подсвечивать, чтобы такие карточки были заметны.
- **Без лишних модалок/подтверждений** на правках и смене статуса — оператор работает быстро.
- Локализация интерфейса — русский (данные русскоязычные).
- Локально, один пользователь: авторизация в v1 не нужна (можно добавить HTTP Basic позже).

---

## 8. Структура приложения (предлагаемая)

```
yandex_enrichment_experiment/review_app/
  __init__.py
  db.py            — async engine/session (asyncpg), DSN из env REVIEW_DB_URL
  models.py        — SQLAlchemy: ResearchCard (+ опц. RerunJob)
  schema_sql.py    — bootstrap DDL (CREATE EXTENSION pg_trgm; CREATE TABLE/INDEX)
  ingest.py        — скан data/research/*.json → upsert в PG (идемпотентно по mtime)
  agent_runner.py  — очередь re-run: importlib(simple_agent_v2) + asyncio.Semaphore(1)
  tts.py           — клиент TTS-нейросети за абстракцией synthesize(text)->bytes (конфиг из env)
  org_card.py      — импорт ORG_CARD_SCHEMA из simple_agent_v2 для валидации
  app.py           — FastAPI: все маршруты
  templates/       — Jinja2: base.html, cards_list.html, card_detail.html, _row.html,
                     _trace.html, _raw_edit.html, _rerun_status.html
  static/          — css, htmx.min.js, codemirror (вендор локально)
```

Запуск: `uv run uvicorn review_app.app:app --port 8002`
(порт 8002, чтобы не конфликтовать с планируемым дашбордом спеки 002 на :8001).

### Сводка маршрутов
| Метод/путь | Назначение |
|---|---|
| `GET /` , `GET /cards` | список с фильтрами/пагинацией (HTMX) |
| `GET /cards/{oid}` | детальная карточка |
| `POST /cards/{oid}/edit` | inline-правка полей карточки → swap секции |
| `POST /cards/{oid}/raw` | сохранить отредактированный raw JSON (валидация по схеме) |
| `POST /cards/{oid}/status` | сменить `review_status` / `operator_notes` |
| `POST /cards/{oid}/rerun` | поставить re-run в очередь (поле `operator_context`) |
| `GET /cards/{oid}/rerun-status` | статус задачи re-run (поллинг HTMX) |
| `POST /cards/{oid}/tts` | озвучить текст через TTS-нейросеть → аудио (audio/mpeg\|wav) |

---

## 9. Критерии приёмки (end-to-end)

1. Поднят локальный Postgres; задан `REVIEW_DB_URL`; bootstrap-DDL выполнен.
2. `ingest`: число строк в `research_cards` = числу файлов `data/research/`; выборочно
   `card` в PG совпадает с файлом.
3. Список рендерится < 0.5 с на полном объёме; фильтры, текстовый поиск и пагинация работают.
4. Детальная карточка: все секции (card/trace/sources/queries/tokens) читаемы; ссылки кликабельны.
5. Правка поля (структурно и через Raw JSON): невалидный JSON → ошибка inline; валидный →
   сохранён. После reload правка видна в PG **и** в JSON-файле; `review_status='edited'`.
6. Re-run одного `oid` с `operator_context`: статус `queued→running→done`; после завершения
   карточка/trace обновились, файл перезаписан, re-ingest отработал, агент учёл уточнение.
7. Повторный `ingest` без изменений файлов → 0 апдейтов; правки оператора (`edited`) не затёрты.
8. Нажатие кнопки **TTS** на тексте карточки: текст уходит на TTS-нейросеть, аудио
   возвращается и проигрывается во встроенном плеере; ошибка движка показывается без падения страницы.

---

## 10. Вне v1 (на будущее)

- Alembic-миграции вместо bootstrap-DDL.
- Live-стриминг trace во время re-run через `sse-starlette`.
- HTTP Basic авторизация для не-локального доступа.
- Слияние с операторским дашбордом спеки `002-enrich-and-monitor`
  (`src/auto_monitor/dashboard`), если эксперимент «выпускается» в продукт.
