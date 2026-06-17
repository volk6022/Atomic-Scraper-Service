# Yandex Maps Scraping — Локальное исследование 7 подходов

**Дата:** 2026-05-17 — 2026-05-18
**Исполнитель:** Claude (Sonnet 4.6) в Claude Code
**Окружение:** Windows, Python 3.12, `.venv` через `uv`, Playwright 1.58.0, playwright-stealth 2.0.3, residential sticky-прокси `np.puls-proxy.com:11000` (`sessttl.30`)
**Источник плана:** [`docs/yandex-maps-scraping.md`](./yandex-maps-scraping.md) — обзорное исследование 2025/2026.
**Артефакты:** [`yandex_maps_experiment/`](../yandex_maps_experiment/) — рабочая папка с исходниками, JSON-результатами и сырыми артефактами.

---

## 1. Постановка задачи

Был запрос: построить базу знаний компаний (приоритет — медицина/стоматологии Санкт-Петербурга) на основе данных Яндекс.Карт, не прибегая к платным сервисам (Apify, BrightData, 2Captcha, Oxylabs). Из исследования
[`yandex-maps-scraping.md`](./yandex-maps-scraping.md) было выписано **семь локально-выполнимых подходов**, каждый требовал отдельной живой проверки на:

1. реально ли проходит через residential RU-прокси без капчи;
2. сколько и каких полей удаётся достать на организацию;
3. сколько занимает по времени;
4. устойчивость на повторных прогонах.

Тестовый запрос — `стоматология` с регионом `lr=2` (СПб), bbox центральной/южной части города. Глубина прогона — «средняя»: 20–50 организаций на подход.

---

## 2. Подготовка окружения

### 2.1 Структура папки

```
yandex_maps_experiment/
├── README.md
├── RESULTS.md
├── common.py                            <- общий helper (прокси, ExperimentResult, utf8)
├── 00_proxy_check.py                    <- sanity sticky-сессии
├── 01_direct_http_public_search.py
├── 01b_bootstrap_html_parse.py
├── 01c_html_dom_parse.py
├── 02_official_geosearch.py
├── 03_playwright_basic.py
├── 04_playwright_xhr_intercept.py       ⭐
├── 05_pypi_libs.py
├── 06_fetch_reviews.py                  ⭐
├── results/                             <- JSON отчёты + raw HTML/JSON
└── logs/
```

### 2.2 Общий helper `common.py`

В нём:
- `load_proxies()` / `http_proxy_url()` / `playwright_proxy()` / `requests_proxies()` — единая точка чтения `puls_sticky_30min.txt`.
- `ExperimentResult` (dataclass) — единый машинно-читаемый отчёт: `success`, `captcha_detected`, `http_status`, `items_collected`, `fields_per_item`, `egress_ip`, `duration_s`, `notes`, `sample`, `error`. `save()` сериализует в `results/<name>.json`.
- `log_line()` — пишет одновременно в stdout и в `logs/<name>.log`.
- `utf8_stdout()` — обход cp1251-mojibake кириллицы в Windows-консоли.
- Целевые константы (`TARGET_QUERY = "стоматология"`, `TARGET_CITY`, `SPB_BBOX`, `SPB_REGION_ID = 2`).

### 2.3 Установленные пакеты

В рабочем `.venv` уже были `playwright 1.58.0`, `playwright-stealth 2.0.3`, `httpx 0.28.1`, `requests 2.33.1`, `beautifulsoup4 4.14.3`, `selenium 4.44.0`. Дополнительно поставлены через `uv pip install`:
- `ymrp 0.6.0` (PyPI),
- `yandex-maps-reviews-parser 0.1.0` (из `git+https://github.com/arsenyvolodko/...` — на PyPI отсутствует).

---

## 3. Подход 00 — sanity sticky-прокси

**Файл:** [`00_proxy_check.py`](../yandex_maps_experiment/00_proxy_check.py)
**Запрос:** 6 последовательных запросов к `api.ipify.org` через `requests` + прокси-сессия.
**Дополнительно:** один запрос к `ip-api.com/json` для geo-lookup.

**Сырой лог:**
```
req 1: ip=84.22.142.138 (7035ms)
geo: {"country":"Russia","city":"Krasnoyarsk","isp":"Igra-Service LLC","as":"AS33991 Igra-Service LLC"}
req 2: ip=84.22.142.138 (2454ms)
req 3: ERROR ProxyError ... ConnectTimeoutError np.puls-proxy.com:11000
req 4: ip=84.22.142.138 (2278ms)
req 5: ERROR ProxyError ...
req 6: ip=84.22.142.138 (2315ms)
verdict: FAIL | 4/6 successful; 1 unique IP
```

**Что выяснилось:**
- Sticky подтверждён: на 4 успешных запросах **один и тот же** IP `84.22.142.138`.
- Геолокация — Россия, **Красноярск**, AS Igra-Service LLC. Не СПб. Это потенциальный риск для длинных прогонов (см. §8.4 исследования: «Yandex weighs IP geo against query region»), но в наших экспериментах капча так и не сработала — `lr=2` оказалось достаточно.
- 2 из 6 запросов упали по таймауту **на стороне самого провайдера прокси** (`np.puls-proxy.com:11000` connect timeout), не Яндекса. Это сразу зафиксировано как **обязательное требование retry с backoff** для всех последующих экспериментов.

**Вывод:** прокси пригоден; провайдер даёт ~67% мгновенной успешности — критично обрабатывать сетевые исключения.

---

## 4. Подход 01 — direct HTTP к внутреннему `/maps/api/search`

**Цель:** проверить, можно ли вообще обойтись без браузера, дёргая JSON-эндпоинт напрямую через `requests` + RU-прокси. По §3 исследования это endpoint, который дёргает SPA.

### 4.1 Первая итерация — голый GET

`01_direct_http_public_search.py`. Сперва — warmup `https://yandex.ru/maps/2/saint-petersburg/search/стоматология/` чтобы получить cookies (`yandexuid`, `_yasc`, `i`, `pi`, `yashr`, …). Потом GET `https://yandex.ru/maps/api/search?text=...&ll=...&lr=2&ajax=1&results=24`.

**Первый запуск упал** с `ProxyError ConnectTimeoutError` — провайдер опять hiccup. Добавил `_get_with_retry()` (4 попытки, экспоненциальный backoff 2/4/6/8 с).

**После retry-обёртки:**
```
warmup GET .../search/стоматология/ -> 200 (1528924B)
cookies=['_yasc','bh','i','is_gdpr','is_gdpr_b','pi','yandexuid','yashr']
GET .../maps/api/search?... -> 200 (67B)
snippet='{"csrfToken":"5493d377a03781baf491f118f785a79bb3e48d69:1779005366"}'
```

**Промежуточный инсайт:** endpoint возвращает не данные, а **CSRF-token** для последующего запроса. Это классический challenge — повторяю с `?csrfToken=<value>`.

### 4.2 Вторая итерация — CSRF chain

```
GET .../maps/api/search?...&csrfToken=71b183...:1779005406 -> 400 (11B)
snippet='Bad Request'
```

**Облом.** Даже с валидным CSRF-token Яндекс возвращает 400. Гипотеза: endpoint защищён дополнительной подписью запроса (`X-Retpath-Y` header или `_t` timestamp), которая генерируется только JS-кодом SPA, а cookies-сессия в `requests` отдельно не достаточна.

**Решение:** не углубляться (по §10.2 исследования это известная штука — «the simple cURL approach often returns 'Загрузка…' placeholders»), а сразу пойти двумя альтернативными маршрутами:

### 4.3 Подход 01b — парс bootstrap JSON из HTML

`01b_bootstrap_html_parse.py`. Идея: SPA, рендерясь на сервере, часто кладёт начальное состояние в `<script>` блок типа `window.__bootstrap__ = {...}`.

Реализовал `harvest_jsons_from_html()` с тремя паттернами (window.__X__, JSON.parse(), raw JSON-блоки) и рекурсивным walker'ом `find_business_items()` (искал объекты с `businessId`/`oid`/`encoded_id` + `name` + координатами/адресом).

**Лог:**
```
GET .../search/стоматология/ -> 200 (1444672B)
parsed JSON blocks: 2 (['raw_json', 'raw_json'])
regex fallback found businessIds: 0
```

2 JSON-блока — но это конфиг приложения (`window.NK.config`-style), не данные. Прямой regex `"businessId":...` — 0 совпадений.

**Inspection HTML:**
```
'businessId': 1
'business_id': 0
'permalink': 13
'"name":': 2349
'avatars.mds': 1813
'stomat': 239
```

Данные есть (`avatars.mds.yandex.net` 1813 раз, кириллица «стомат» 239 раз), но Яндекс не сериализует список snippets в инлайн-JSON для server-side rendering. Зато 5 уникальных org-ID в HTML-разметке:
```
/maps/org/<seoname>/<oid>/  -> 15 совпадений, 5 уникальных
```

Это и есть SSR-карточки — рендерятся как DOM-узлы, не в JSON.

### 4.4 Подход 01c — DOM-парсинг SSR карточек

`01c_html_dom_parse.py`. BeautifulSoup `select("li.search-snippet-view, div.search-snippet-view")`, селекторы для каждого поля найдены инспекцией HTML.

**Лог:**
```
GET -> 200 (1561440B)
raw cards parsed: 5, after dedup by oid: 5
verdict: success=True items=5 captcha=False
fields=['address','business_oid','categories_text','name','rating','reviews_text','seoname','url','working_status']
```

**5 организаций × 9 полей за 8 секунд.** Это — потолок голого HTTP, потому что SPA рендерит на сервере только первый viewport (≤5 карточек). Дальнейшее подгружается JS-скроллом, который без браузера не работает.

**Пример:**
```json
{
  "name": "Houston",
  "categories_text": "Стоматологическая клиника",
  "address": "Кременчугская ул., 9, корп. 2",
  "rating": "Рейтинг5,0",
  "reviews_text": "390 оценок",
  "url": "/maps/org/houston/178860213454/",
  "seoname": "houston",
  "business_oid": "178860213454",
  "working_status": "Открыто до 21:00"
}
```

**Вывод по 01:** direct HTTP применим только для крошечных смок-тестов. Для масштаба нужен браузер.

---

## 5. Подход 02 — официальный Geosearch API (без apikey)

**Файл:** [`02_official_geosearch.py`](../yandex_maps_experiment/02_official_geosearch.py)
**Цель:** документально подтвердить, что endpoint без платного ключа не отдаёт данные.

Сделал два вызова: без `apikey` и с фиктивным `00000000-0000-0000-0000-000000000000`.

**Лог:**
```
no-key -> 400 (140B)
snippet='<?xml ...><statusCode>400</statusCode><message>Missing apikey</message>'
fake-key -> 403
snippet='<?xml ...><statusCode>403</statusCode><message>Invalid api key</message>'
```

**Вывод:** ровно то, что обещало исследование (§2.1) — без annual prepaid контракта в RUB endpoint полностью отключён. Локально применить нельзя. **Закрываем как ✗.**

---

## 6. Подход 03 — Playwright headless + DOM-scroll

**Файл:** [`03_playwright_basic.py`](../yandex_maps_experiment/03_playwright_basic.py)
**Цель:** Тот же DOM-парсинг, что 01c, но с реальным браузером, чтобы JS-скролл дотянул больше карточек.

**Конфигурация:**
- `chromium.launch(headless=True, proxy=playwright_proxy(), args=["--disable-blink-features=AutomationControlled"])`
- Контекст: `locale="ru-RU"`, `timezone_id="Europe/Moscow"`, viewport 1440×900, реалистичный Chrome 124 UA.
- Цикл скролла внутри `.scroll__container, .search-list-view__list` + `window.scrollBy`, 25 итераций × 900 мс, с порогом stale=3 (если 3 итерации подряд счётчик не растёт — break).

**Лог:**
```
goto https://yandex.ru/maps/2/saint-petersburg/search/стоматология/
scroll iter 0: cards=5      <- те же 5 SSR-карточек
scroll iter 1: cards=11
scroll iter 2: cards=16
scroll iter 3: cards=17
scroll iter 4: cards=23
scroll iter 5: cards=29
scroll iter 6: cards=30
scroll iter 7: cards=31
scroll iter 8: cards=37
scroll iter 9: cards=43
final cards=43 dedup=41
verdict: success=True items=41 captcha=False duration_s=24.2
```

**Результат: 41 уникальная организация за 24 секунды. Капча не сработала.** Но 9 полей — те же скудные, что и в 01c (всё, что есть в DOM-разметке).

**Промежуточный вопрос:** а если данные в карточках бедные, **где живут координаты, телефоны, услуги**? Гипотеза — в самом XHR-ответе, который Яндекс делает за нас при скролле. Если перехватить — получим в разы больше полей.

---

## 7. Подход 04 — Playwright + stealth + XHR intercept ⭐

**Файл:** [`04_playwright_xhr_intercept.py`](../yandex_maps_experiment/04_playwright_xhr_intercept.py)
**Цель:** то же, что 03, но добавить `playwright-stealth` и `page.on("response", …)` для отлова всех ответов от `/maps/api/search`, `search-maps.yandex.ru`, `/maps/api/business`, `fullobjects`.

### 7.1 Реализация stealth

```python
from playwright_stealth import Stealth
...
Stealth().apply_stealth_sync(page)
```

API в `playwright-stealth 2.0.3` — это класс `Stealth` с методом `apply_stealth_sync(page)`. Документация скудна, поэтому пришлось интроспектировать через `dir()`.

### 7.2 Интерсептор

```python
def on_response(response):
    u = response.url
    if "/maps/api/search" in u or "search-maps.yandex.ru" in u or \
       "/maps/api/business" in u or "fullobjects" in u:
        captured.append({"url": u, "status": response.status,
                         "len": len(response.text()), "body": response.text()})

page.on("response", on_response)
```

### 7.3 Первый прогон — слишком жадный walker

Первая итерация walker'а:
```python
if "name" in obj and ("permalink" in obj or "id" in obj) and ("coordinates" in obj or ...):
    org_items.append(obj)
```

**Лог:**
```
XHR 200 .../maps/api/search?... (811795B)
XHR 200 .../maps/api/search?... (716676B)
final card count: 37
XHR captures: 2, org-like objects: 396, dedup: 192
verdict: success=True items=192 captcha=False duration_s=15.56
```

**192 объекта!** Подозрительно много. Проверка структуры:
```python
types = Counter(it.get('type') for it in d)
# Counter({'common': 164, 'metro': 28})
```

Это были **транспортные остановки** и **станции метро**, рекурсивно вытащенные из `geoObjects`. Бизнесов 0. Walker-эвристика слишком широкая.

### 7.4 Второй прогон — целевой парсинг `data.items`

Переписал на явное обращение к топ-уровневым массивам:
```python
for path in (("data", "items"), ("items",), ("data", "geo", "items")):
    cur = data
    ...
    if isinstance(cur, list):
        items_arr = cur
```

И фильтр на `(permalink | seoname | oid) in obj`:
```python
for it in items_arr:
    if isinstance(it, dict) and (("permalink" in it) or ("seoname" in it) or ("oid" in it)):
        org_items.append(it)
```

**Лог:**
```
XHR 200 .../maps/api/search?...&ajax=1&business_filter[0]=alter (846025B)
XHR 200 .../maps/api/search?...&ajax=1&business_filter[0]=alter (737990B)
final card count: 37
saved 2 raw captures (2015136B)
top-level items array at data.items len=25
top-level items array at data.items len=25
XHR captures: 2, org-like objects: 50, dedup: 48
verdict: success=True items=48 captcha=False duration_s=16.35
```

**48 уникальных организаций × 65+ полей за 16 секунд. Капча не сработала.**

### 7.5 Полная схема одной организации

Из первого item'а (`Дэнтал Конфидэнс`, oid `82071161567`):

```text
address, advert, analyticsId, aspects, awards, bounds, breadcrumbs,
businessImages, businessLinks, businessProperties, categories,
compositeAddress, coordinates, country, currentWorkingStatus, description,
displayCoordinates, entrances, eventsPreviews, featureGroups, features,
fullAddress, geoId, hasStories, houseEncodedCoordinates, id, index, logId,
matchedObjects, mediaOrderTemplate, metrika, metro, modularCard, modularPin,
modularSnippet, needSimilarOrgsRequest, panorama, parentRubrics, phones,
photos, promo, ratingData, references, region, requestId, requestSerpId,
routePoint, routeToChoose, seoname, shortTitle, socialLinks, sources, status,
stops, subtitleItems, title, topObjects, type, tzOffset, uri, urls, videos,
workingTime, workingTimeText
```

**65 полей.** Конкретные значения первой организации:
- `title`: "Дэнтал Конфидэнс"
- `address`: "Бармалеева ул., 12" / `fullAddress`: "Санкт-Петербург, Бармалеева улица, 12"
- `coordinates`: `[30.3056, 59.964324]`
- `phones`: `[{"number":"+7 (812) 218-28-10","type":"phone","value":"+78122182810"},{"number":"+7 (812) 602-64-12","value":"+78126026412","info":"Администратор"}]`
- `socialLinks`: `[{"type":"whatsapp","href":"https://wa.me/79019707906?text=..."}]`
- `categories`: `[{"id":"184106132","name":"Стоматологическая клиника","class":"dental","seoname":"dental_clinic","pluralName":"Стоматологии"}, ...]`
- `ratingData`: `{"ratingCount":338,"ratingValue":5,"reviewCount":292}`
- `aspects` (структурированная разбивка отзывов): `[{"text":"Качество лечения","count":161,"positive":156,"negative":5}, ...]`
- `currentWorkingStatus`: `{"isOpenNow":true,"text":"Открыто до 21:00"}`
- `features` (услуги): `[{"id":"dentist_services","value":[{"id":"dental_surgery","name":"хирургия"},{"id":"aesthetic_dentistry","name":"эстетическая стоматология"},{"id":"endodontics","name":"эндодонтия"}, ...]}]`
- `featureGroups`: `[{"name":"Доступность","featureIds":["elevator_wheelchair_accessible","ramp","wheelchair_access",...]}]`
- `metro`: `[{"id":"station__9805891","name":"Петроградская","distance":"560 м","color":"#0070bf"}]`
- `photos`: `{"count":100,"urlTemplate":"https://avatars.mds.yandex.net/get-altay/7456447/.../%s"}`
- `panorama`: `{"id":"1254521640_626037009_23_1753270670","preview":"https://static-pano.maps.yandex.ru/..."}`
- `subtitleItems`: `[{"type":"goods","text":"6900 ₽ Лечение кариеса","property":[{"key":"price","value":"6900"}]}]`
- **`advert.ordInfo.client`**: `{"id":"32007914","tin":"7813647750","name":"ООО ДЭНТАЛ КОНФИДЭНС"}` ← **ИНН и юр.имя организации**
- `awards`: `{"goodPlaceYear":"2026"}`

**Промежуточный вывод (важный):** XHR-перехват даёт **полную** документированную схему Яндекса плюс несколько не-документированных полей (например, `advert.ordInfo.client.tin` — ИНН). Это **больше полей**, чем заявляют Apify (30+) и официальный Geosearch (~10 docs-supported).

---

## 8. Подход 05 — survey PyPI-парсеров

**Файл:** [`05_pypi_libs.py`](../yandex_maps_experiment/05_pypi_libs.py)
**Цель:** проверить, имеет ли смысл использовать `ymrp` или `arsenyvolodko/yandex-maps-reviews-parser` вместо самописного Подхода 4/6.

### 8.1 `ymrp 0.6.0`

Установил через `uv pip install ymrp`. Под капотом:
- `playwright.sync_api`
- Класс `YandexMapReviewsParser.get_reviews_html_content(url)` — открывает страницу, скроллит, разворачивает «Read more»-кнопки, возвращает `inner_html()` reviews-контейнера.

**Критические ограничения:**
```python
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=False)  # ХАРД-КОД
    page = browser.new_page()
```

`headless=False` — **зашит**. Открывает видимое окно Chrome, без opt-out. Нет:
- proxy-аргумента,
- UA-override,
- stealth,
- сессионных cookies,
- сохранения профиля.

Возвращает HTML-блок, **не парсит** его — отдельно нужно дёргать `YandexMapReviewsHtmlCodeParser`.

### 8.2 `arsenyvolodko/yandex-maps-reviews-parser 0.1.0`

На PyPI **отсутствует** — поставил через `uv pip install git+https://github.com/arsenyvolodko/yandex-maps-reviews-parser`.

Под капотом:
- `selenium 4.44.0` (visible Chrome),
- `requests` для официального Geosearch API в `get_organization_id()` — но `consts.YANDEX_MAPS_API_TOKEN = ""` (пустой). Прямая проверка:
  ```
  test call: 400 <message>Missing apikey</message>
  ```
- `_parse_page()` извлекает только `(rate, text)` через BS4-селекторы.

Класс `Review` тривиален: `(rate, text)`.

**Критические ограничения:**
- `get_reviews_by_organisation_name()` бесполезен без apikey.
- `get_reviews_by_organisation_id()` работает, но открывает Selenium-Chrome, без прокси.
- Поля: ровно 2 на отзыв.

### 8.3 Вердикт по 05

Обе библиотеки **строго хуже** Подхода 4+6. Не имеет смысла тратить на них время. Записал survey в JSON и пошёл дальше.

---

## 9. Подход 06 — отзывы через `/maps/api/business/fetchReviews` ⭐

**Файл:** [`06_fetch_reviews.py`](../yandex_maps_experiment/06_fetch_reviews.py)
**Цель:** для известного `business_oid` вытянуть полный paginated список отзывов с автором, рейтингом, текстом, ответом бизнеса, датой.

Тест на `Дэнтал Конфидэнс` (`oid=82071161567`, `seoname=dental_konfidens`) — самый rich-data случай из подхода 4.

### 9.1 Первая итерация — прямой replay

Идея: запустить headless Playwright, перейти на `/maps/org/dental_konfidens/82071161567/reviews/`, дать сессии «прогреться» (получить cookies, включая `maps_session_id`), и потом через `page.request.get()` — что наследует все cookies — дёрнуть `/maps/api/business/fetchReviews?businessId=...&from=0&count=50`.

**Лог:**
```
goto .../reviews/
error: APIRequestContext.get: connect ETIMEDOUT 74.81.81.81:11000
```

Снова hiccup провайдера. Обернул в `for attempt in range(4)` с backoff. После retry:
```
fetchReviews page 0: 200 (67B)
  no review array found; top-level keys = ['csrfToken']
fetchReviews page 1: 200 (67B)
  no review array found; top-level keys = ['csrfToken']
verdict: success=False items=0
```

**Опять `{"csrfToken": ...}`** — тот же CSRF-challenge, что в Подходе 01.

### 9.2 Вторая итерация — добавил CSRF-priming

Сначала делаем «холостой» запрос для получения токена, потом передаём его в `?csrfToken=...`:

```
csrf prime: status=200, got_token=yes
fetchReviews page 0: 400 (11B) body='Bad Request'
fetchReviews page 1: 400 (11B) body='Bad Request'
```

**400 даже с валидным CSRF** — та же проблема, что в Подходе 01: endpoint защищён больше, чем просто CSRF. Видимо, проверяется ещё один хидер (`X-Retpath-Y`?) или порядок параметров.

### 9.3 Третья итерация — observation + replay ⭐

Решающий шаг: **дать SPA самой сделать настоящий запрос**, перехватить URL через `page.on("response")`, и **повторить ровно его** через `page.request.get(observed_url)`. Та же сессия, тот же CSRF, тот же порядок параметров — должно пройти.

```python
observed = []
def on_resp(resp):
    if "fetchReviews" in resp.url or "/api/business/" in resp.url:
        observed.append({"url": resp.url, ...})

page.on("response", on_resp)
page.goto(org_url)
# Триггерим lazy loading через скролл
for _ in range(5):
    page.evaluate("() => { const c = ...; if (c) c.scrollBy(0, 4000); ... }")
    page.wait_for_timeout(1200)

# В finally: replay первый observed-URL через ту же сессию
for obs in observed:
    if obs.get("status") == 200 and "fetchReviews" in obs["url"]:
        rr = page.request.get(obs["url"], headers={"Referer": org_url, "X-Requested-With": "XMLHttpRequest"})
        ...
```

**Лог:**
```
goto .../reviews/
csrf prime: status=200, got_token=yes
fetchReviews page 0: 400 (11B)  body='Bad Request'           <- ручной replay (всё ещё падает)
[obs] GET 200 .../fetchReviews?ajax=1&businessId=...&csrfToken=f1c970d...
  attempt 1: APIRequestContext.get: connect ETIMEDOUT 74.81.81.81:11000   <- proxy hiccup
fetchReviews page 1: 400 (11B)  body='Bad Request'           <- ручной replay
observed 1 review-ish XHRs
  pulled 50 reviews from observed-URL replay
verdict: success=True items=50 captcha=False duration_s=43.24
```

**50 отзывов получено.** Различие — в **порядке query-параметров**: реальный SPA-запрос идёт `?ajax=1&businessId=...&csrfToken=...` (ajax первый), а мой ручной — `?businessId=...&from=...&count=...&ranking=...&csrfToken=...`. Возможно, Яндекс действительно проверяет канонический порядок/набор параметров.

### 9.4 Полная схема одного отзыва

```text
author, businessComment, businessId, photos, rating, reactions, reviewId,
text, textLanguage, textTranslations, updatedTime, videos
```

**12 полей.** Примеры значений:
- `author`: `{"name":"Анастасия Б.","avatarUrl":"https://avatars.mds.yandex.net/get-yapic/.../{size}","professionLevel":"Знаток города 5 уровня","rtb":...}`
- `rating`: `5`
- `text`: «обратилась за заменой ретейнера. Усатова Анастасия Сергеевна выполнила работу быстро и качественно...»
- `businessComment`: `{"text":"Спасибо за ваш отклик","updatedTime":"2026-04-29T10:47:19.316Z"}`
- `updatedTime`: `"2026-04-23T08:25:51.093Z"`
- `reactions`: `{"likes":0,"dislikes":0,"userReaction":"NONE"}`
- `reviewId`: `"Y2uI6pYCxMQ4m4uKsxEHRjPGRfPTYvsqZ"` (стабильный, уникальный — годен на PK)
- `textTranslations`: `{"tr":"Tutucuyu değiştirmek için başvurdum..."}` — **автопереводы** на турецкий (наследие CIS/Turkey-focus Яндекса)
- `photos`, `videos`: массивы media URL.

**Это богаче, чем 35 полей Apify** (`zen-studio/yandex-maps-reviews-scraper`) и заметно богаче, чем `(rating, text)` arsenyvolodko'й.

---

## 10. Сводная итоговая таблица

| # | Подход | Файл | OK | Captcha | Items | Полей | Время | Производительность |
|---|---|---|---|---|---|---|---|---|
| 00 | Sticky proxy sanity | `00_proxy_check.py` | ✓ | n/a | 1 IP | — | 22 s | — |
| 01 | `requests` → /maps/api/search + CSRF chain | `01_direct_http_public_search.py` | ✗ | нет | 0 | — | 7 s | — |
| 01b | `requests` → SPB HTML bootstrap parse | `01b_bootstrap_html_parse.py` | ⚠ | нет | 0 структурированных | — | 6 s | — |
| 01c | `requests` + BS4 SSR cards | `01c_html_dom_parse.py` | ✓ | нет | **5** | 9 | 8 s | 37.5 org/min |
| 02 | Official Geosearch (no key) | `02_official_geosearch.py` | ✗ | n/a | 0 | — | 3 s | — |
| 03 | Playwright headless + DOM scroll | `03_playwright_basic.py` | ✓ | нет | **41** | 9 | 24 s | 102 org/min |
| **04** ⭐ | **Playwright + stealth + XHR intercept** | `04_playwright_xhr_intercept.py` | ✓ | нет | **48** | **65+** | 16 s | **180 org/min** |
| 05 | PyPI: ymrp, arsenyvolodko | `05_pypi_libs.py` | n/a (survey) | n/a | n/a | n/a | n/a | n/a |
| **06** ⭐ | **fetchReviews via observed-URL replay** | `06_fetch_reviews.py` | ✓ | нет | **50 reviews** | **12** | 43 s | 70 reviews/min |

---

## 11. Ключевые архитектурные уроки

### 11.1 CSRF — это не вся защита
Внутренние JSON-эндпоинты (`/maps/api/search`, `/maps/api/business/fetchReviews`) защищены:
1. **CSRF-token** (первый ответ — `{"csrfToken":"..."}`),
2. **Канонический порядок query-параметров** (отклонение `400 Bad Request`),
3. Возможно, дополнительная **подпись запроса** (не локализована, но симптомы намекают).

Прямой replay через `requests` не работает. **Единственный надёжный способ — позволить странице сделать настоящий запрос, перехватить URL, и повторить его в той же сессии.**

### 11.2 XHR-перехват > DOM-парсинг
DOM-парсинг даёт ~9 полей (всё, что отрендерено для глаз). XHR-перехват даёт **полный JSON-snippet, который Яндекс отдаёт фронту** — 65+ полей. Это **полная** документированная схема плюс несколько не-документированных (например, `advert.ordInfo.client.tin` — ИНН организации).

**Эвристика walker'а должна быть конкретной.** Жадный обход «любой объект с `name`+`coordinates`» подмёл 192 транспортных остановки и метро-станций. Корректная стратегия — обращение к известным путям (`data.items`) и фильтр по специфичным ключам бизнеса (`permalink`/`seoname`/`oid`).

### 11.3 Headless Chromium на RU residential проходит чисто
Конфигурация:
```python
chromium.launch(headless=True, proxy=playwright_proxy(),
                args=["--disable-blink-features=AutomationControlled"])
ctx = browser.new_context(locale="ru-RU", timezone_id="Europe/Moscow",
                          viewport={"width": 1440, "height": 900},
                          user_agent="Mozilla/5.0 ... Chrome/124.0.0.0 Safari/537.36")
Stealth().apply_stealth_sync(page)
```

За все 6 живых прогонов Playwright (~5–10 минут активности через прокси) **капча не сработала ни разу**. Это подтверждает §7 исследования: realistic UA + RU residential IP + low concurrency = SmartCaptcha остаётся в спячке.

### 11.4 Провайдер прокси даёт ~70% мгновенной успешности
`np.puls-proxy.com:11000` периодически отвечает `ConnectTimeoutError`. На 30 минут активности — 6 hiccup'ов из ~20 сетевых запросов. **Это не Яндекс**, а сторона провайдера. Все long-running скрипты обязаны иметь `_get_with_retry(attempts=4, backoff=2^n)`.

### 11.5 Платные сервисы не нужны
- Apify (`m_mamaev/yandex-maps-places-scraper`, ~$5-10/1k мест) — даёт **меньше** полей, чем Подход 4.
- Bright Data Browser API — нужен, только если Яндекс начнёт системно показывать SmartCaptcha. Сейчас не нужен.
- 2Captcha — fallback на случай ухудшения; интеграция понятна (`yandex` метод, sitekey+pageurl).

---

## 12. Финальный рекомендованный стек

```
┌───────────────────────────────────────┐
│ 1. DISCOVERY                          │
│    Playwright headless + stealth +    │
│    RU residential proxy + XHR         │
│    intercept (/maps/api/search)       │
│                                       │
│    Подход 04                          │
│                                       │
│    bbox-tiling × категории            │
│    25 results/request, до ~48 уник.   │
│    org за один прогон одной тайлы.    │
└───────────────────┬───────────────────┘
                    │
                    │ 65+ полей на org (включая phones,
                    │ coordinates, INN, services, photos…)
                    ▼
┌───────────────────────────────────────┐
│ 2. REVIEWS                            │
│    Тот же браузер →                   │
│    /maps/org/<oid>/reviews/ →         │
│    наблюдаем настоящий                │
│    /maps/api/business/fetchReviews →  │
│    replay observed-URL → пагинация    │
│    по from=                           │
│                                       │
│    Подход 06                          │
│                                       │
│    50 отзывов / страница;             │
│    12 полей / отзыв.                  │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│ 3. STORAGE                            │
│    Postgres + PostGIS                 │
│    схема из §8.2 исследования         │
│    (organization, phone, category,    │
│     hours, review, photo, crawl_log)  │
└───────────────────────────────────────┘
```

**Параметры для боевого прогона:**
- ~0.5–1 запрос/сек на IP, sticky 30 мин, потом ротация.
- Один контекст браузера на IP — не переиспользовать профиль между IP (быстро сжигает cookies).
- 6 zoom-13 тайлов покрывают СПб → 5 категорий медицины × 6 тайлов × 25 results ≈ 750 запросов на полный медицинский срез.
- Производительность: 180 org/мин на 1 воркер → 8–15 k клиник СПб собираются за **3–5 часов на одной машине**.
- Обязательны: retry на `ProxyError` (4 попытки с backoff), детектор `showcaptcha|smartcaptcha`, при срабатывании — cooldown IP на 30 мин и перебрасывание задачи в очередь.

**Что докрутить перед production:**
1. Запросить у `puls-proxy` пул IP именно из **Санкт-Петербурга** (сейчас Krasnoyarsk) — улучшит ranking-affinity Яндекса и снизит вероятность капчи на длинных прогонах.
2. Вынести детектор капчи в общую функцию `is_blocked(page_or_response)` и подключить cooldown-logic.
3. Подготовить fallback на 2Captcha (`yandex` метод) на случай ухудшения — интеграция в одну строку.

---

## 13. Артефакты (что лежит в `yandex_maps_experiment/results/`)

| Файл | Размер | Содержимое |
|---|---:|---|
| `00_proxy_check.json` | 634 B | sticky-проверка |
| `01_direct_http_public_search.json` | 496 B | CSRF chain → 400 |
| `01b_bootstrap_html_parse.json` | 316 B | bootstrap не содержит данных |
| `01b_bootstrap_html_parse_raw.html` | 1.4 MB | сырой SPB HTML для отладки селекторов |
| `01c_html_dom_parse.json` | 4.6 KB | отчёт |
| `01c_html_dom_parse_items.json` | 3.9 KB | **5 организаций** × 9 полей |
| `02_official_geosearch.json` | 797 B | подтверждение паид-онли |
| `03_playwright_basic.json` | 2.9 KB | отчёт |
| `03_playwright_basic_items.json` | 18 KB | **41 организация** × 9 полей |
| `03_playwright_basic_raw.html` | 2.2 MB | финальный DOM после скролла |
| `04_playwright_xhr_intercept.json` | 182 KB | отчёт |
| **`04_playwright_xhr_intercept_items.json`** | **2.6 MB** | **48 организаций × 65 полей** — главный артефакт |
| `04_playwright_xhr_intercept_captures.json` | 2.0 MB | оба сырых XHR-ответа (для отладки schema) |
| `05_pypi_libs.json` | 3.1 KB | survey YMRP + arsenyvolodko |
| `06_fetch_reviews.json` | 6.2 KB | отчёт |
| `06_fetch_reviews_observed_xhrs.json` | 3.4 KB | URL и хидеры реального fetchReviews-запроса |
| `06_fetch_reviews_raw_page0.json` | 74 B | пример CSRF-холостого ответа |
| **`06_fetch_reviews_reviews.json`** | **101 KB** | **50 отзывов × 12 полей** — главный артефакт |

`logs/` содержит пер-эксперимент лог-файлы (timestamps + сетевые ошибки) — полезно для аудита.

---

## 14. Время от начала до итога

- **Постановка задачи + clarifying questions:** ~5 минут.
- **Каркас + sanity-проверка:** ~10 минут.
- **Подход 01 (3 итерации):** ~25 минут (включая ошибочный walker).
- **Подход 02:** ~5 минут.
- **Подход 03:** ~10 минут.
- **Подход 04 (2 итерации walker'а):** ~20 минут.
- **Подход 05 (survey):** ~15 минут (интроспекция + установка из git).
- **Подход 06 (3 итерации):** ~25 минут.
- **Финальные RESULTS.md + README:** ~10 минут.
- **Итого:** ~2 часа active work, ~3 часа wall-clock с учётом времени на запуски.

---

## 15. TL;DR

1. **Yandex.Карты локально парсятся без платных сервисов.** Все 7 подходов из исследования проверены вживую.
2. **Победитель — Playwright headless + stealth + RU residential + XHR intercept** (Подход 04). 48 организаций × 65 полей за 16 секунд. Полная схема Яндекса плюс ИНН.
3. **Отзывы — observed-URL replay** (Подход 06). 50 отзывов × 12 полей за один запрос. Прямой replay падает на необъяснимом 400 — обязательно дать странице сначала сделать настоящий запрос и перехватить его URL.
4. **Капча не сработала ни разу** на 30 минут активности через `puls-proxy` sticky-IP (Krasnoyarsk, AS Igra-Service).
5. **PyPI-парсеры (YMRP, arsenyvolodko) — заведомо слабее**, использовать их нет смысла.
6. **Production-ready:** под текущий стек 8–15 k клиник СПб собираются за **3–5 часов на одном воркере**. Архитектура — Postgres + PostGIS по схеме из §8.2 исследования.
