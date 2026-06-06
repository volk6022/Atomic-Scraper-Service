"""Эксперимент 8 (ЖИВОЙ): глубокая пагинация отзывов через браузер — но БЕЗ replay.

Прошлый подход (observe URL → page.request.get replay) был нестабилен: s/reqId
одноразовые/протухают. Стабильнее — просто ПЕРЕХВАТЫВАТЬ ответы fetchReviews при
скролле (браузер сам считает подпись s). Так же делает рабочий парсер поиска.

+ блокировка тайлов/картинок/css (но НЕ скриптов — JS нужен для XHR), чтобы дёшево.
Замеряем: собрано уникальных отзывов, трафик, капча.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from src.infrastructure.browser.proxy_provider import proxy_provider
from src.infrastructure.browser.user_agent_pool import UserAgentPool

OUT = Path(__file__).parent / "results"
SEONAME, OID = "schastye", "1153763644"
TARGET_REVIEWS = 200
HEAVY = ("core-renderer-tiles", ".maps.yandex.net/tiles", "avatars.mds.yandex.net",
         "mc.yandex.ru", "an.yandex.ru", "/clck/", "strm.yandex", "/get-coverage")
STEALTH_ARGS = ["--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage", "--no-sandbox", "--disable-setuid-sandbox"]


def should_abort(rtype, url):
    if "fetchReviews" in url:
        return False
    if rtype in ("image", "media", "font", "stylesheet"):
        return True
    if any(h in url for h in HEAVY):
        return True
    return False


async def extract_ssr_reviews(page):
    for s in await page.query_selector_all("script"):
        t = await s.inner_text()
        if len(t) < 50_000:
            continue
        try:
            d = json.loads(t)
        except Exception:
            continue
        try:
            rr = d["stack"][0]["results"]["items"][0]["reviewResults"]
            if isinstance(rr.get("reviews"), list):
                return rr["reviews"]
        except Exception:
            continue
    return []


def parse_ajax_reviews(data):
    def rec(o, d=0):
        if d > 12:
            return None
        if isinstance(o, dict):
            if isinstance(o.get("reviews"), list):
                return o["reviews"]
            for v in o.values():
                r = rec(v, d + 1)
                if r:
                    return r
        elif isinstance(o, list):
            for x in o[:40]:
                r = rec(x, d + 1)
                if r:
                    return r
        return None
    return rec(data) or []


async def main():
    proxy = proxy_provider.get_proxy()
    ua = UserAgentPool().get_user_agent()
    url = f"https://yandex.ru/maps/org/{SEONAME}/{OID}/reviews/"

    captured_pages = []
    total = {"down": 0}
    tasks = []
    captcha = False

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=STEALTH_ARGS, proxy=proxy)
        ctx = await browser.new_context(user_agent=ua, locale="ru-RU",
                                        timezone_id="Europe/Moscow",
                                        viewport={"width": 1440, "height": 900})
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = await ctx.new_page()

        async def route_h(route):
            req = route.request
            try:
                if should_abort(req.resource_type, req.url):
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                pass
        await page.route("**/*", route_h)

        async def rec_size(req):
            try:
                s = await req.sizes()
                total["down"] += (s.get("responseBodySize") or 0) + (s.get("responseHeadersSize") or 0)
            except Exception:
                pass

        def on_finished(req):
            tasks.append(asyncio.create_task(rec_size(req)))

        def on_resp(resp):
            if "fetchReviews" in resp.url and resp.status == 200:
                async def grab():
                    try:
                        captured_pages.append(await resp.json())
                    except Exception:
                        pass
                tasks.append(asyncio.create_task(grab()))
        page.on("requestfinished", on_finished)
        page.on("response", on_resp)

        ssr_reviews = []
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            low = (await page.content()).lower()
            if "smartcaptcha" in low or "showcaptcha" in low:
                captcha = True
            else:
                try:
                    await page.wait_for_selector(
                        ".business-reviews-card-view, .business-review-view", timeout=15_000)
                except Exception:
                    pass
                ssr_reviews = await extract_ssr_reviews(page)
                # скроллим панель отзывов, перехватывая fetchReviews
                ids = {r.get("reviewId") for r in ssr_reviews}
                sjs = ("() => {const c=document.querySelector('.scroll__container, "
                       ".business-reviews-card-view, div[class*=reviews]');"
                       "if(c)c.scrollBy(0,5000);window.scrollBy(0,4000);}")
                stale = 0
                for _ in range(40):
                    have = len(ids) + sum(len(parse_ajax_reviews(p)) for p in captured_pages)
                    if have >= TARGET_REVIEWS:
                        break
                    before = len(captured_pages)
                    try:
                        await page.evaluate(sjs)
                    except Exception:
                        pass
                    await page.wait_for_timeout(1100)
                    if len(captured_pages) == before:
                        stale += 1
                        if stale >= 4:
                            break
                    else:
                        stale = 0
        except Exception as e:
            print("err:", str(e)[:140])
        finally:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await ctx.close()
            await browser.close()

    ids = set()
    for r in ssr_reviews:
        ids.add(r.get("reviewId"))
    for pg in captured_pages:
        for r in parse_ajax_reviews(pg):
            ids.add(r.get("reviewId"))

    res = {"org": f"{SEONAME}/{OID}", "captcha": captcha,
           "ssr_reviews": len(ssr_reviews), "ajax_pages_captured": len(captured_pages),
           "unique_reviews": len(ids), "down_kb": round(total["down"] / 1024, 1),
           "kb_per_review": round(total["down"] / 1024 / max(1, len(ids)), 2)}
    print(json.dumps(res, ensure_ascii=False, indent=2))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "08_reviews_browser.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
