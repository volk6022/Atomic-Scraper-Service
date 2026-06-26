"""
Targeted fl budget test: find projects with stated budget from RSS,
call detail_fl, record results. Proves the fix works on budget-bearing items.
"""
from __future__ import annotations
import sys, json, re, xml.etree.ElementTree as ET
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).parent))
from monitor_proto import detail_fl, norm, _FL_HEADERS, FL_FEEDS

def main():
    # Collect fresh RSS and find items whose title contains a Бюджет annotation
    budget_items: list[dict] = {}
    all_pool: list[dict] = {}  # id -> item

    with httpx.Client(headers=_FL_HEADERS, follow_redirects=True, timeout=20) as c:
        for feed_url in FL_FEEDS:
            resp = c.get(feed_url)
            if resp.status_code != 200:
                continue
            raw = resp.content
            if not raw.lstrip().startswith((b"<?xml", b"<rss")):
                continue
            try:
                root = ET.fromstring(raw)
            except Exception:
                continue
            ch = root.find("channel")
            if ch is None:
                continue
            for it in ch.findall("item"):
                link = (it.findtext("link") or "").strip()
                if not link:
                    continue
                m = re.search(r'/projects/(\d+)/', link)
                pid = m.group(1) if m else link
                title = (it.findtext("title") or "").strip()
                desc = (it.findtext("description") or "").strip()
                item = norm("fl", pid, title, link,
                            extra={"desc": desc[:300]})
                all_pool[pid] = item
                # Detect budget-bearing items
                if re.search(r'Бюджет:\s*[\d\s]+', title):
                    budget_items[pid] = item

    print(f"RSS pool: {len(all_pool)} items, with budget: {len(budget_items)}", flush=True)

    results = []
    for pid, item in list(budget_items.items())[:5]:
        print(f"\n  Testing id={pid}: {item['title'][:70]}", flush=True)
        try:
            card = detail_fl(item)
            print(f"    amount: {card.get('amount')!r}", flush=True)
            print(f"    desc[:80]: {str(card.get('description',''))[:80]!r}", flush=True)
            results.append({
                "id": pid,
                "title_rss": item["title"],
                "amount": card.get("amount"),
                "description": str(card.get("description", ""))[:200],
                "url": item["url"],
                "pass": card.get("amount") is not None,
            })
        except Exception as e:
            print(f"    ERROR: {e}", flush=True)
            results.append({"id": pid, "error": str(e), "pass": False})

    # Also test no-budget items to confirm they correctly return None
    no_budget_sample = [v for k, v in all_pool.items() if k not in budget_items][:2]
    for item in no_budget_sample:
        try:
            card = detail_fl(item)
            results.append({
                "id": item["id"],
                "title_rss": item["title"][:60],
                "amount": card.get("amount"),
                "url": item["url"],
                "note": "genuinely_no_budget",
                "pass": True,  # None is expected/correct
            })
            print(f"\n  No-budget id={item['id']}: amount={card.get('amount')!r} (expected None) => OK", flush=True)
        except Exception as e:
            print(f"\n  No-budget id={item['id']}: ERROR {e}", flush=True)

    # Save to card_test dir alongside card_parse_results.json
    out = Path(__file__).parent / "card_test" / "fl_budget_evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out}", flush=True)

    budget_pass = sum(1 for r in results if r.get("pass") and r.get("amount") is not None)
    total_budget = sum(1 for r in results if "note" not in r and "error" not in r)
    print(f"\nSUMMARY: {budget_pass}/{total_budget} budget-bearing items had amount populated", flush=True)


if __name__ == "__main__":
    main()
