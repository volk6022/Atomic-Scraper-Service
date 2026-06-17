"""Детерминированная статистика по 3-зонным ресёрчам 2026-06-10/12 (без LLM).

Аналог stats_517.py для НОВОГО формата карточек сервиса (result.structured_output
/ stats / trace_summary вместо плоского формата simple_agent_v2). Добавлены
новые измерения: depth_score критика, заполняемость deep_dive (типовые поля
Workstream A) и legal_entity (ИНН/ОГРН — Workstream C), разбивка по зонам.

Источник: yandex_enrichment_experiment/data_2026-06-10_{optikov,petrogradka,kirovsky}/research
Запуск: PYTHONIOENCODING=utf-8 uv run python research_analysis/stats_3zones.py
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
ZONES = ["optikov", "petrogradka", "kirovsky"]
DIRS = {z: REPO / "yandex_enrichment_experiment" / f"data_2026-06-10_{z}" / "research" for z in ZONES}
OUT = Path(__file__).parent / "results"

SOCIAL_PLATFORMS = ["vk", "telegram", "instagram", "youtube", "linkedin", "habr"]


def norm_q(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(q).lower())).strip()


def _nonempty(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        s = v.strip().lower()
        return bool(s) and not s.startswith(("не указано", "не найдено", "нет данных", "unknown", "n/a"))
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def card_fields(card: dict) -> dict:
    card = card or {}
    c = card.get("contacts") or {}
    soc = card.get("social") or {}
    ym = card.get("yandex_maps") or {}
    dd = card.get("deep_dive") or {}
    le = card.get("legal_entity") or {}
    inn = str(le.get("inn") or "")
    return {
        "what_they_do": 1 if (card.get("what_they_do") or "").strip() else 0,
        "scale_indicators": len(card.get("scale_indicators") or []),
        "vacancies": len(card.get("vacancies") or []),
        "social": sum(len(v) for v in soc.values() if isinstance(v, list)),
        "phones": len(c.get("phones") or []),
        "emails": len(c.get("emails") or []),
        "websites": len(c.get("websites") or []),
        "problems_signals": len(card.get("problems_signals") or []),
        "sources": len(card.get("sources") or []),
        "ym_filled": sum(1 for k in ("rating", "reviews_count", "hours") if ym.get(k) not in (None, "", 0)),
        "deep_dive_filled": sum(1 for v in dd.values() if _nonempty(v)),
        "inn_found": 1 if re.fullmatch(r"\d{10}|\d{12}", inn) else 0,
        "legal_filled": sum(1 for v in le.values() if _nonempty(v)),
    }


def d(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {}
    return {"mean": round(statistics.mean(xs), 1), "median": round(statistics.median(xs), 1),
            "min": round(min(xs), 1), "max": round(max(xs), 1)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    R = []  # (zone, top-level json)
    for z, dpath in DIRS.items():
        for f in sorted(dpath.glob("*.json")):
            try:
                R.append((z, json.loads(f.read_text(encoding="utf-8"))))
            except Exception:
                pass
    N = len(R)
    res = [(z, (j.get("result") or {})) for z, j in R]
    cards = [(r.get("structured_output") or {}) for _, r in res]
    stats = [(r.get("stats") or {}) for _, r in res]
    trace = [(r.get("trace_summary") or {}) for _, r in res]
    critic = [(r.get("critic") or {}) for _, r in res]

    status = Counter(j.get("status", "?") for _, j in R)
    nonempty_card = sum(1 for c in cards if any(card_fields(c).values()))
    submit_attempts = Counter(s.get("submit_attempts", 0) for s in stats)
    accepted = sum(1 for t in trace if t.get("accepted"))

    serp = [(s.get("tool_calls") or {}).get("web_serp", 0) for s in stats]
    scrape = [(s.get("tool_calls") or {}).get("web_scrape", 0) for s in stats]
    ratios = [a / max(1, b) for a, b in zip(serp, scrape)]

    dup_frac = []
    for t in trace:
        qs = t.get("queries_history") or []
        if not qs:
            dup_frac.append(0.0)
            continue
        norms = [norm_q(q) for q in qs]
        dup_frac.append((len(norms) - len(set(norms))) / len(norms))
    high_dup = sum(1 for f in dup_frac if f >= 0.3)

    scores = [c.get("score") for c in critic if c.get("score") is not None]
    depth = [c.get("depth_score") for c in critic if c.get("depth_score") is not None]
    turns = [s.get("turns", 0) for s in stats]
    elapsed = [s.get("elapsed_seconds", 0) for s in stats]
    tokens = [((s.get("tokens") or {}).get("grand_total") or 0) for s in stats]
    compactions = [s.get("compactions", 0) for s in stats]
    refraser = [t.get("refraser_runs", 0) for t in trace]

    field_keys = list(card_fields({}).keys())
    fill_rate = {k: round(100 * sum(1 for c in cards if card_fields(c)[k]) / N, 1) for k in field_keys}

    cf = [card_fields(c) for c in cards]
    with_email = sum(1 for x in cf if x["emails"])
    with_phone = sum(1 for x in cf if x["phones"])
    only_phone = sum(1 for x in cf if x["phones"] and not x["emails"])
    with_social = sum(1 for x in cf if x["social"])
    no_contact = sum(1 for x in cf if not x["phones"] and not x["emails"] and not x["social"])
    social_by_platform = Counter()
    for c in cards:
        soc = (c or {}).get("social") or {}
        for p in SOCIAL_PLATFORMS:
            social_by_platform[p] += len(soc.get(p) or [])

    # --- per-zone key rates ---
    per_zone = {}
    for z in ZONES:
        idx = [i for i, (zz, _) in enumerate(res) if zz == z]
        if not idx:
            continue
        n = len(idx)
        per_zone[z] = {
            "n": n,
            "email_pct": round(100 * sum(1 for i in idx if cf[i]["emails"]) / n, 1),
            "social_pct": round(100 * sum(1 for i in idx if cf[i]["social"]) / n, 1),
            "inn_pct": round(100 * sum(1 for i in idx if cf[i]["inn_found"]) / n, 1),
            "deep_dive_pct": round(100 * sum(1 for i in idx if cf[i]["deep_dive_filled"]) / n, 1),
            "critic_score": d([critic[i].get("score") for i in idx]),
            "depth_score": d([critic[i].get("depth_score") for i in idx]),
            "elapsed_s": d([stats[i].get("elapsed_seconds") for i in idx]),
            "tokens": d([(stats[i].get("tokens") or {}).get("grand_total") for i in idx]),
        }

    rep = {
        "N": N,
        "zones": {z: len([1 for zz, _ in res if zz == z]) for z in ZONES},
        "status": dict(status),
        "accepted_by_critic": accepted,
        "nonempty_card": nonempty_card, "nonempty_card_pct": round(100 * nonempty_card / N, 1),
        "submit_attempts_dist": dict(sorted(submit_attempts.items())),
        "tools": {
            "web_serp": d(serp), "web_scrape": d(scrape),
            "serp_total": sum(serp), "scrape_total": sum(scrape),
            "serp_per_scrape_ratio": d(ratios),
        },
        "duplicate_queries": {"mean_dup_frac": round(statistics.mean(dup_frac), 3),
                              "researches_with_>=30%_dups": high_dup},
        "critic_score": d(scores),
        "depth_score": d(depth),
        "turns": d(turns), "elapsed_s": d(elapsed), "tokens_grand_total": d(tokens),
        "compactions": {"dist": dict(Counter(compactions)), **d(compactions)},
        "refraser_runs": d(refraser),
        "field_fill_rate_pct": fill_rate,
        "contacts": {
            "with_email": with_email, "with_email_pct": round(100 * with_email / N, 1),
            "with_phone": with_phone, "only_phone_no_email": only_phone,
            "only_phone_pct": round(100 * only_phone / N, 1),
            "with_social": with_social, "with_social_pct": round(100 * with_social / N, 1),
            "no_contact_at_all": no_contact,
            "social_by_platform": dict(social_by_platform),
        },
        "per_zone": per_zone,
    }
    (OUT / "stats_3zones.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"N={N} zones={rep['zones']} status={dict(status)} accepted={accepted}")
    print(f"critic={rep['critic_score']} depth={rep['depth_score']}")
    print(f"turns={rep['turns']} elapsed={rep['elapsed_s']} tokens={rep['tokens_grand_total']}")
    print("ЗАПОЛНЯЕМОСТЬ ПОЛЕЙ (%):")
    for k, v in fill_rate.items():
        print(f"   {k:18} {v}")
    print("КОНТАКТЫ:", json.dumps(rep["contacts"], ensure_ascii=False))
    print("ПО ЗОНАМ:", json.dumps(per_zone, ensure_ascii=False, indent=1))

    fig, ax = plt.subplots(2, 2, figsize=(15, 11))
    ks = list(fill_rate.keys()); vs = list(fill_rate.values())
    ax[0, 0].barh(ks, vs, color="#2a6"); ax[0, 0].set_title("Заполняемость полей схемы, % (300 орг, 3 зоны)")
    ax[0, 0].invert_yaxis(); ax[0, 0].grid(alpha=.3, axis="x")
    for i, v in enumerate(vs):
        ax[0, 0].text(v + 1, i, str(v), va="center", fontsize=8)
    ax[0, 1].hist(scores, bins=20, color="#39c", alpha=.8, label=f"score (mean {rep['critic_score'].get('mean')})")
    ax[0, 1].hist(depth, bins=20, color="#c63", alpha=.6, label=f"depth (mean {rep['depth_score'].get('mean')})")
    ax[0, 1].set_title("Оценки критика"); ax[0, 1].legend(); ax[0, 1].grid(alpha=.3)
    ax[1, 0].hist(serp, bins=20, alpha=.7, label="web_serp", color="#c33")
    ax[1, 0].hist(scrape, bins=20, alpha=.7, label="web_scrape", color="#39c")
    ax[1, 0].set_title("Вызовы тулов на ресёрч"); ax[1, 0].legend(); ax[1, 0].grid(alpha=.3)
    ax[1, 1].bar(["email", "только\nтелефон", "соцсети", "ИНН", "нет\nконтактов"],
                 [with_email, only_phone, with_social, sum(x["inn_found"] for x in cf), no_contact],
                 color=["#2a6", "#c33", "#39c", "#a3c", "#999"])
    ax[1, 1].set_title(f"Контакты и ИНН (из {N} орг)"); ax[1, 1].grid(alpha=.3, axis="y")
    fig.tight_layout()
    fig.savefig(OUT / "stats_3zones.png", dpi=120)
    print(f"\n[+] {OUT/'stats_3zones.json'}\n[+] {OUT/'stats_3zones.png'}")


if __name__ == "__main__":
    main()
