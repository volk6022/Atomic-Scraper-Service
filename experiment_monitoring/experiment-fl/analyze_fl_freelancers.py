"""
analyze_fl_freelancers.py — offline analysis of fl.ru freelancer-catalog data.

No network. Reads samples/<dir>/list_*.jsonl (+ rates_*.jsonl) produced by
fl_freelancers_scrape.py, auto-discovers professions, and computes per-profession
+ global:
  - Competition density (scraped + estimated total, PRO share).
  - Seller maturity: reviews / deals / experience / portfolio buckets (barrier to
    entry — analog of Kwork's review buckets).
  - Specialization landscape (spec_text frequency) + name/positioning keywords.
  - Competency-term gaps (Ivan's stack vs the market).
  - Rate stats from sampled profiles (hourly / monthly ₽).

Run from repo root:
  uv run python experiment_monitoring/experiment-fl/analyze_fl_freelancers.py
  uv run python experiment_monitoring/experiment-fl/analyze_fl_freelancers.py --dir freelancers
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent

# Ivan's stack — probe presence across specialization text + names (gap finder).
COMPETENCY_TERMS = [
    "tensorrt", "triton", "onnx", "квантизац", "инференс", "ускорен",
    "rag", "langchain", "langgraph", "llm", "gpt", "chatgpt", "нейросет",
    "нейронны", "fine-tun", "дообуч", "lora", "qlora", "clip", "dinov2",
    "yolo", "детекц", "распознаван", "ocr", "компьютерн", "cv", "opencv",
    "stt", "tts", "озвуч", "whisper", "playwright", "selenium", "антибот",
    "капч", "прокси", "avito", "авито", "wildberries", "wb", "ozon",
    "маркетплейс", "2gis", "яндекс карт", "парсинг", "парсер", "парсит",
    "n8n", "make", "автоматизац", "бот", "chat", "агент", "agent", "api",
    "backtrader", "ccxt", "binance", "трейд", "бирж", "moex",
]

STOP = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы
за бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну для под
это the a of to and for in on под-ключ ключ под работа услуги заказ""".split())


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def bucketize(vals: list[int], edges: list[int]) -> dict:
    """Count into buckets defined by upper edges; last bucket is > last edge."""
    out: dict[str, int] = {}
    labels = []
    prev = -1
    for e in edges:
        labels.append(f"{prev+1}-{e}" if prev >= 0 else f"0-{e}")
        prev = e
    labels.append(f"{edges[-1]+1}+")
    for lbl in labels:
        out[lbl] = 0
    for v in vals:
        placed = False
        for i, e in enumerate(edges):
            if v <= e:
                out[labels[i]] += 1
                placed = True
                break
        if not placed:
            out[labels[-1]] += 1
    return out


def stats(vals: list[int]) -> dict:
    if not vals:
        return {}
    s = sorted(vals)
    n = len(s)
    def q(p): return s[min(n - 1, int(p * n))]
    return {"n": n, "min": s[0], "p25": q(.25), "median": q(.5),
            "p75": q(.75), "p90": q(.9), "max": s[-1]}


def analyze_profession(prof: str, rows: list[dict], rates: list[dict], meta: dict) -> dict:
    n = len(rows)
    pro = [r for r in rows if r.get("is_pro")]
    reviews = [int(r["reviews"]) for r in rows if r.get("reviews") is not None]
    deals = [int(r["deals"]) for r in rows if r.get("deals") is not None]
    exp = [int(r["experience_years"]) for r in rows if r.get("experience_years") is not None]
    pf = [int(r["portfolio_works"]) for r in rows if r.get("portfolio_works") is not None]

    specs = Counter(r["spec_text"] for r in rows if r.get("spec_text"))
    # positioning keywords from PRO names (only PRO have names)
    name_words = Counter()
    for r in pro:
        for w in re.findall(r"[a-zа-яё0-9]{3,}", (r.get("name") or "").lower()):
            if w not in STOP:
                name_words[w] += 1

    # competency coverage across spec_text (all rows)
    corpus = " ".join((r.get("spec_text") or "") for r in rows).lower()
    comp = {t: corpus.count(t) for t in COMPETENCY_TERMS}
    comp = {t: c for t, c in comp.items() if c}

    hourly = [int(x["hourly_rate"]) for x in rates if x.get("hourly_rate")]
    monthly = [int(x["monthly_rate"]) for x in rates if x.get("monthly_rate")]

    return {
        "profession": prof,
        "scraped": n,
        "est_total": meta.get("est_total_freelancers"),
        "has_more_pages": meta.get("has_more"),
        "pro_count": len(pro),
        "pro_share_pct": pct(len(pro), n),
        "verified_share_pct": pct(sum(1 for r in rows if r.get("is_verified")), n),
        # maturity
        "reviews_buckets": bucketize(reviews, [0, 10, 50, 200]),
        "reviews_stats": stats(reviews),
        "fresh_0_reviews_pct": pct(sum(1 for v in reviews if v == 0), len(reviews)) if reviews else 0,
        "heavy_200plus_reviews_pct": pct(sum(1 for v in reviews if v > 200), len(reviews)) if reviews else 0,
        "deals_stats": stats(deals),
        "experience_stats": stats(exp),
        "portfolio_stats": stats(pf),
        # positioning
        "top_specializations": specs.most_common(12),
        "top_name_words": name_words.most_common(10),
        "competency_terms_present": dict(sorted(comp.items(), key=lambda kv: -kv[1])),
        # rates
        "rates_sampled": len(rates),
        "hourly_rate_stats": stats(hourly),
        "monthly_rate_stats": stats(monthly),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="freelancers", help="samples/ subfolder")
    args = ap.parse_args()
    base = HERE / "samples" / args.dir

    lists = sorted(base.glob("list_*.jsonl"))
    if not lists:
        print(f"no list_*.jsonl in {base}")
        return

    per: list[dict] = []
    summary = []
    if (base / "summary.json").exists():  # summary.json is a JSON array, not jsonl
        summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
    meta_by_prof = {m["profession"]: m for m in summary} if summary else {}

    all_rows: list[dict] = []
    for lp in lists:
        prof = lp.stem[len("list_"):]
        rows = load_jsonl(lp)
        rates = load_jsonl(base / f"rates_{prof}.jsonl")
        all_rows.extend(rows)
        per.append(analyze_profession(prof, rows, rates, meta_by_prof.get(prof, {})))

    glob = analyze_profession("__ALL__", all_rows,
                              [x for p in lists for x in load_jsonl(base / f"rates_{p.stem[len('list_'):]}.jsonl")],
                              {})

    out = {"per_profession": per, "global": glob}
    (base / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # -------- console digest --------
    print("=" * 78)
    print(f"fl.ru FREELANCER-CATALOG ANALYSIS — {args.dir}  ({len(all_rows)} freelancers)")
    print("=" * 78)
    for a in per:
        print(f"\n### {a['profession']}  (scraped {a['scraped']}, est_total≈{a['est_total']}, more={a['has_more_pages']})")
        print(f"  PRO share: {a['pro_share_pct']}%   verified: {a['verified_share_pct']}%")
        rs = a["reviews_stats"]
        print(f"  reviews: median {rs.get('median')}  p90 {rs.get('p90')}  max {rs.get('max')}  "
              f"| fresh(0) {a['fresh_0_reviews_pct']}%  heavy(200+) {a['heavy_200plus_reviews_pct']}%")
        print(f"  reviews buckets: {a['reviews_buckets']}")
        es = a["experience_stats"]; ps = a["portfolio_stats"]; ds = a["deals_stats"]
        print(f"  experience yrs median {es.get('median')} (max {es.get('max')})  "
              f"portfolio median {ps.get('median')}  deals median {ds.get('median')}")
        hr = a["hourly_rate_stats"]; mr = a["monthly_rate_stats"]
        print(f"  rate (sampled {a['rates_sampled']}): hourly median {hr.get('median')}₽ "
              f"(p90 {hr.get('p90')})  monthly median {mr.get('median')}₽")
        print(f"  top specs: {[f'{s}×{c}' for s,c in a['top_specializations'][:8]]}")
        if a["competency_terms_present"]:
            print(f"  competency terms: {a['competency_terms_present']}")
    g = glob
    print("\n" + "=" * 78)
    print(f"GLOBAL: {g['scraped']} freelancers | PRO {g['pro_share_pct']}% | "
          f"fresh(0rev) {g['fresh_0_reviews_pct']}% | heavy(200+) {g['heavy_200plus_reviews_pct']}%")
    print(f"  reviews median {g['reviews_stats'].get('median')}  exp median {g['experience_stats'].get('median')}y")
    print(f"  hourly median {g['hourly_rate_stats'].get('median')}₽  monthly median {g['monthly_rate_stats'].get('median')}₽")
    print(f"  global top specs: {[f'{s}×{c}' for s,c in g['top_specializations'][:15]]}")
    print(f"\nSaved -> {base/'analysis.json'}")


if __name__ == "__main__":
    main()
