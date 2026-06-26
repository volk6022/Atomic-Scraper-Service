"""avito_url_probe2.py - test city slugs and search params."""
import httpx, re, io, sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}
SAMPLES = Path(__file__).parent / "samples"
SAMPLES.mkdir(parents=True, exist_ok=True)


def probe(label: str, url: str) -> None:
    try:
        r = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    except Exception as e:
        print(f"[{label}] ERROR {e}")
        return
    html = r.text
    items = re.findall(r'"id":(\d{10,12}),"categoryId"', html)
    count_m = re.search(r'"count":(\d+),"totalCount"', html)
    total = count_m.group(1) if count_m else "none"
    print(f"[{label}] HTTP {r.status_code} items={len(items)} total={total}")
    if items:
        print(f"  first_ids: {items[:3]}")
    # Search results may use different pattern
    item_ids = re.findall(r'"itemId":(\d{10,12})', html)
    titles = re.findall(r'"title":"((?:[^"\\]|\\.){3,60})"', html)
    if item_ids:
        print(f"  itemId pattern: {item_ids[:3]}")
    if titles:
        print(f"  first titles: {titles[:3]}")
    (SAMPLES / f"avito_{label}.html").write_bytes(html[:100000].encode("utf-8", errors="replace"))


probe("spb_correct", "https://www.avito.ru/sankt-peterburg/vakansii?s=104")
probe("msk_vakansii", "https://www.avito.ru/moskva/vakansii?s=104")
probe("all_q_python_dev", "https://www.avito.ru/all/vakansii?q=python+developer&s=104")
probe("all_q_ml", "https://www.avito.ru/all/vakansii?q=machine+learning&s=104")
