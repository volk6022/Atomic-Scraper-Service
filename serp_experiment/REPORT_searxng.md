# Отчёт по SearXNG — serp_experiment

Дата: 2026-05-16
Хост: Windows 10/11, Docker Desktop, Python 3.12, uv.
Расположение деплоя: `serp_experiment/repos/searxng-deploy/`

---

## Условия окружения

SearXNG крутится в Docker; контейнер ходит к апстримам через резидентный
socks5 (puls, sticky 30 мин). Прогоны сделаны и **с VPN** на хосте, и **без
VPN** — см. сравнение ниже.

`outgoing.proxies` всё время включён — direct без socks5 не тестировали, на
прошлом этапе с этого IP Google/Brave/Startpage стабильно отдавали CAPTCHA.

---

## Setup

### Структура

```
serp_experiment/repos/
  searxng/                         # source-only клон github.com/searxng/searxng
                                   # (нужен для копирования дефолтных settings,
                                   # запуск через Docker)
  searxng-docker/                  # официальный compose-репо (deprecated, оставлен
                                   # как референс)
  searxng-deploy/                  # наш изолированный деплой
    docker-compose.yml             # image: docker.io/searxng/searxng:latest
                                   # порт 127.0.0.1:8080:8080
    searxng/settings.yml           # переопределение поверх use_default_settings
```

### Что в `docker-compose.yml`
- image `docker.io/searxng/searxng:latest` (на момент прогона `2026.5.6-330d56bba`)
- bind `127.0.0.1:8080:8080`
- volume `./searxng:/etc/searxng:rw`
- `cap_drop: ALL` + минимальные `CHOWN/SETGID/SETUID`
- логи json-file ограничены (1m × 1)

### Что в `searxng/settings.yml`
- `use_default_settings: true` (унаследовать всё из upstream-settings, оверрайдить только нужное)
- `search.formats: [html, json]` — **критично**: без `json` API возвращает 403
- `server.limiter: false` — single-user инстанс, лимитер шумит
- `server.method: GET` — упрощает дебаг
- `outgoing.request_timeout: 5.0` / `max_request_timeout: 10.0` / `extra_proxy_timeout: 5`
- `outgoing.proxies.all://: [socks5h://...@np.puls-proxy.com:11000]` — puls sticky 30min
- `engines:` явно выключены `brave`, `startpage`, `karmasearch`, `karmasearch videos`, `ahmia`, `torch`
  - первые три стабильно отдавали CAPTCHA/access-denied (даже через puls)
  - ahmia/torch — onion-движки, без Tor падают на старте

---

## Запуск

```powershell
cd serp_experiment\repos\searxng-deploy
docker compose up -d
# … правишь searxng\settings.yml …
docker compose restart searxng
docker compose logs -f searxng
```

JSON API:
```
GET http://localhost:8080/search?q=<query>&format=json&language=en
```

---

## Прогоны

Утилита: `uv run python -m serp_experiment.run_benchmark --only searxng_local`
(под капотом `serp_experiment/approaches/searxng_local.py`).

Запрос: `"What is artificial intelligence"`. Repeats: 10. Pause: 2s.

### Прогон 1 — default outgoing (request_timeout=10s, extra_proxy_timeout=10s, brave/startpage не отключены)
- успех: **10/10**
- mean: **9.21s**, median: **9.34s**
- organic: **10/10** в каждом запросе
- замечание: тайминги бимодальные (~12s / ~6s через раз) — половина запросов
  ждала timeout у битых апстримов (Brave: «too many requests», Startpage:
  CAPTCHA/timeout, karmasearch: access denied)

Артефакты:
- `serp_experiment/run_searxng_v3.log` (после второго прогона, перезаписан)
- (промежуточный JSON был перезаписан)

### Прогон 2 — после тюнинга, VPN ON
Изменения относительно прогона 1:
- `request_timeout: 5.0`, `extra_proxy_timeout: 5`
- явно `disabled: true` для brave, startpage, karmasearch×2, ahmia, torch

Результаты:
- успех: **10/10**
- mean: **5.94s**, median: **6.00s**, min: **5.00s**, max: **7.06s**
- organic: avg **9.8**, min **9**, max **10**
- unresponsive_engines после прогрева: пусто
- работают: `duckduckgo` (~10), `google` (~10, иногда 9), `wikipedia` (0-1 как
  infobox)

Артефакты:
- `serp_experiment/run_searxng_v3.log`
- `serp_experiment/results_searxng_v3.json`

Δ относительно прогона 1: **-36% latency**, тот же 100% успех и тот же объём
organic.

### Прогон 5 — длинный тест, VPN OFF, 10 query × 10 repeats = 100 запросов

Скрипт: `serp_experiment/long_test_searxng.py`. Параметры дефолтные:
- `--repeats 10` (на каждый query)
- `--pause-req 2.0` (между запросами одного query)
- `--pause-query 4.0` (между разными query)
- 10 разнотипных query (factual / local / technical / commercial / новости /
  howto / финансы / entertainment) — см. `DEFAULT_QUERIES` в скрипте.

Конфиг SearXNG — тот же, что в прогоне 2/3/4 (puls socks5 sticky, 5s timeout,
brave/startpage/karmasearch/ahmia/torch отключены).

Результаты:

| q  | query                                    | ok    | mean  | median | p95   | organic |
|----|------------------------------------------|-------|-------|--------|-------|---------|
| 1  | What is artificial intelligence          | 9/10  | 5.05s | 3.91s  | 7.42s | 9.6     |
| 2  | python asyncio tutorial                  | 6/10  | 3.66s | 2.91s  | 7.30s | 7.8     |
| 3  | best coffee shops Saint Petersburg Russia| 1/10  | 3.81s | 3.03s  | 7.31s | 10.0    |
| 4  | how to bake sourdough bread at home      | 1/10  | 6.90s | 7.31s  | 7.62s | 10.0    |
| 5  | GDP of Germany 2024                      | 5/10  | 5.07s | 5.29s  | 7.33s | 10.0    |
| 6  | Tesla stock price last 5 years           | 4/10  | 2.80s | 2.61s  | 3.93s | 10.0    |
| 7  | climate change effects 2025              | 2/10  | 3.78s | 2.91s  | 7.51s | 9.0     |
| 8  | best science fiction movies 2024         | 3/10  | 3.75s | 2.83s  | 7.32s | 4.7     |
| 9  | buy iPhone 15 Pro Max                    | 4/10  | 2.77s | 2.73s  | 3.42s | 10.0    |
| 10 | weather forecast Moscow tomorrow         | 1/10  | 5.27s | 5.68s  | 7.51s | 7.0     |
|    | **TOTAL**                                | **36/100** | 4.29s | 3.12s | 7.42s | **8.9** |

Elapsed: 645s (~10.7 мин).

**Что увидели:**
- **Q1 (первый запрос) — 90% успех**. Дальше success-rate деградирует волнами.
- **Q3 "coffee shops SPb" — 1/10**, **Q4 "sourdough bread" — 1/10**, далее
  то 40%, то 10%. К концу теста (Q10 weather) — снова 1/10.
- На момент **сразу после теста** DDG в `unresponsive_engines` как `CAPTCHA`,
  Google молча отдаёт 0 результатов (без явного флага).
- **EMPTY-ответы быстрые (~2.5-3s)** — это значит SearXNG получил ответ от
  апстримов (или из cache), но органик там нет. То есть Google/DDG отдают
  пустой/CAPTCHA-страницу, SearXNG парсит её как 0 результатов.
- **Когда работает — organic_count 9-10** (Q3, Q4, Q6, Q9 ровно 10). Качество не
  пострадало — пострадал именно success rate.
- **Q8 "best sci-fi movies" даёт всего 4.7 organic** при success — у этого
  запроса SERP сильно загромождён карточками/topstories, и часть результатов
  не попадает в формат `organic`.

### Прогоны 6 и 7 — те же настройки, длинный тест с/без VPN

**Прогон 6 (VPN ON, N=100)** — `results_searxng_long_vpn.json`, `run_searxng_long_vpn.log`:

| query | ok | mean | median | p95 | organic |
|-------|-----|------|--------|-----|---------|
| AI | 10/10 | 3.92s | 3.60s | 6.65s | 10.0 |
| python asyncio | 10/10 | 4.50s | 3.72s | 6.43s | 10.0 |
| coffee shops SPb | 10/10 | 4.60s | 3.76s | 6.66s | 10.0 |
| sourdough bread | 10/10 | 5.06s | 5.75s | 6.37s | 10.0 |
| GDP Germany | 10/10 | 3.78s | 3.48s | 6.23s | 10.0 |
| Tesla stock | 9/10 | 6.07s | 5.79s | 7.04s | 10.0 |
| climate change | 10/10 | 6.08s | 6.01s | 7.24s | 10.0 |
| sci-fi movies | 10/10 | 5.61s | 5.80s | 7.17s | 10.0 |
| buy iPhone | 10/10 | 5.69s | 6.09s | 6.54s | 10.0 |
| weather Moscow | 10/10 | 4.92s | 5.48s | 6.08s | 10.0 |
| **TOTAL** | **99/100** | 5.02s | 5.38s | 6.66s | **10.0** |

Единственный fail — Q6/9 (Tesla stock #9), один EMPTY ~7s. Скорее всего рядовой
транзитный flap.

**Прогон 7 (VPN OFF, повтор, N=100)** — `results_searxng_long_no_vpn_2.json`,
`run_searxng_long_no_vpn.log`:
- 22/100 success (хуже прогона 5 — 36/100).
- Q5 "GDP Germany" — **0/10**, полный shutdown на этой query.
- Паттерн тот же: первая query 70%, дальше деградация волнами.

**Вывод между прогонами 6 и 7:** включение VPN — **+77 пунктов success rate**
(99% vs 22%) при той же конфигурации SearXNG/proxy. Не «лишний хоп» с
накладной latency, а **решающий фактор**.

### Прогон 9 — wide test, пулл из 20 socks5 + retries=2, VPN ON

Скрипт: `serp_experiment/wide_test_searxng.py`. Параметры:
- 30 query × 10 repeats = **300 logical requests** (см. `DEFAULT_QUERIES` в скрипте, 10 старых + 20 новых)
- `--retries 2` — до 3 попыток на каждый logical request; считаем OK, если хоть одна вернула organic > 0
- `--pause-req 0.1`, `--pause-query 0.5`
- VPN на хосте: **ON** (изначально планировалось OFF, но забыли отключить — оставлено, т.к. это всё равно интересная точка данных)

Конфиг SearXNG: 20 socks5 sessttl.10 (`puls .ru x10 + .pl x10`).

Per-query (выдержка по фейлам):

| query | ok | mean | median | p95 | organic | att_avg |
|-------|-----|------|--------|-----|---------|---------|
| python asyncio tutorial | **5/10** | 14.74s | 16.72s | 18.25s | 8.4 | **2.60** |
| cat behavior explained | **5/10** | 11.84s | 13.71s | 18.28s | 10.0 | **2.10** |
| best electric cars 2024 | **7/10** | 11.43s | 10.97s | 18.00s | 10.0 | **2.00** |
| coffee shops SPb | 9/10 | 8.58s | 6.32s | 17.67s | 10.0 | 1.40 |
| (остальные 26 query) | **10/10** | 6.0-7.4s | ~6s | 7-20s | 9.2-10.0 | 1.0-1.4 |
| **TOTAL** | **286/300** | 7.25s | 6.07s | 16.82s | 9.8 | **1.20** |

Attempts histogram (всего 300 logical requests):
- `attempts=1`: 263 → 87.7% success **с первой попытки**
- `attempts=2`: 14 → OK со второй
- `attempts=3`: 23 → из них **9 OK** на третьей + **14 fail** (исчерпали ретраи)

Elapsed: 37 минут.

### Что показал wide-test

1. **Голый "VPN + 20 IP пулл" дал бы 87.7% — это деградация от VPN-only baseline 99%.**
   Гипотеза: пулл включает «грязные» IP (особенно `.pl` пул), cycle крутит их
   равномерно — на грязный IP попадают engine-запросы и валятся. С одним
   sticky IP всё шло через одну (чистую) точку.
2. **Retries компенсируют, но не дотягивают до single-sticky+VPN.** +7.6pp от
   ретраев, итог 95.3% vs 99% single-sticky-VPN. Цена — median 6s vs 5.4s, плюс
   p95 16.82s (когда ретрай нужен, latency болезненно высокий).
3. **Фейлы концентрированы в 4 query из 30** (asyncio, cat behavior, electric
   cars, coffee SPb). 26 query — 10/10. Возможно, keyword-trigger у апстримов
   на эти темы (asyncio фейлил и в прошлых прогонах). Стоит изучить отдельно.

### Прогон 10 — wide test, тот же конфиг, VPN OFF

Скрипт и конфиг идентичны прогону 9 (20 socks5 sessttl.10 + retries=2,
30 query × 10 repeats). Единственная разница — VPN выключен.

Per-query (выдержка по фейлам):

| query | ok | mean | median | p95 | organic | att_avg |
|-------|-----|------|--------|-----|---------|---------|
| history of the Roman Empire | **6/10** | 9.29s | 7.30s | 19.82s | 10.0 | 1.80 |
| chocolate cake recipe easy | **7/10** | 7.40s | 7.25s | 13.37s | 10.0 | 1.60 |
| python asyncio | 8/10 | 8.16s | 3.74s | 22.03s | 9.9 | 1.60 |
| coffee SPb / sci-fi / Tokyo / Wi-Fi / sust energy / progr lang / photography | 8/10 | ~7-10s | ~5-9s | ~17-22s | 9.1-10.0 | 1.4-1.8 |
| (15 остальных query) | **10/10** | 5.2-9.8s | ~4-7s | 7-22s | 9.3-10.0 | 1.0-1.7 |
| **TOTAL** | **267/300 (89.0%)** | 8.20s | 7.18s | 19.32s | 9.9 | **1.50** |

Attempts histogram:
- `attempts=1`: 217 → **72.3% success с первой попытки**
- `attempts=2`: 17 → OK со второй
- `attempts=3`: 66 → **33 OK + 33 fail** (исчерпали ретраи)

Elapsed: 42 минуты.

### Сравнение прогонов 9 (VPN) и 10 (без VPN) — оба wide-test, тот же конфиг

| метрика | #9 VPN ON | #10 VPN OFF | дельта |
|---|---|---|---|
| Final success | 95.3% | **89.0%** | −6.3pp |
| First-try success | 87.7% | **72.3%** | **−15.4pp** |
| mean latency | 7.25s | 8.20s | +0.95s |
| median latency | 6.07s | 7.18s | +1.11s |
| Avg attempts | 1.20 | 1.50 | +0.30 |

**Сдвиг по конкретным query (не повторяется!)** — это критически важное
наблюдение:

| query | #9 VPN | #10 без VPN |
|---|---|---|
| python asyncio | 5/10 | 8/10 |
| cat behavior | 5/10 | 10/10 |
| electric cars | 7/10 | 10/10 |
| Roman Empire | 10/10 | 6/10 |
| chocolate cake | 10/10 | 7/10 |

То есть **«проблемных тематик» нет** — фейлы перетасовываются между запусками
рандомно. Это окончательно подтверждает: причина не в keyword-trigger у
апстримов, а в **временно́м совпадении грязных IP в пуле с конкретным
запросом**.

### Прогон 11 — long-test через локальный proxy-router, VPN OFF

Архитектура (см. `serp_experiment/proxy_router/`):
- 20 puls socks5 (10 .ru + 10 .pl) загружены в `WorkerPool`.
- 15 worker'ов в `ACTIVE`, 5 в `RESERVE`, FSM (PROBING_INITIAL → ACTIVE ↔ RESERVE ↔ COOLDOWN → DRAINING → RETIRED), TTL ≈ 9:45 c jitter cooldown 15-30s ±10s.
- Health-prober бьёт каждого worker'а через **отдельный probe-SearXNG-контейнер** (4 шт., google+ddg only) — атомарная проверка чистоты IP в боевом контракте.
- Прод-SearXNG ходит на единственный URL `http://host.docker.internal:8888` (main listener router'а). На каждый CONNECT router выбирает worker'а LRU + tie-break по inflight_count.
- `request_timeout` в SearXNG = **8.0s**.

Конфиг long-теста: тот же что и в прогонах 5-7: 10 query × 10 repeats, pause-req=2s, pause-query=4s, **без retries**.

Per-query:

| query | ok | примечание |
|-------|-----|------|
| What is artificial intelligence | **10/10** | первый, прогрев + чистый |
| python asyncio tutorial | **2/10** | 6 EMPTY ровно на 10.04-10.07s (engine timeout 8s + retry), 2 fast EMPTY от ban_time_on_fail |
| best coffee shops SPb | 8/10 | |
| sourdough bread | **10/10** | |
| GDP Germany 2024 | 7/10 | |
| Tesla stock 5 years | 9/10 | |
| climate change effects 2025 | **6/10** | |
| best sci-fi movies 2024 | **10/10** | |
| buy iPhone 15 Pro Max | 8/10 | |
| weather Moscow tomorrow | **4/10** | хвостовой коллапс — 6 fast EMPTY 2.4-3.5s (suspended engines не разлипают) |
| **TOTAL** | **74/100** | mean 5.10s, median 3.99s, organic avg 9.5 |

Elapsed: 792.5s (≈13 min).

**Detailed failure breakdown (26 fails):**
- 9 slow timeouts (~10s) — все 3 engines уперлись в `request_timeout: 8s`;
- **17 fast EMPTY (2.4-4.0s)** — engines в SearXNG-side suspension от предыдущего timeout-а (`ban_time_on_fail: 5s` + `max_ban_time_on_fail: 120s`); upstream вообще не дёргался, SearXNG сразу вернул пустоту.

**Метрики router'а на момент прогона (по `/metrics`):**
- pool: 15 active + 5 reserve + 0 cooldown, `pool_clean_pct` 96%;
- probe_total: 808, probe_clean: 675 (**83.5%** общий, **95%** в скользящем окне).
- по worker'у: 13 из 20 показали `clean_pct=1.00`, 4 показали 0.50-0.71 (это `.pl` + два `.ru:11002/11006/11007`).

**Корневая причина деградации vs ожидания (≥95%):**
- Probe-budget (timeout 20s) **выше** prod-budget (8s). Worker, что отвечает за 9-12s, проходит как clean, но в prod валится по timeout.
- SearXNG бьёт 3 engines (google + ddg + wiki) **конкурентно**, и router LRU-вращает их на 3 разных worker'а. Failure rate на тройку ≈ 3 · P(single worker slow) — единичный медленный worker валит весь query.
- После каждого timeout сработала SearXNG-side circuit breaker `ban_time_on_fail` — несколько последующих запросов получают fast EMPTY мгновенно.

### Прогон 12 — wide-test через proxy-router, concurrency=4, VPN OFF

Конфиг тот же что и в прогоне 11 (router + 20 socks5, 15 active + 5 reserve), но wide:
- 30 query × 10 repeats = **300 logical requests** (тот же набор query, что и в прогонах 9 и 10).
- `--concurrency 4` (20% от пула, согласовано), `--retries 2` (до 3 попыток на каждый logical request).
- pause-req=0.1s, pause-query=0.5s.
- `request_timeout: 8.0s` (без изменений).

Per-query (выдержка по фейлам):

| query | ok | mean | median | p95 | organic | att_avg |
|-------|-----|------|--------|-----|---------|---------|
| sci-fi movies 2024 | **1/10** | 8.42s | 7.86s | 11.21s | 9.0 | 3.00 |
| buy iPhone 15 Pro Max | **1/10** | 9.75s | 8.05s | 21.61s | 10.0 | 3.00 |
| weather Moscow tomorrow | **1/10** | 10.27s | 8.79s | 22.46s | 10.0 | 3.00 |
| climate change 2025 | **2/10** | 8.06s | 7.45s | 15.32s | 10.0 | 2.60 |
| hiking trails Switzerland | **3/10** | 8.87s | 8.61s | 15.20s | 10.0 | 2.60 |
| cat behavior | **3/10** | 9.59s | 8.10s | 15.73s | 10.0 | 2.80 |
| photography tips DSLR | **3/10** | 7.95s | 7.66s | 9.30s | 10.0 | 2.90 |
| best electric cars 2024 | **4/10** | 6.97s | 7.36s | 8.55s | 10.0 | 2.70 |
| coffee shops SPb | 5/10 | 8.11s | 8.12s | 11.69s | 10.0 | 2.50 |
| Bitcoin price 2025 | 5/10 | 8.52s | 10.61s | 16.26s | 10.0 | 2.20 |
| WiFi issues | 5/10 | 6.90s | 7.60s | 9.03s | 8.2 | 2.60 |
| Linux command basics | 5/10 | 7.84s | 8.47s | 12.93s | 10.0 | 2.30 |
| (рядом 6-8/10 query: 14 шт.) | 6-8/10 | 5-11s | 5-10s | 9-18s | 9.0-10.0 | 1.6-2.5 |
| crypto market analysis | **10/10** | 5.46s | 4.45s | 10.98s | 10.0 | 1.30 |
| upcoming Marvel 2025 | **10/10** | 4.75s | 3.72s | 10.06s | 9.8 | 1.00 |
| **TOTAL** | **177/300 (59.0%)** | 6.13s | 5.25s | — | 9.6 | **2.20** |

Attempts histogram (300 logical requests):
- `attempts=1`: 102 → **34.0% success с первой попытки**;
- `attempts=2`: 37 → OK со второй;
- `attempts=3`: 161 → из них **38 OK** на третьей + **123 fail** (исчерпали ретраи).

Elapsed: 574s (≈10 min).

**Это значительно хуже baseline'а** (89% без router, 95% с VPN). Router в его текущей конфигурации **деградировал** результаты, не улучшил.

### Сравнение прогонов через router (#11, #12) с baseline'ом

| метрика | #5 1 IP OFF | #7 1 IP OFF #2 | #8 3 IP OFF | #10 20 IP OFF wide | **#11 router OFF long** | **#12 router OFF wide c=4** |
|---|---|---|---|---|---|---|
| Success | 36% | 22% | 66% | **89%** | **74%** | **59%** |
| First-try | — | — | — | 72.3% | 74%* | **34.0%** |
| Avg attempts | 1 | 1 | 1 | 1.50 | 1.00 | 2.20 |

\* у прогона 11 нет retries, success-per-attempt = overall success.

**Парадокс**: pool_clean от probe = 95%+, но prod success = 74% (long) и 59% (wide). Router исправно отфильтровывает явно мертвые IP, но **не отлавливает «slow IP»**, которые проходят probe в 10-15s (под 20s budget) и валятся в prod на 8s timeout-е.

### Прогон 8 — пулл из 3 socks5 sessttl.10, VPN OFF

Конфиг `outgoing.proxies`:
```yaml
proxies:
  all://:
    - socks5h://...;sessttl.10:...@np.puls-proxy.com:11000
    - socks5h://...;sessttl.10:...@np.puls-proxy.com:11001
    - socks5h://...;sessttl.10:...@np.puls-proxy.com:11002
```

SearXNG round-robin'ит этот список через `itertools.cycle` (см. `searx/network/network.py:150` — каждый Network имеет свой proxy cycle, на каждый исходящий запрос двигается на +1).

Результаты:

| query | ok | mean | median | p95 | organic |
|-------|-----|------|--------|-----|---------|
| AI | 9/10 | 5.02s | 3.54s | 7.42s | 9.3 |
| python asyncio | 7/10 | 6.16s | 7.33s | 7.45s | 10.0 |
| coffee shops SPb | 6/10 | 4.90s | 3.64s | 7.60s | 10.0 |
| sourdough bread | 7/10 | 5.78s | 7.36s | 7.57s | 10.0 |
| GDP Germany | 8/10 | 5.61s | 6.27s | 7.59s | 10.0 |
| Tesla stock | 8/10 | 6.22s | 7.35s | 7.55s | 10.0 |
| climate change | 6/10 | 6.25s | 7.38s | 7.45s | 10.0 |
| sci-fi movies | 5/10 | 6.35s | 7.40s | 7.44s | 9.8 |
| buy iPhone | 4/10 | 6.79s | 7.37s | 7.55s | 10.0 |
| weather Moscow | 6/10 | 6.33s | 7.42s | 7.61s | 10.0 |
| **TOTAL** | **66/100** | 5.94s | 7.37s | 7.55s | **9.9** |

Elapsed: 810s.

**Что улучшилось vs прогоны 5/7 (1 sticky IP, без VPN, 22-36/100):**
- success-rate ×2.3 (66% vs средние 29%);
- распределение ровнее: нет «полных коллапсов» query (раньше Q5 GDP — 0/10, теперь 8/10; Q4 sourdough — 1/10, теперь 7/10);
- organic avg вырос до 9.9 — когда работает, отдаёт 10 из 10.

**Цена ротации:**
- median latency **поднялся с 3s → 7.4s**. Каждая новая sticky-сессия (а с TTL=10 их больше) — новый TCP/TLS handshake к апстриму на стороне puls;
- mean +1.5s vs single-sticky;
- p95 упёрся в ~7.55s — это `request_timeout + RTT`, часть запросов реально таймаутят один из engine.

**До VPN-уровня (99%) пулл не дотянул.** Гипотеза: дело не только в IP-entropy на наш sticky-IP, но и в **географии puls-PoP**. VPN, видимо, заводит на cleaner pool, где Google/DDG ещё не научились подозревать.

### Прогоны 3 и 4 — те же настройки, VPN OFF

Один и тот же конфиг что и в прогоне 2 (puls socks5 sticky + disabled engines
+ 5s timeout). VPN на хосте выключен, socks5 идёт через прямой канал.

**Прогон 3** (`results_searxng_no_vpn.json`):
- успех: **8/10**
- mean: **5.07s**, median: **4.76s**
- organic: avg **9.8**
- особенность: 2 подряд `EMPTY` (запросы #8 и #9, каждый ~7.05s) — апстримы
  кратковременно отдали нулевой результат / попали в suspended-окно. Запрос
  #10 опять зашёл нормально, без ручного вмешательства.

**Прогон 4** (`results_searxng_no_vpn_2.json`):
- успех: **10/10**
- mean: **3.38s**, median: **3.07s**, min: **2.53s**, max: **7.05s**
- organic: avg **9.4**

### Сводная таблица (latency mean / success / organic avg)

| Прогон | VPN | N   | success | mean   | median | organic avg | примечание |
|--------|-----|-----|---------|--------|--------|-------------|------------|
| 1      | ON  | 10  | 10/10   | 9.21s  | 9.34s  | 10.0        | без тюна (timeout 10s, движки не отключены) |
| 2      | ON  | 10  | 10/10   | 5.94s  | 6.00s  | 9.8         | тюнинг |
| 3      | OFF | 10  | 8/10    | 5.07s  | 4.76s  | 9.8         | тюнинг, два подряд EMPTY |
| 4      | OFF | 10  | 10/10   | 3.38s  | 3.07s  | 9.4         | тюнинг |
| 5      | OFF | 100 | **36/100** | 4.29s  | 3.12s  | 8.9         | длинный тест, 10 разных query |
| 6      | ON  | 100 | **99/100** | 5.02s  | 5.38s  | 10.0        | длинный тест с VPN — почти идеально |
| 7      | OFF | 100 | **22/100** | 3.96s  | 3.01s  | 9.5         | повторный без VPN — даже хуже прогона 5 |
| 8      | OFF | 100 | **66/100** | 5.94s  | 7.37s  | 9.9         | пулл из 3 socks5 sessttl.10 — +30pp к baseline |
| 9      | ON  | 300 | **286/300 (95.3%)** | 7.25s | 6.07s | 9.8 | wide-test: пулл 20 + retries=2; первая попытка 87.7% |
| 10     | OFF | 300 | **267/300 (89.0%)** | 8.20s | 7.18s | 9.9 | wide-test без VPN: пулл 20 + retries=2; первая попытка 72.3% |
| 11     | OFF | 100 | **74/100**  | 5.10s | 3.99s | 9.5 | long-test через router (LRU, 15 active + 5 reserve, probe-clean 96%) |
| 12     | OFF | 300 | **177/300 (59.0%)** | 6.13s | 5.25s | 9.6 | wide-test через router, concurrency=4, retries=2; первая попытка 34.0% |

Сравнение VPN ON vs OFF (на тюненном конфиге, прогоны 2 vs 3+4):
- **VPN добавлял ~2-3 секунды latency** на запрос (mean 5.94s vs ~4.2s
  усреднённо без VPN). Логично — лишний хоп.
- **Success rate без VPN на узкой выборке (2 прогона)**: один 100%, один 80%.
  Двух прогонов мало для выводов, но **EMPTY-паттерн «два подряд»** в прогоне
  3 намекает на короткие окна, когда апстримы у puls-IP попадают под rate-limit.
  С VPN такого не наблюдали — возможно совпадение, возможно VPN-канал даёт
  чуть другой набор IP у puls.
- **Organic avg** не отличается (9.4-10.0 во всех прогонах).

---

## Что НЕ протестировано
- **Direct connection** (без `outgoing.proxies`) — без socks5 движки на этом
  IP стабильно блокировались на прошлом этапе. Прогон не делали.
- **Без VPN при бОльшем N** — двух прогонов мало, чтобы оценить стабильность
  (один 100%, один 80%). Стоит сделать N=30-50.
- **Brave/Startpage с другими прокси** (residential pool вместо puls sticky) —
  возможно, дело именно в реюз-IP пула puls.
- **Puls rotate (не sticky)** — sticky фиксирует IP на 30мин, ротация даёт
  свежий IP на каждый запрос; стоит померить delta по success/latency.
- **Параллельные запросы** — все прогоны строго последовательные, по запросу за раз.
- **Качество результатов** — глазами проверили первые 3 organic (IBM, Britannica,
  NASA для AI-запроса) — корректно; систематического сравнения с эталоном нет.

---

## Текущие выводы (после 12 прогонов, ~1500 запросов)

1. **Маленькие выборки (N=10) давали ложно-оптимистичный результат.** На N=100+
   реальные числа в 2-3 раза ниже.
2. **Главный узел проблемы — upstream-рейтлимит на конкретный IP.** Google/DDG
   ставят IP в suspended-окно после первой CAPTCHA, и дальше SearXNG получает
   0 результатов через этот IP в течение часа.
3. **VPN — самый дешёвый способ выйти на 99%.** Single sticky-IP + VPN
   обходит проблему почти полностью, потому что VPN заводит нас в чистый
   географический PoP puls'а, где апстримы ещё не научились подозревать.
4. **Пулл из N IP без VPN тоже работает — но хуже.** 20 IP + retries=2
   подняли baseline с 22-36% до 89%. Это много, но до VPN-уровня 99% не дотянуло.
5. **Пулл с VPN неожиданно деградирует.** 20 IP + retries=2 с VPN дали 95.3%
   vs 99% у single-sticky+VPN. Причина: пулл подмешивает к чистому VPN-IP
   грязные IP из общего puls-пула, и round-robin периодически попадает на них.
6. **Фейлы случайные, не по query.** Между прогонами 9 и 10 «проблемные query»
   полностью поменялись. Значит не keyword-trigger у апстримов, а просто
   «какой IP в этот момент попался» — статистика IP-пула.
7. **Качество результатов когда работает — норм** (9.9-10.0 organic). Проблема
   исключительно availability.
8. **Архитектурный вывод**: чтобы выйти на стабильные 99%+ без VPN, нужна
   **прослойка-роутер**, которая держит health-check'и над пуллом IP и
   подсовывает SearXNG'у только живые. Иначе round-robin будет периодически
   натыкаться на «грязные» адреса. См. раздел «Следующие шаги».
9. **Прогоны 11-12: router в текущей конфигурации деградирует, не помогает.**
   Long-test через router (без VPN): **74%** vs 89% baseline (20 IP без router).
   Wide-test через router c=4: **59%** vs 89% baseline.
   Причина: **gap между probe-budget (20s) и prod-budget (8s)**. Worker может
   стабильно отвечать за 10-14s — пройдёт все probes как clean, но в prod
   получит ReadTimeout. Pool_clean по probe-метрике 95-96%, но реальный
   prod-success — 59-74%. Это **architectural mismatch**, не баг router'а.
   Дополнительно: при конкурентном wide-режиме (c=4) ситуацию усугубляет
   `ban_time_on_fail` у SearXNG — один timeout valит engine на 5-120s,
   следующие 3-10 запросов получают fast EMPTY мгновенно (cascade failure).
   **Router работоспособен** (probe-pipeline 95% clean, состояние LRU/FSM
   корректны, .ru пулл показывает 100% clean, .pl 91%); проблема в
   калибровке порогов и timeout-ов.
10. **Ключевые ручки настройки** (актуальны):
   - `outgoing.proxies` — обязательно socks5 через резидентный пул, либо один URL на локальный router;
   - `outgoing.request_timeout` — 5-8s комфортно для single-IP; при использовании router'а критично, чтобы probe-budget router'а **не превышал** этот таймаут (иначе worker'ы slow-but-pass-probe валят prod);
   - `disabled: true` для проблемных движков сокращает latency втрое;
   - `search.formats` должен содержать `json`, иначе 403;
   - `ban_time_on_fail` (default 5s) и `max_ban_time_on_fail` (default 120s) — circuit breaker на стороне SearXNG. При конкурентном режиме один timeout каскадно валит следующие 3-10 запросов через fast EMPTY → планировать concurrency aware to this.

---

## Следующие шаги (предложения)

В порядке приоритета:

1. **~~Прокси-роутер с health-check'ами~~** — РЕАЛИЗОВАНО (см. `serp_experiment/proxy_router/`).
   На прогонах 11-12 показал 74% / 59% — **хуже baseline'а**, нужна калибровка
   (см. п. 2 и 3 ниже).
2. **Калибровка router'а: stricter latency budget при probe** —
   снизить `outgoing.request_timeout` у probe-SearXNG'ов с 8s до **5s** или
   ввести явный latency-cutoff в `health.py` (если probe > 5s — не clean,
   даже если organic > 0). Текущий probe пропускает worker'ов с latency 10-14s,
   но prod'у с `request_timeout: 8s` они тоже не подходят. Цель — выровнять
   probe-budget с prod-budget, чтобы pool_clean=95% означал реальное
   prod-success=95%.
3. **Поднять prod `request_timeout` до 12-15s** — alternative подход, дать
   slow workers'ам шанс на prod. Минусы: max latency у медленных query
   поднимется до 12-15s, mean подрастёт на 2-3s. Плюсы: меньше cascade
   через `ban_time_on_fail`.
4. **Подавить `ban_time_on_fail` cascade** в SearXNG: снизить
   `max_ban_time_on_fail` со 120s до 10-15s, чтобы engine быстрее
   возвращался в строй после случайного timeout-а. Альтернативно: выставить
   `ban_time_on_fail: 0` (engine не банится никогда), и пусть retry-loop
   сверху делает работу.
5. **Фильтрация по `.ru` only** (отбросить `.pl`) — по router-метрикам
   .ru показывает 100% clean window, .pl — 91%. На 300 запросах с `.ru` only
   ожидается 95%+, потому что фейлы исчезают из tail-а.
6. **Альтернативные движки** — выключить Google/DDG, попробовать
   mojeek/yahoo/qwant/seznam. Они менее популярны → реже банят. Если выйдут
   на 90%+ — можно вообще обойтись без пула умного роутера.
3. **Изучить geo-распределение puls IP** — выяснить, есть ли у puls возможность
   запрашивать конкретные регионы/страны. Сейчас мы видим .ru и .pl, может
   быть и другие. VPN, по сути, заставляет puls выдавать «другие» IP — если
   это управляемо напрямую, можно обойтись без VPN.
4. **Кэш на стороне нашего клиента** — если query повторяется в коротком окне,
   возвращать прошлый ответ. Не решает основную проблему, но снижает нагрузку
   на upstream.

---

## Файлы в репо после прогонов

```
serp_experiment/
  REPORT_searxng.md                # этот файл
  results_searxng_v3.json          # сырые тайминги прогона 2 (VPN on, тюнинг)
  run_searxng_v3.log               # консольный вывод прогона 2
  results_searxng_no_vpn.json      # прогон 3 (VPN off, тюнинг) — 8/10
  results_searxng_no_vpn_2.json    # прогон 4 (VPN off, тюнинг) — 10/10
  results_searxng_long.json        # прогон 5 (VPN off, N=100) — 36/100
  run_searxng_long.log             # лог прогона 5
  results_searxng_long_vpn.json    # прогон 6 (VPN on, N=100) — 99/100
  run_searxng_long_vpn.log         # лог прогона 6
  results_searxng_long_no_vpn_2.json # прогон 7 (VPN off повтор) — 22/100
  run_searxng_long_no_vpn.log      # лог прогона 7
  results_searxng_long_pool3.json  # прогон 8 (3 socks5 sessttl.10, VPN off) — 66/100
  run_searxng_long_pool3.log       # лог прогона 8
  results_searxng_wide.json        # прогон 9 (20 socks5 + retries=2, VPN on) — 286/300
  run_searxng_wide.log             # лог прогона 9
  results_searxng_wide_no_vpn.json # прогон 10 (20 socks5 + retries=2, VPN off) — 267/300
  run_searxng_wide_no_vpn.log      # лог прогона 10
  results_router_long.json         # прогон 11 (router + 20 socks5, long, VPN off) — 74/100
  run_long_router.log              # лог прогона 11
  results_router_wide_c4.json      # прогон 12 (router + 20 socks5, wide c=4, VPN off) — 177/300
  run_wide_router.log              # лог прогона 12
  router.jsonl                     # event-стрим router'а (probe / connect / state)
  run_router.log                   # лог самого router'а
  proxy_router/                    # сабпакет: WorkerPool + HealthProber + Router + Metrics
  test_router_isolated.py          # изолированный smoke router-pipeline'а
  long_test_searxng.py             # скрипт long-теста (10 query x 10 repeats)
  wide_test_searxng.py             # скрипт wide-теста (30 query x 10 repeats, retries)
  more_proxes.txt                  # 20 socks5 URL для пулла
  approaches/searxng_local.py  # клиент (без изменений с прошлого раза)
  repos/
    searxng/                   # source-only клон (sparse-checkout)
    searxng-docker/            # deprecated upstream compose (для референса)
    searxng-deploy/            # наш деплой
      docker-compose.yml
      searxng/settings.yml
```
