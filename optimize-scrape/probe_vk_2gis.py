"""Probe whether VK (m.vk.com) and 2gis carry the useful fields in raw httpx HTML.

The generic html_to_text extractor strips <head> meta + <script> JSON, so a low
word-count does NOT mean the fetch is useless. Check for og: meta, phones, social
handles, and inline-JSON markers directly in the raw HTML.
"""
from __future__ import annotations
import asyncio, re, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.actions.yandex_maps import _httpx_proxy  # noqa: E402

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}
PHONE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")

TARGETS = [
    ("m.vk.com", "https://m.vk.com/club32063264"),
    ("m.vk.com", "https://m.vk.com/public194067229"),
    ("vk.com-desktop", "https://vk.com/club32063264"),
    ("2gis", "https://2gis.ru/spb/firm/5348552838715575"),
]

def meta(html, prop):
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)', html, re.I)
    if not m:
        m = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}', html, re.I)
    return m.group(1)[:160] if m else None

async def get(url, tries=10):
    to = httpx.Timeout(connect=5, read=20, write=20, pool=20)
    for _ in range(tries):
        p = _httpx_proxy()
        try:
            async with httpx.AsyncClient(proxy=p, headers=HEADERS, timeout=to, follow_redirects=True) as c:
                r = await c.get(url)
                return r.text, r.status_code
        except Exception:
            continue
    return None, None

async def main():
    for name, url in TARGETS:
        html, st = await get(url)
        if not html:
            print(f"\n### {name} {url}\n  FETCH FAILED")
            continue
        low = html.lower()
        print(f"\n### {name}  status={st}  html={len(html)//1024}KB")
        print(f"  og:title       = {meta(html,'og:title')}")
        print(f"  og:description = {meta(html,'og:description')}")
        print(f"  phones in html = {PHONE.findall(html)[:5]}")
        print(f"  has vk.link/tg = vk:{'vk.com/' in low}  tg:{'t.me/' in low}  inst:{'instagram.com/' in low}")
        markers = [m for m in ('window.__initialstate','data-jsx','og:','application/ld+json',
                               'mvk_','"phone"','"contact"','описание','подписчик') if m in low]
        print(f"  markers        = {markers}")
        # show a slice of visible-ish text near 'описание' or first og:description
        d = meta(html, 'og:description')
        if d:
            print(f"  DESC SAMPLE    = {d}")

asyncio.run(main())
