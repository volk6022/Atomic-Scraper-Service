"""avito_q_fetch.py - check q= search structure"""
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

url = "https://www.avito.ru/all/vakansii?q=python+developer&s=104"
r = httpx.get(url, headers=HEADERS, timeout=25, follow_redirects=True)
html = r.text
print(f"HTTP {r.status_code} | {len(html)} chars")
(SAMPLES / "avito_q_python_full.html").write_text(html, encoding="utf-8", errors="replace")

items = re.findall(r'"id":(\d{10,12}),"categoryId"', html)
print(f"items pattern 1: {len(items)}")
catalog_idx = html.find('"catalog"')
print(f"catalog key at: {catalog_idx}")
if catalog_idx >= 0:
    print(html[catalog_idx:catalog_idx+500])
count_m = re.search(r'"count":(\d+),"totalCount"', html)
if count_m:
    print(f"total count: {count_m.group(1)}")
# Check if it loads via JS (lazy)
lazy = "suspense" in html.lower() or "lazy" in html.lower()
print(f"lazy/suspense indicators: {lazy}")
