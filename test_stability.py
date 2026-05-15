"""
Stability test: calls /scraper, /serper, /html-to-md each 10 times.
Reports success rate and latency. No changes to service code.
"""
import asyncio
import time
from collections import defaultdict

import httpx

BASE_URL = "http://localhost:8000"
API_KEY = "default_internal_key"
REPEATS = 10
TIMEOUT = 45.0

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

ENDPOINTS = [
    {
        "name": "/scraper",
        "path": "/scraper",
        "payload": {"url": "https://example.com", "output_format": "text"},
    },
    {
        "name": "/serper",
        "path": "/serper",
        "payload": {"q": "python web scraping tutorial", "num": 5},
    },
    {
        "name": "/html-to-md",
        "path": "/html-to-md",
        "payload": {
            "html": "<h1>Hello</h1><p>Test <b>bold</b> content.</p>",
            "format": "markdown",
        },
    },
]


async def call_once(client: httpx.AsyncClient, path: str, payload: dict) -> dict:
    start = time.perf_counter()
    try:
        resp = await client.post(path, json=payload, headers=HEADERS, timeout=TIMEOUT)
        elapsed_ms = (time.perf_counter() - start) * 1000
        ok = resp.status_code == 200
        error_text = None
        if not ok:
            error_text = resp.text[:200]
        else:
            body = resp.json()
            # /scraper: success field
            if "status" in body and body.get("status") == "failed":
                ok = False
                error_text = body.get("error", "status=failed")[:200]
            # /serper: must have at least 1 organic result
            elif "organic" in body and len(body["organic"]) == 0:
                ok = False
                error_text = "organic list is empty (0 results)"
        return {"ok": ok, "ms": elapsed_ms, "status_code": resp.status_code, "error": error_text}
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"ok": False, "ms": elapsed_ms, "status_code": None, "error": str(exc)[:200]}


async def test_endpoint(ep: dict) -> list[dict]:
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        results = []
        for i in range(REPEATS):
            r = await call_once(client, ep["path"], ep["payload"])
            status = "OK" if r["ok"] else "FAIL"
            err = f"  error: {r['error']}" if r["error"] else ""
            print(f"  [{ep['name']}] #{i+1:02d} {status} {r['ms']:.0f}ms{err}")
            results.append(r)
        return results


def print_summary(ep_name: str, results: list[dict]):
    ok_count = sum(1 for r in results if r["ok"])
    times = [r["ms"] for r in results]
    avg = sum(times) / len(times)
    errors = list({r["error"] for r in results if r["error"]})

    print(f"\n{'-'*60}")
    print(f"  {ep_name}")
    print(f"  success : {ok_count}/{REPEATS}")
    print(f"  latency : avg={avg:.0f}ms  min={min(times):.0f}ms  max={max(times):.0f}ms")
    if errors:
        print(f"  errors  :")
        for e in errors[:5]:
            print(f"    * {e}")
    print(f"{'-'*60}")


async def main():
    print(f"\n{'='*60}")
    print(f"  Stability check  -  {REPEATS} calls per endpoint")
    print(f"  {BASE_URL}")
    print(f"{'='*60}\n")

    all_results: dict[str, list] = {}
    for ep in ENDPOINTS:
        print(f"\n>>> {ep['name']}")
        results = await test_endpoint(ep)
        all_results[ep["name"]] = results

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")

    for ep in ENDPOINTS:
        print_summary(ep["name"], all_results[ep["name"]])

    print()


if __name__ == "__main__":
    asyncio.run(main())
