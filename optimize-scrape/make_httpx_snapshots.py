"""Dump the httpx-SSR extracted text per verification URL, so the browser-MCP
verifier can diff browser-visible fields against what httpx-SSR actually captured.

Mirrors the production extract: html_to_text + the same ~3500-char budget the agent
sees (goal_conditioned_extract is query-specific; here we keep full html_to_text and
also a 3500-char head, which is what matters for 'did we lose data').
"""
from __future__ import annotations
import asyncio, json, re, sys
from pathlib import Path
from urllib.parse import urlparse
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.domain.utils.content_cleaner import html_to_text, count_words  # noqa: E402
from src.actions.yandex_maps import _httpx_proxy  # noqa: E402

OUT = ROOT / "optimize-scrape" / "httpx_snapshots"
OUT.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    # NB: NO brotli — the venv lacks the `brotli` lib, so advertising `br` makes
    # ~half the target domains (zoon/rubrikator/spravker/2gis) return undecoded
    # garbage that fools word-count. gzip/deflate only → clean SSR. See probe_brotli.py.
    "Accept-Encoding": "gzip, deflate",
}
PHONE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
SOCIAL = re.compile(r"(?:vk\.com|t\.me|instagram\.com)/[A-Za-z0-9_./]+")

# Verification set: confirmed-win domains + the uncertain VK/2gis (real run URLs).
URLS = [
    "https://t.me/maximumauto",
    "https://zoon.ru/spb/restaurants/restoran_po_bokalam_na_klinskom_prospekte/",
    "https://zoon.ru/spb/education/shkola_no5/",
    "https://spb.hh.ru/employer/224317",
    "https://prodoctorov.ru/spb/lpu/61561-stomatologiya-doktora-budovskogo/",
    "https://www.rusprofile.ru/id/2556112",
    "https://rubrikator.org/russia/saint-petersburg/parikmaherskaya-no1",
    "https://orgzz.ru/spb/co/produktovyy_magazin/5523403",
    "https://spb.spravker.ru/medtsentryi-i-kliniki/say-me.htm",
    "https://vk.com/club32063264",
    "https://2gis.ru/spb/firm/5348552838715575",
]

def rewrite(url):
    p = urlparse(url); host = p.netloc.lower()
    if host in ("t.me", "www.t.me") and not p.path.startswith("/s/"):
        return f"https://t.me/s{p.path}"
    if host in ("vk.com", "www.vk.com"):
        return f"https://m.vk.com{p.path}"
    return url

def slug(url):
    return re.sub(r"[^A-Za-z0-9]+", "_", url)[:80]

async def get(url, tries=12):
    to = httpx.Timeout(connect=5, read=20, write=20, pool=20)
    for _ in range(tries):
        p = _httpx_proxy()
        try:
            async with httpx.AsyncClient(proxy=p, headers=HEADERS, timeout=to, follow_redirects=True) as c:
                r = await c.get(url)
                if len(r.text) > 1500:
                    return r.text
        except Exception:
            continue
    return None

async def main():
    index = []
    for url in URLS:
        rurl = rewrite(url)
        html = await get(rurl)
        rec = {"orig_url": url, "fetched_url": rurl}
        if not html:
            rec["status"] = "FETCH_FAILED"
            print(f"FAILED  {url}")
        else:
            text = html_to_text(html)
            rec.update({
                "status": "ok",
                "words": count_words(text),
                "phones": sorted(set(PHONE.findall(html)))[:8],
                "socials": sorted(set(SOCIAL.findall(html)))[:12],
                "text_3500": text[:3500],
            })
            (OUT / f"{slug(url)}.txt").write_text(text[:8000], encoding="utf-8")
            print(f"OK  {url}  words={rec['words']} phones={len(rec['phones'])} socials={len(rec['socials'])}")
        index.append(rec)
    (OUT / "_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT/'_index.json'}")

asyncio.run(main())
