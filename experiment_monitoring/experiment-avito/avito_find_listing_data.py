"""Find where the listing item data is embedded in Avito HTML."""
import httpx, json, re, io, sys
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

r = httpx.get("https://www.avito.ru/all/vakansii?s=104", headers=HEADERS, timeout=25, follow_redirects=True)
html = r.text

# Find where item ID 8195307158 appears (first item we know is there)
# Check all script blocks that contain item IDs
scripts = re.findall(r'<script([^>]*)>(.*?)</script>', html, re.DOTALL)
print(f"Total script blocks: {len(scripts)}")

for i, (attrs, content) in enumerate(scripts):
    if re.search(r'"id":\d{10,12},"categoryId"', content):
        print(f"\nScript {i} (attrs={attrs[:60]!r}) contains item data!")
        print(f"  Length: {len(content)} chars")
        # How does it start?
        print(f"  Start: {content[:200]!r}")
        # Find the enclosing variable
        idx = content.find('"count"')
        if idx >= 0:
            print(f"  Context around 'count': {content[max(0,idx-200):idx+500]!r}")
        break

# Also look for the catalog data in non-script elements
# Try to find the exact JSON blob containing items
idx1 = html.find('"itemsOnPage":50')
if idx1 >= 0:
    print(f"\n'itemsOnPage':50 found at index {idx1}")
    # Find enclosing structure
    start = max(0, idx1 - 200)
    print(f"  Context (400 chars): {html[start:start+400]!r}")
    # What script block is it in?
    last_script = html.rfind('<script', 0, idx1)
    print(f"  Last <script before it: index {last_script}")
    if last_script >= 0:
        script_ctx = html[last_script:last_script+200]
        print(f"  Script tag: {script_ctx!r}")
