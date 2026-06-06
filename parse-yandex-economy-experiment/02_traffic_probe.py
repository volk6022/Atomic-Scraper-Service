"""Эксперимент 2 (ЖИВОЙ, через прокси): замер трафика на 1 запрос и где он тратится.

Запускает реальный браузер (как прод: stealth-args + прокси из proxies.txt),
грузит страницу поиска Я.Карт, считает байты ответа по типам ресурсов и хостам
через request.sizes(), извлекает организации (SSR + XHR) и проверяет капчу.

Политики блокировки (argv[1]):
  baseline   — ничего не блокируем (полный прод-сценарий)
  noassets   — режем image/media/font
  noassets_css — + stylesheet
  minimal    — + блок хостов тайлов/аватаров/аналитики, оставляем doc/script/api
  minimal_nopag — minimal, но БЕЗ скролла (только SSR-страница)

Бюджет: каждый baseline ~2.5 МБ. Скрипт печатает байты — следим за расходом.

Использование:
  python parse-yandex-economy-experiment/02_traffic_probe.py baseline
  python parse-yandex-economy-experiment/02_traffic_probe.py minimal_nopag
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from src.infrastructure.browser.proxy_provider import proxy_provider
from src.infrastructure.browser.user_agent_pool import UserAgentPool

OUT = Path(__file__).parent / "results"

CLAT, CLON = 59.914403, 30.327319
ZOOM = 17
QUERY = "кафе"           # плотная категория — худший случай
TARGET = 30

# хосты/подстроки тяжёлого «не-данными» трафика
HEAVY_HOSTS = (
    "core-renderer-tiles", ".maps.yandex.net/tiles", "avatars.mds.yandex.net",
    "mc.yandex.ru", "an.yandex.ru", "/clck/", "yastatic.net",
    "strm.yandex", "/get-coverage", "api-maps.yandex",
)
SEARCH_MARKERS = ("/maps/api/search", "search-maps.yandex.ru/v1", "fullobjects")

STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage",
    "--no-sandbox", "--disable-setuid-sandbox",
]


def policy_should_abort(policy: str, rtype: str, url: str) -> bool:
    if policy == "baseline":
        return False
    if policy == "doc_only":
        # оставляем только сам документ (inline-SSR-скрипт уже внутри HTML);
        # блокируем ВСЁ внешнее — js-бандл, css, картинки, тайлы, xhr.
        return rtype != "document"
    if rtype in ("image", "media", "font"):
        return True
    if policy in ("noassets_css", "minimal", "minimal_nopag") and rtype == "stylesheet":
        return True
    if policy in ("minimal", "minimal_nopag"):
        if any(h in url for h in HEAVY_HOSTS):
            # но не трогаем сам search API
            if not any(m in url for m in SEARCH_MARKERS):
                return True
    return False


async def run(policy: str) -> dict:
    do_scroll = policy not in ("minimal_nopag", "doc_only")
    proxy = proxy_provider.get_proxy()
    ua = UserAgentPool().get_user_agent()

    by_type = Counter()
    by_host = Counter()
    total = {"down": 0, "up": 0}
    n_req = {"made": 0, "aborted": 0}
    size_tasks = []
    captured = []
    captcha = False

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS,
                                            proxy=proxy)
        ctx = await browser.new_context(
            user_agent=ua, locale="ru-RU", timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = await ctx.new_page()

        async def route_handler(route):
            req = route.request
            if policy_should_abort(policy, req.resource_type, req.url):
                n_req["aborted"] += 1
                try:
                    await route.abort()
                except Exception:
                    pass
            else:
                try:
                    await route.continue_()
                except Exception:
                    pass

        await page.route("**/*", route_handler)

        async def record(req):
            try:
                s = await req.sizes()
            except Exception:
                return
            down = (s.get("responseBodySize") or 0) + (s.get("responseHeadersSize") or 0)
            up = (s.get("requestBodySize") or 0) + (s.get("requestHeadersSize") or 0)
            total["down"] += down; total["up"] += up
            by_type[req.resource_type] += down
            by_host[urlparse(req.url).hostname or "?"] += down

        def on_finished(req):
            n_req["made"] += 1
            size_tasks.append(asyncio.create_task(record(req)))

        def on_response(resp):
            if any(m in resp.url for m in SEARCH_MARKERS):
                async def grab():
                    try:
                        captured.append(await resp.text())
                    except Exception:
                        pass
                size_tasks.append(asyncio.create_task(grab()))

        page.on("requestfinished", on_finished)
        page.on("response", on_response)

        url = (f"https://yandex.ru/maps/2/saint-petersburg/search/"
               f"{quote(QUERY, safe='')}/?ll={CLON},{CLAT}&z={ZOOM}")
        ssr_items = []
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            html = await page.content()
            if "smartcaptcha" in html.lower() or "showcaptcha" in html.lower():
                captcha = True
            else:
                try:
                    await page.wait_for_selector(
                        ".search-list-view, .search-snippet-view", timeout=15_000)
                except Exception:
                    pass
                ssr_items = await extract_ssr(page)
                if do_scroll:
                    await scroll(page, TARGET)
        except Exception as e:
            print("  goto/err:", str(e)[:120])
        finally:
            if size_tasks:
                await asyncio.gather(*size_tasks, return_exceptions=True)
            await ctx.close()
            await browser.close()

    # подсчёт уникальных орг из SSR + XHR
    oids = set()
    n_ssr = 0
    for it in ssr_items:
        oid = str(it.get("id") or it.get("oid") or "")
        if oid:
            oids.add(oid); n_ssr += 1
    for body in captured:
        if len(body) < 80:
            continue
        try:
            d = json.loads(body)
        except Exception:
            continue
        items = (d.get("data", {}) or {}).get("items") if isinstance(d.get("data"), dict) else None
        items = items or d.get("items") or []
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict):
                oid = str(it.get("id") or it.get("oid") or "")
                if oid:
                    oids.add(oid)

    return {
        "policy": policy, "scroll": do_scroll, "captcha": captcha,
        "down_kb": round(total["down"] / 1024, 1),
        "up_kb": round(total["up"] / 1024, 1),
        "total_kb": round((total["down"] + total["up"]) / 1024, 1),
        "req_made": n_req["made"], "req_aborted": n_req["aborted"],
        "orgs_unique": len(oids), "orgs_ssr": n_ssr,
        "by_type_kb": {k: round(v / 1024, 1) for k, v in by_type.most_common()},
        "top_hosts_kb": {k: round(v / 1024, 1) for k, v in by_host.most_common(8)},
    }


async def extract_ssr(page):
    try:
        for s in await page.query_selector_all("script"):
            t = await s.inner_text()
            if len(t) < 100_000:
                continue
            try:
                d = json.loads(t)
            except Exception:
                continue
            stack = d.get("stack")
            if isinstance(stack, list) and stack and isinstance(stack[0], dict):
                res = stack[0].get("results")
                if isinstance(res, dict) and isinstance(res.get("items"), list):
                    return res["items"]
    except Exception:
        pass
    return []


async def scroll(page, target):
    cjs = ("() => document.querySelectorAll("
           "'li.search-snippet-view, div.search-snippet-view').length")
    sjs = ("() => {const l=document.querySelector('.scroll__container, "
           ".search-list-view__list, .search-list-view');if(l)l.scrollBy(0,2000);"
           "window.scrollBy(0,1500);}")
    seen = stale = 0
    for _ in range(25):
        try:
            c = await page.evaluate(cjs)
        except Exception:
            c = seen
        if c >= target:
            break
        if c == seen:
            stale += 1
            if stale >= 3:
                break
        else:
            stale = 0
        seen = c
        try:
            await page.evaluate(sjs)
        except Exception:
            pass
        await page.wait_for_timeout(900)


if __name__ == "__main__":
    pol = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    r = asyncio.run(run(pol))
    OUT.mkdir(parents=True, exist_ok=True)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    # дописываем в общий лог
    log = OUT / "02_traffic_log.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
