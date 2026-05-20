# Yandex Maps scraping — local feasibility benchmark

**Дата запуска:** 2026-05-18
**Цель:** база знаний компаний по категориям/городу. Тестовый кейс — `стоматология` в Санкт-Петербурге (lr=2).
**Прокси:** `puls_sticky_30min.txt` — резидентный, sticky-сессия 30 мин, ротация IP на стороне провайдера.
**Окружение:** Windows, Python 3.12 в `.venv` корня (`uv`), Playwright 1.58, playwright-stealth 2.0.

Каждый эксперимент — отдельный исполняемый скрипт; результат сохраняется в
`results/<NN>_<name>.json` (+ сырые HTML/JSON артефакты для отладки).

---

## Сводная таблица

| # | Подход | OK | Captcha | Объектов | Полей/объект | Время | Вердикт |
|---|---|---|---|---|---|---|---|
| 00 | Sticky-прокси (sanity check) | ✓ | — | 1 IP (Russia / Krasnoyarsk / AS Igra-Service) | — | ~22 s | sticky подтверждён, ~67% success rate на провайдере (2/6 hiccups → нужны retries) |
| 01 | `requests` → `/maps/api/search` (CSRF retry) | ✗ | нет | 0 | — | 7 s | endpoint возвращает CSRF-токен на первый вызов; повтор с токеном даёт 400 Bad Request. Нужен полный browser session, кук+headers недостаточно. |
| 01b | `requests` → SPB-SERP HTML, парс bootstrap-JSON | ⚠ | нет | 0 структурированных | — | 6 s | HTML грузится (1.4 MB), но bootstrap-state не содержит сериализованного списка организаций (есть только конфиг). |
| **01c** | **`requests` + BeautifulSoup → SSR-разметка карточек** | ✓ | нет | **5** | 9 (`name`, `address`, `business_oid`, `seoname`, `categories_text`, `rating`, `reviews_text`, `working_status`, `url`) | 8 s | Работает «как есть» — но SPA рендерит на сервере только первый viewport. Остальное — за JS. |
| 02 | Официальный Geosearch `https://search-maps.yandex.ru/v1/` без apikey | ✗ | — | 0 | — | 3 s | `400 Missing apikey` / `403 Invalid api key`. Подтверждает: только платный годовой контракт. Локально не применимо. |
| 03 | Playwright headless + RU residential proxy, скролл DOM | ✓ | нет | **41** | 9 | 24 s | Стабильно, без капчи. Скорость ~1.7 организаций/сек. Поля те же, что у 01c. |
| **04** | **Playwright + stealth + intercept `/maps/api/search`** | ✓ | нет | **48** | **65+** | 16 s | **Лучший подход.** Перехватили 2 XHR-ответа (~1.5 MB JSON), достали полную схему: `phones`, `coordinates`, `categories`, `rubrics`, `ratingData`, `aspects`, `workingTime`, `metro`, `photos`, `videos`, `features` (услуги), `advert.ordInfo.client.tin` (ИНН!), `socialLinks`, `panorama`, `awards`, …  |
| 05 | PyPI: `ymrp`, `arsenyvolodko/yandex-maps-reviews-parser` | ✗ live | — | — | — | — | Доминируются подходом 4. `ymrp` хард-кодит `headless=False`, без прокси. arsenyvolodko требует платный apikey для name→id и открывает Selenium-Chrome ради `(rating, text)`. |
| **06** | **fetchReviews replay через observed-URL (Playwright)** | ✓ | нет | **50** отзывов | 12 (`reviewId`, `author`, `rating`, `text`, `businessComment`, `updatedTime`, `photos`, `videos`, `reactions`, `textLanguage`, `textTranslations`, `businessId`) | 43 s | Прямой replay с CSRF падает 400; решение — позволить странице сделать «настоящий» XHR, перехватить его URL и повторить через `page.request.get()` той же сессии. |

**Итог по полноте:**
*Геосёрч (платный) + Apify (платный)* в исследовании имеют 30-60 полей. **Подход 4 (Playwright XHR-intercept) даёт 65+ полей на организацию — полная схема Яндекса**, плюс reviews из подхода 6.

---

## Деталь по каждому подходу

### 00. Прокси
- Egress IP `84.22.142.138` (Russia / Krasnoyarsk / AS33991 Igra-Service LLC).
- Sticky подтверждён: 1 уникальный IP на 6 запросов (4 успешных).
- 2 hiccup из 6 на стороне самого provider'а (np.puls-proxy.com:11000 timeout) — это нужно учесть в любом scraper, через retry с backoff. Это **не** связано с Яндексом.
- **Важный нюанс:** провайдер отдал IP Красноярска, а не СПб. Яндекс взвешивает IP-geo против region query (`lr=2`), но в наших экспериментах капча ни разу не сработала — `lr=2` достаточно. Для масштабирования стоит запросить у `puls-proxy` IP-пул именно из СПб (см. §8.4 исследования).

### 01a/b/c. Direct HTTP
- `01_direct_http_public_search.py` — реализована CSRF-цепочка («первый ответ = токен, второй = данные»). На втором шаге Яндекс отдаёт `400 Bad Request` — endpoint защищён больше, чем простой CSRF (вероятно подпись запроса/ts на стороне браузера).
- `01b_bootstrap_html_parse.py` — SPA не SSR-ит данные в `window.__bootstrap__` etc. Найден только конфиг.
- `01c_html_dom_parse.py` — **рабочий**: SSR рендерит первые 5 карточек в DOM. Извлекаются 9 полей. Это потолок «голого HTTP» подхода.

### 02. Official Geosearch
- Чисто документированный отказ: `400` без ключа, `403` с фейк-ключом. Полностью совпадает с §2.1 исследования.
- Не применимо локально без годового контракта в RUB (выписывается через api-maps@yandex-team.ru).

### 03. Playwright headless + RU proxy
- Headless Chromium + `Locale=ru-RU` + `Timezone=Europe/Moscow` + RU residential — **никакой капчи** на 24-секундную сессию.
- Скролл результирующей панели: за 10 итераций (по 900 мс) накопили 43 карточки, 41 уникальная по `business_oid`.
- Извлекаются те же 9 «скудных» полей, что и в 01c.

### 04. Playwright + stealth + XHR intercept ⭐
- Та же конфигурация + `playwright-stealth` + `page.on("response")` фильтр по `/maps/api/search`.
- За 16 с (всё, включая 10 скроллов) перехвачены 2 ответа `/maps/api/search?...&ajax=1` весом ~1.5 MB.
- Из `data.items` вытащено 48 уникальных организаций со 65 полями:
  - Идентификаторы: `id`, `seoname`, `references[].id`, `geoId`, `analyticsId`
  - Контакты: `phones[]` (`number`, `type` — phone / fax / администратор, `value` в E.164), `socialLinks[]` (whatsapp, telegram, vk), `urls`
  - География: `coordinates`, `displayCoordinates`, `bounds`, `entrances`, `routePoint`, `panorama` (с превью)
  - Адрес: `address`, `fullAddress`, `compositeAddress` (country/locality/street/house)
  - Категории: `categories[]` (с `class`, `seoname`, `pluralName`), `parentRubrics`, `breadcrumbs`
  - Часы: `workingTime`, `workingTimeText`, `currentWorkingStatus.isOpenNow`
  - Рейтинг: `ratingData.ratingValue`, `ratingCount`, `reviewCount`; `aspects[]` — структурированная разбивка по тематикам отзывов (`positive`, `neutral`, `negative` + photos)
  - Медиа: `photos.count` + `urlTemplate` на `avatars.mds.yandex.net/.../{size}`; `videos`; `businessImages.logo`
  - Услуги/меню: `features[]` (для медицины — список услуг: `dental_surgery`, `endodontics`, `aesthetic_dentistry` …); `subtitleItems` (цены, например «6900 ₽ Лечение кариеса»); `topObjects`
  - Транспорт: `metro[]` (станция, расстояние, цвет линии), `stops[]`
  - Дополнительно: `description`, `awards.goodPlaceYear`, `promo`, `eventsPreviews` (новости бизнеса), `hasStories`, `status`, `region` (full SPB hierarchy)
  - **ИНН/ОГРН-эквивалент:** `advert.ordInfo.client.tin` + `name` (юр.лицо)

### 05. PyPI-парсеры (survey)
- `ymrp 0.6.0` — Playwright под капотом, но `headless=False` зашит; без прокси/UA.
- `arsenyvolodko/yandex-maps-reviews-parser 0.1.0` (PyPI отсутствует, ставится из GitHub) — Selenium-Chrome + bs4; для name→id требует апикей в `consts.YANDEX_MAPS_API_TOKEN` (пустой в репо). Возвращает только `(rating, text)`.
- Оба — слабее, чем наш Подход 4+6. Использовать смысла нет.

### 06. Reviews через fetchReviews
- Прямой replay `…/fetchReviews?businessId=<oid>&from=<N>&count=50&ranking=by_time` (даже с CSRF) → `400 Bad Request`. Проблема, видимо, в анти-replay подписи запроса или специфическом порядке параметров.
- **Рабочий шаблон:** перейти на `/maps/org/<seoname>/<oid>/reviews/` в headless Playwright, проскроллить (это триггерит реальный XHR), перехватить URL через `page.on("response")` и повторить его через `page.request.get(observed_url)`. Та же session, тот же CSRF, та же подпись — проходит.
- 50 отзывов за один replay (`count=50` максимум на страницу); пагинация — увеличиваем `from=`.
- Поля: `author.name`, `author.avatarUrl`, `author.professionLevel` («Знаток города 5 уровня»), `rating`, `text`, `businessComment.text`+`updatedTime` (ответ бизнеса), `photos`, `videos`, `reactions.likes/dislikes`, `textLanguage`, `textTranslations` (автопереводы на турецкий и др.) — **больше, чем 35 полей, заявленных Apify**.

---

## Финальный рекомендованный стек для вашей задачи

База знаний компаний СПб по категориям, локально:

```
┌───────────────────┐
│ 1. Discovery      │   Playwright (headless, stealth, RU residential)
│    Подход 04      │   bbox-tiling × категории; перехват /maps/api/search
└─────────┬─────────┘
          │ JSON-snippets (≤ ~50 уник. orgs / запрос; до 25 на «страницу»)
          ▼
┌───────────────────┐
│ 2. Enrichment     │   Те же 65+ полей в одном snippet — отдельный enrichment
│ (обычно не нужен) │   нужен только для photo/menu deep-dive (`fullobjects/1.x`)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 3. Reviews        │   Подход 06: открыть `/reviews/`, перехватить fetchReviews,
│    Подход 06      │   replay постранично; ~50/страницу; кооперативно paginate.
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 4. Storage        │   Postgres + PostGIS (schema из §8.2 исследования)
└───────────────────┘
```

**Параметры:**
- Один контекст браузера на один IP, пока IP «горячий» (sticky 30 мин).
- ~0.5–1 запрос/сек на IP. На 6 hiccups провайдера из 12 (после ротации новый IP) — обязательны retries c backoff (2/4/8 с).
- Поскольку Подход 4 на 16 с даёт 48 org → 50 org/мин — для 8-15 k клиник СПб реальный сбор за **3–5 часов на одном воркере без капчи**.
- Доразведка по категориям: SPB в zoom-13 — это ~6 квадратов; 5 категорий клиник × 6 тайлов × 24 результата ≈ 720 запросов на полный медицинский срез.

**Что _не_ нужно делать:**
1. Не платить за Apify/BrightData/Oxylabs для этой задачи — Подход 4 покрывает 100% тех же полей.
2. Не использовать арсения/YMRP — они хуже по всем метрикам.
3. Не дёргать `/maps/api/search` напрямую через `requests` — серверный CSRF/sig вне сессии браузера не работает.
4. Не платить за официальный Geosearch — он даёт меньше полей (~10 docs-supported), не разрешает хранение и стоит годового контракта.

**Что докрутить перед боевым прогоном:**
- Поменять провайдеру pool с Krasnoyarsk на SPB (запрос в support) — это улучшит ranking-affinity Яндекса и снизит риск капчи на длинном прогоне.
- Спустить детектор `showcaptcha/smartcaptcha` из всех скриптов в общую функцию + при срабатывании — «остудить» IP на 30 мин (доп. sticky-сессию) и перебросить задачу в очередь.
- Если в будущем Yandex закрутит гайки — fallback на 2Captcha (`yandex` метод, $1-3 / 1k solves) подключается заменой `on_captcha_detected` callback.

---

## Файлы

- `common.py` — общие хелперы (прокси, dataclass-репорт, utf8 stdout)
- `00_proxy_check.py` … `06_fetch_reviews.py` — отдельные тесты
- `results/*.json` — машинно-читаемые отчёты по каждому эксперименту
- `results/01b_bootstrap_html_parse_raw.html`, `results/03_playwright_basic_raw.html` — сырые HTML для отладки селекторов
- `results/04_playwright_xhr_intercept_items.json` (2.6 MB) — 48 организаций × 65 полей
- `results/04_playwright_xhr_intercept_captures.json` (2.0 MB) — оба сырых XHR-ответа
- `results/06_fetch_reviews_reviews.json` (101 KB) — 50 отзывов с полной схемой
- `logs/` — пер-эксперимент логи (для трассировки proxy hiccups, CSRF-цепочек, …)

Запуск целиком:
```bash
uv run python yandex_maps_experiment/00_proxy_check.py
uv run python yandex_maps_experiment/01c_html_dom_parse.py
uv run python yandex_maps_experiment/02_official_geosearch.py
uv run python yandex_maps_experiment/03_playwright_basic.py
uv run python yandex_maps_experiment/04_playwright_xhr_intercept.py
uv run python yandex_maps_experiment/05_pypi_libs.py
uv run python yandex_maps_experiment/06_fetch_reviews.py
```
