# serp_experiment

Сравнительный бенчмарк подходов к скрейпингу Google SERP.

## Что сравнивается

Девять комбинаций (3 транспорта × 3 сетевых режима):

| подход                   | без прокси | http-прокси | socks5-прокси |
|--------------------------|:---------:|:-----------:|:-------------:|
| `requests + bs4`         | ✓         | ✓           | ✓             |
| `playwright` (headless)  | ✓         | ✓           | ✓ †           |
| `playwright + stealth`   | ✓         | ✓           | ✓ †           |

† Chromium не умеет авторизоваться в SOCKS5 через Playwright `proxy={...}`.
Чтобы это обойти, для каждого SOCKS5-прогона поднимается локальный
HTTP-CONNECT-форвардер (`proxy_forwarder.py`), который слушает на
`127.0.0.1:<random>` и тащит трафик через SOCKS5 с логином/паролем уже сам.
Playwright видит обычный HTTP-прокси без пароля, провайдер ротации работает
как обычно. Источник прокси для подходов — абстракция `PlaywrightProxySource`:
для HTTP-аплинка отдаёт Playwright нативный dict, для SOCKS5 — поднимает
форвардер и отдаёт его локальный URL.

Прокси берутся из файла `puls.txt` в корне репозитория (одна строка `http://...`,
одна строка `socks5://...`). Ротация IP — на стороне оператора (`puls-proxy.com`):
при каждом новом запросе провайдер выдаёт новый exit-IP.

В режиме «без прокси» используется ваш резидентский IP.

## Что замеряется

* Время выполнения каждого из 10 (по умолчанию) запросов.
* Среднее и медиана по 10 запросам.
* Доля успешных запросов (success rate) — успехом считается непустой
  массив `organic`.
* Количество извлечённых organic-результатов в успешных запусках.

Для первого успешного запроса каждого варианта в консоль выводятся первые
3 organic-результата (`title`, `link`, `snippet`) — чтобы глазами убедиться,
что парсер не сломан и страница не показывает капчу.

## Формат результата

Каждый подход возвращает Serper-совместимый словарь:

```python
{
  "searchParameters": {
    "q": "What is artificial intelligence",
    "type": "search",
    "engine": "google",
    "num": 10,
  },
  "organic": [
    {"title": "...", "link": "...", "snippet": "...", "position": 1},
    ...
  ],
}
```

## Запуск

```bash
# дефолт: 9 вариантов × 10 запросов, запрос "What is artificial intelligence"
uv run python -m serp_experiment.run_benchmark

# другой запрос и 5 повторов на вариант
uv run python -m serp_experiment.run_benchmark --query "machine learning" --repeats 5

# только requests/bs4-варианты
uv run python -m serp_experiment.run_benchmark --only requests_bs4

# пропустить playwright-stealth-socks5
uv run python -m serp_experiment.run_benchmark --skip playwright_stealth__socks5

# сохранить сырые тайминги в JSON
uv run python -m serp_experiment.run_benchmark --save out.json
```

## Зависимости

Доустановлены: `playwright-stealth`, `pysocks` (для SOCKS5 в `requests`), `lxml`
(быстрый парсер для BeautifulSoup).

## Тесты с VPN / Xbox-DNS

Скрипт ничего сам не делает с сетью на уровне ОС — он использует системные
маршруты. Чтобы сравнить варианты:

1. VPN включён, Xbox-DNS включён → запустить.
2. VPN выключен, Xbox-DNS включён → запустить.
3. VPN включён, Xbox-DNS выключен → запустить.
4. VPN выключен, Xbox-DNS выключен → запустить.

Каждый раз сохраняйте результат с уникальным именем, например:
`--save out_vpn-on_xbox-on.json`.

## Парсер

`parser.py` использует трёхуровневую стратегию извлечения:

1. `div.tF2Cxc` — классический контейнер organic-результата.
2. `div.yuRUbf` (обёртка title-ссылки) → подняться к ближайшему предку,
   содержащему сниппет (`.VwiC3b` / `[data-sncf]`).
3. Fallback: каждый `<h3>` → найти ближайшего предка-div, у которого есть
   сниппет внутри.

Отсеиваются:
- ссылки без `http`;
- ссылки на сам Google;
- дубликаты.

Признаки блокировки (капча, страница `/sorry/`) поднимают `BlockedError`
и считаются неуспешным запуском.
