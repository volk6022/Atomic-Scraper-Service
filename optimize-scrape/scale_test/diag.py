"""Disambiguate: is it the internet/VPN or the proxy pool that's down?"""
import asyncio, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.infrastructure.browser.proxy_provider import proxy_provider  # noqa
from src.actions.yandex_maps import _build_proxy_url  # noqa

UA = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate"}

async def direct():
    try:
        async with httpx.AsyncClient(headers=UA, timeout=15) as c:
            r = await c.get("https://t.me/s/maximumauto")
            print(f"DIRECT (no proxy): status={r.status_code} bytes={r.num_bytes_downloaded} len={len(r.text)}")
    except Exception as e:
        print(f"DIRECT FAILED: {type(e).__name__}: {e}")

async def one_proxy(n=5):
    print(f"proxies loaded: {len(getattr(proxy_provider, '_proxies', []))}")
    for i in range(n):
        p = proxy_provider.get_proxy()
        url = _build_proxy_url(p) if p else None
        masked = (url[:22] + '...') if url else None
        try:
            async with httpx.AsyncClient(proxy=url, headers=UA, timeout=12) as c:
                r = await c.get("https://api.ipify.org?format=json")
                print(f"  proxy#{i} {masked} -> OK {r.status_code} {r.text[:60]}")
        except Exception as e:
            print(f"  proxy#{i} {masked} -> {type(e).__name__}: {str(e)[:80]}")

async def main():
    await direct()
    await one_proxy()

asyncio.run(main())
