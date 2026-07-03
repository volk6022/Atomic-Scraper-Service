"""
analyze_kwork_services.py — offline analysis of the scraped Kwork supply catalog.

Reads samples/services/list_*.jsonl (+ cards_*.jsonl) and produces analysis.json
with, per subcategory and globally:
  - price distribution (base "от N" price; loss-leader share at the 500 floor)
  - competition structure (seller-level & seller-review buckets; top players)
  - title keyword landscape (unigrams + bigrams)
  - competency-term coverage across titles + card descriptions (gap hunting)
  - extras (доп-опции) aggregated from cards — the real revenue structure

No network. Run:
  uv run python experiment_monitoring/experiment-kwork/analyze_kwork_services.py
"""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent

# SRC and LEAVES are resolved in main() from --dir; leaves auto-discovered from
# the list_*.jsonl files present, so the same analyzer serves any scrape folder.
SRC = HERE / "samples" / "services"
LEAVES: list[str] = []

RU_STOP = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только
ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если или под для
про или под до нею без ваш ваши вашу под-ключ ключ вашего ваших свой своих любой любые
""".split())
GENERIC = set("""
разработка разработаю создам создание сделаю напишу написание под ключ setup настройка
услуга услуги заказ заказать любой любая любые быстро качественно профессионально решение
бот бота боты ботов telegram телеграм python питон
""".split())

# competency terms to probe for gaps (regex-ready, lowercase substring match)
COMPETENCY_TERMS = [
    "tensorrt", "triton", "onnx", "квантизаци", "quantization", "fp16", "int8",
    "rag", "langchain", "langgraph", "vllm", "llama", "qwen", "fine-tun", "дообуч",
    "lora", "qlora", "эмбеддинг", "embedding", "faiss", "qdrant", "clip", "dinov2",
    "yolo", "детекц", "сегментац", "трекинг", "ocr", "распознаван",
    "whisper", "stt", "tts", "озвуч",
    "playwright", "selenium", "антибот", "cloudflare", "капч", "прокси",
    "avito", "авито", "wildberries", "ozon", "маркетплейс", "2gis", "яндекс карт",
    "n8n", "make.com", "make ", "автоматизац", "интеграц", "api", "парсинг", "парсер",
    "backtrader", "vectorbt", "ccxt", "binance", "трейд", "бирж", "moex", "бэктест",
    "mini app", "mini-app", "webapp", "web app", "веб-прилож",
]


def load_list(leaf: str) -> list[dict]:
    fp = SRC / f"list_{leaf}.jsonl"
    if not fp.exists():
        return []
    return [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_cards(leaf: str) -> list[dict]:
    fp = SRC / f"cards_{leaf}.jsonl"
    if not fp.exists():
        return []
    return [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]


def pct(vals: list[int], p: float) -> int | None:
    if not vals:
        return None
    s = sorted(vals)
    k = int(round((len(s) - 1) * p))
    return s[k]


def price_stats(gigs: list[dict]) -> dict:
    prices = [int(g["price"]) for g in gigs if g.get("price")]
    above = [p for p in prices if p > 500]
    return {
        "n": len(prices),
        "min": min(prices) if prices else None,
        "p25": pct(prices, 0.25), "median": pct(prices, 0.5),
        "p75": pct(prices, 0.75), "p90": pct(prices, 0.90),
        "max": max(prices) if prices else None,
        "share_at_500_floor": round(sum(1 for p in prices if p <= 500) / len(prices), 3) if prices else None,
        "median_excl_floor": pct(above, 0.5),
        "mean": round(st.mean(prices)) if prices else None,
    }


def seller_structure(gigs: list[dict]) -> dict:
    def revi(g):
        try:
            return int(g.get("userRatingCount") or 0)
        except (TypeError, ValueError):
            return 0
    buckets = Counter()
    for g in gigs:
        r = revi(g)
        b = ("0" if r == 0 else "1-10" if r <= 10 else "11-50" if r <= 50
             else "51-200" if r <= 200 else "200+")
        buckets[b] += 1
    lvl = Counter(str(g.get("sellerLevel")) for g in gigs)
    top = sorted(gigs, key=revi, reverse=True)[:6]
    top_players = [
        {"seller": g.get("userName"), "reviews": revi(g), "level": g.get("sellerLevel"),
         "price": g.get("price"), "title": (g.get("gtitle") or "")[:60]}
        for g in top
    ]
    n = len(gigs) or 1
    heavy = sum(1 for g in gigs if revi(g) >= 200)
    mass = sum(1 for g in gigs if 1 <= revi(g) <= 50)
    fresh = sum(1 for g in gigs if revi(g) == 0)
    return {
        "review_buckets": dict(buckets),
        "level_counts": dict(lvl),
        "heavy_players_200plus": heavy,
        "heavy_share": round(heavy / n, 3),
        "mass_1_50": mass,
        "fresh_0_reviews": fresh,
        "fresh_share": round(fresh / n, 3),
        "top_players": top_players,
    }


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("ё", "е")
    toks = re.findall(r"[a-zа-я0-9][a-zа-я0-9\-\.\+]{1,}", text)
    return [t for t in toks if t not in RU_STOP and len(t) > 2]


def keyword_landscape(gigs: list[dict], top_n: int = 25) -> dict:
    uni = Counter()
    bi = Counter()
    for g in gigs:
        toks = tokenize(g.get("gtitle") or "")
        content = [t for t in toks if t not in GENERIC]
        uni.update(content)
        for a, b in zip(toks, toks[1:]):
            bi[f"{a} {b}"] += 1
    return {
        "top_unigrams": uni.most_common(top_n),
        "top_bigrams": bi.most_common(top_n),
    }


def competency_coverage(all_gigs: list[dict], all_cards: list[dict]) -> dict:
    title_blob = " ".join((g.get("gtitle") or "") for g in all_gigs).lower().replace("ё", "е")
    desc_blob = " ".join(
        ((c.get("gdesc_text") or "") + " " + (c.get("gtitle") or "")) for c in all_cards
    ).lower().replace("ё", "е")
    out = {}
    n_titles = len(all_gigs)
    for term in COMPETENCY_TERMS:
        t = term.lower()
        out[term] = {
            "in_titles": title_blob.count(t),
            "in_card_desc": desc_blob.count(t),
        }
    return {"n_titles_scanned": n_titles, "n_cards_scanned": len(all_cards), "terms": out}


def extras_analysis(all_cards: list[dict]) -> dict:
    prices = []
    titles = Counter()
    n_with = 0
    for c in all_cards:
        ex = c.get("extras") or []
        if ex:
            n_with += 1
        for e in ex:
            if e.get("price"):
                prices.append(int(e["price"]))
            if e.get("title"):
                titles.update(tokenize(e["title"]))
    return {
        "cards_with_extras": n_with,
        "cards_total": len(all_cards),
        "extra_count": len(prices),
        "extra_price_min": min(prices) if prices else None,
        "extra_price_median": pct(prices, 0.5),
        "extra_price_p90": pct(prices, 0.9),
        "extra_price_max": max(prices) if prices else None,
        "top_extra_terms": titles.most_common(20),
    }


def main() -> None:
    global SRC, LEAVES
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="services",
                    help="scrape folder under samples/ (e.g. services, services-dev)")
    args = ap.parse_args()
    SRC = HERE / "samples" / args.dir
    LEAVES = sorted(p.stem[len("list_"):] for p in SRC.glob("list_*.jsonl"))
    print(f"analyzing {SRC} — {len(LEAVES)} categories: {', '.join(LEAVES)}\n")

    per_cat = {}
    all_gigs: list[dict] = []
    all_cards: list[dict] = []
    for leaf in LEAVES:
        gigs = load_list(leaf)
        cards = load_cards(leaf)
        all_gigs += gigs
        all_cards += cards
        per_cat[leaf] = {
            "gig_count": len(gigs),
            "prices": price_stats(gigs),
            "sellers": seller_structure(gigs),
            "keywords": keyword_landscape(gigs),
            "extras": extras_analysis(cards),
        }

    result = {
        "per_category": per_cat,
        "global": {
            "total_gigs": len(all_gigs),
            "total_cards": len(all_cards),
            "prices": price_stats(all_gigs),
            "sellers": seller_structure(all_gigs),
            "keywords": keyword_landscape(all_gigs, top_n=40),
            "competency": competency_coverage(all_gigs, all_cards),
            "extras": extras_analysis(all_cards),
        },
    }
    out = SRC / "analysis.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # console digest
    print("=== PRICE (base 'от N' ₽) ===")
    print(f"{'category':22s} {'n':>4} {'p25':>6} {'med':>6} {'p75':>6} {'p90':>7} {'max':>8} {'@500':>5} {'med>500':>8}")
    for leaf in LEAVES:
        p = per_cat[leaf]["prices"]
        print(f"{leaf:22s} {p['n']:>4} {str(p['p25']):>6} {str(p['median']):>6} {str(p['p75']):>6} "
              f"{str(p['p90']):>7} {str(p['max']):>8} {str(round(p['share_at_500_floor']*100)):>4}% {str(p['median_excl_floor']):>8}")
    g = result["global"]
    print("\n=== SELLER STRUCTURE (global) ===")
    print("review buckets:", g["sellers"]["review_buckets"])
    print("heavy(200+ reviews) share:", g["sellers"]["heavy_share"], "| fresh(0) share:", g["sellers"]["fresh_share"])
    print("\n=== COMPETENCY COVERAGE (title / card-desc counts) ===")
    for term, c in g["competency"]["terms"].items():
        if c["in_titles"] or c["in_card_desc"]:
            print(f"  {term:16s} titles={c['in_titles']:3d}  card_desc={c['in_card_desc']:3d}")
    print("\n=== EXTRAS (доп-опции, from cards) ===")
    print(g["extras"])
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
