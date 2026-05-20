# yandex_maps_experiment

Локальная проверка всех применимых способов парсинга Яндекс.Карт из
[`docs/yandex-maps-scraping.md`](../docs/yandex-maps-scraping.md), с
использованием sticky-резидентного прокси (`puls_sticky_30min.txt`).

**Целевой кейс:** база знаний компаний по категориям/городу — на тестах
«стоматология» в Санкт-Петербурге (`lr=2`).

## Краткий итог

**Победитель — Подход 4** (`04_playwright_xhr_intercept.py`):
headless Playwright + `playwright-stealth` + RU residential proxy + перехват
`/maps/api/search` XHR. Даёт **48 уникальных организаций × 65+ полей** за
**16 секунд** без капчи. Полная схема Яндекса: телефоны (E.164), координаты,
часы работы, услуги, фото-templates, метро, ИНН через `advert.ordInfo.client.tin`.

Для отзывов — **Подход 6** (`06_fetch_reviews.py`): тот же браузер, та же
сессия, но replay observed-URL `/maps/api/business/fetchReviews`. 50 отзывов с
12 полями каждый, включая `businessComment` (ответ бизнеса) и
`textTranslations` (автопереводы).

См. [`RESULTS.md`](./RESULTS.md) — полный отчёт по всем 7 подходам.

## Запуск

```bash
# Из корня репозитория
uv run python yandex_maps_experiment/00_proxy_check.py
uv run python yandex_maps_experiment/04_playwright_xhr_intercept.py
uv run python yandex_maps_experiment/06_fetch_reviews.py
```

## Структура

```
yandex_maps_experiment/
├── README.md                            <- этот файл
├── RESULTS.md                           <- полный отчёт со всеми вердиктами
├── common.py                            <- общие хелперы (прокси, ExperimentResult, …)
├── 00_proxy_check.py                    <- sanity check sticky-сессии
├── 01_direct_http_public_search.py      <- direct HTTP к /maps/api/search (CSRF-chain → 400)
├── 01b_bootstrap_html_parse.py          <- разбор HTML на bootstrap-JSON (данных нет)
├── 01c_html_dom_parse.py                <- разбор SSR-карточек (5 орг.)
├── 02_official_geosearch.py             <- official Geosearch без apikey (400/403)
├── 03_playwright_basic.py               <- headless + DOM-скроллинг (41 орг.)
├── 04_playwright_xhr_intercept.py    ★  <- лучший подход: XHR-перехват (48 орг × 65+ полей)
├── 05_pypi_libs.py                      <- survey YMRP + arsenyvolodko
├── 06_fetch_reviews.py               ★  <- отзывы через observed-URL replay (50 отз × 12 полей)
├── results/                             <- JSON отчёты + raw артефакты
└── logs/                                <- лог-файлы каждого прогона
```

Источник плана и трейд-оффов: `../docs/yandex-maps-scraping.md` (§3, §4, §7, §8, §10).
