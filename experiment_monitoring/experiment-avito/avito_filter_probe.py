"""
avito_filter_probe.py — test URL filters, pagination, date sorting.

Run from repo root:
  uv run python experiment-avito\\avito_filter_probe.py
"""
from __future__ import annotations
import datetime, httpx, json, re, sys, io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
}

SAMPLES = Path(__file__).parent / "samples"
SAMPLES_DIR = SAMPLES
SAMPLES.mkdir(parents=True, exist_ok=True)

URLS_TO_TEST = [
    # (label, url)
    ("all_vakansii_sort_date",   "https://www.avito.ru/all/vakansii?s=104"),
    ("all_vakansii_page2",       "https://www.avito.ru/all/vakansii?s=104&p=2"),
    ("spb_vakansii_sort_date",   "https://www.avito.ru/sankpeterburg/vakansii?s=104"),
    ("all_vakansii_q_python",    "https://www.avito.ru/all/vakansii?q=python&s=104"),
    # IT subcategory — category slug from Avito
    ("spb_it_vakansii",
     "https://www.avito.ru/sankpeterburg/vakansii/informacionnye_tehnologii_-_internet_-_telecom-ASgBAgICAUSwCQ?s=104"),
]


def fetch_and_extract(label: str, url: str) -> dict:
    print(f"\n  [{label}] {url}")
    try:
        r = httpx.get(url, headers=HEADERS, timeout=25, follow_redirects=True)
        html = r.text
        status = r.status_code
        print(f"    HTTP {status} | {len(html)} chars | final={r.url}")

        items = re.findall(r'"id":(\d{10,12}),"categoryId":\d+', html)
        timestamps = re.findall(r'"sortTimeStamp":(\d{13})', html)
        count_match = re.search(r'"count":(\d+),"totalCount"', html)
        total = int(count_match.group(1)) if count_match else None

        if timestamps:
            ts_first = datetime.datetime.fromtimestamp(int(timestamps[0]) / 1000)
            ts_last = datetime.datetime.fromtimestamp(int(timestamps[-1]) / 1000)
            print(f"    items={len(items)} total={total} ts_range: {ts_first} → {ts_last}")
        else:
            print(f"    items={len(items)} total={total}")

        # Save snippet
        (SAMPLES / f"avito_{label}.html").write_bytes(html[:80000].encode("utf-8", errors="replace"))

        return {
            "label": label,
            "url": url,
            "status": status,
            "items_on_page": len(items),
            "total_count": total,
            "timestamps": timestamps[:3],
            "first_item_ids": items[:5],
        }
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return {"label": label, "url": url, "error": str(exc)}


def main():
    results = []
    for label, url in URLS_TO_TEST:
        r = fetch_and_extract(label, url)
        results.append(r)

    ev_path = SAMPLES / "avito_filter_evidence.json"
    ev_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEvidence saved: {ev_path}")

    print("\n=== SUMMARY ===")
    for r in results:
        if "error" in r:
            print(f"  [{r['label']}] ERROR: {r['error']}")
        else:
            print(f"  [{r['label']}] status={r['status']} items={r['items_on_page']} total={r.get('total_count','?')}")


if __name__ == "__main__":
    main()
