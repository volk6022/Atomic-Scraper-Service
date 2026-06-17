"""Decisive test: is the mojibake caused by undecoded Brotli?

Fetch zoon/rubrikator/2gis with (a) br advertised and (b) gzip-only, print
Content-Encoding + whether text is clean Cyrillic. Also report brotli lib presence.
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.actions.yandex_maps import _httpx_proxy  # noqa: E402

for lib in ("brotli", "brotlicffi"):
    try:
        __import__(lib); print(f"{lib}: INSTALLED")
    except Exception:
        print(f"{lib}: missing")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
URLS = [
    "https://zoon.ru/spb/education/shkola_no5/",
    "https://rubrikator.org/russia/saint-petersburg/parikmaherskaya-no1",
    "https://2gis.ru/spb/firm/5348552838715575",
]

def clean_ratio(s: str) -> float:
    if not s:
        return 0.0
    cyr = sum(1 for c in s[:4000] if "Ѐ" <= c <= "ӿ" or c.isascii() and c.isprintable())
    return cyr / min(len(s), 4000)

async def fetch(url, enc, tries=10):
    hdr = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
           "Accept-Language": "ru-RU,ru;q=0.9", "Accept-Encoding": enc}
    to = httpx.Timeout(connect=5, read=20, write=20, pool=20)
    for _ in range(tries):
        p = _httpx_proxy()
        try:
            async with httpx.AsyncClient(proxy=p, headers=hdr, timeout=to, follow_redirects=True) as c:
                r = await c.get(url)
                if len(r.text) > 1500:
                    return r.headers.get("content-encoding", "?"), r.text
        except Exception:
            continue
    return None, None

async def main():
    for url in URLS:
        print(f"\n### {url}")
        for enc in ("gzip, deflate, br", "gzip, deflate"):
            ce, txt = await fetch(url, enc)
            if txt is None:
                print(f"  Accept-Encoding={enc:18} -> FAILED")
            else:
                # crude clean check: does first 400 chars contain readable Cyrillic words?
                head = txt[:400].replace("\n", " ")
                ok = clean_ratio(txt) > 0.85
                print(f"  Accept-Encoding={enc:18} -> CE={ce:6} clean={ok} ratio={clean_ratio(txt):.2f}")

asyncio.run(main())
