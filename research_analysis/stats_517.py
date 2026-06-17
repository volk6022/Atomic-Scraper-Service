"""Детерминированная статистика по 517 ресёрчам (без LLM).

Тулы, успешность, критик, заполняемость полей схемы, контакты, дубль-запросы,
компакции/рефразер. Источник: yandex_enrichment_experiment/data_backup.zip.

Запуск: PYTHONIOENCODING=utf-8 python research_analysis/stats_517.py
"""

from __future__ import annotations

import json
import statistics
import zipfile
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[1]
ZIP = REPO / "yandex_enrichment_experiment" / "data_backup.zip"
OUT = Path(__file__).parent / "results"


def norm_q(q: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(q).lower())).strip()


def card_fields(card: dict) -> dict:
    card = card or {}
    c = card.get("contacts") or {}
    soc = card.get("social") or {}
    ym = card.get("yandex_maps") or {}
    return {
        "what_they_do": 1 if (card.get("what_they_do") or "").strip() else 0,
        "scale_indicators": len(card.get("scale_indicators") or []),
        "tech_stack": len(card.get("tech_stack") or []),
        "vacancies": len(card.get("vacancies") or []),
        "social": sum(len(v) for v in soc.values() if isinstance(v, list)),
        "phones": len(c.get("phones") or []),
        "emails": len(c.get("emails") or []),
        "websites": len(c.get("websites") or []),
        "problems_signals": len(card.get("problems_signals") or []),
        "sources": len(card.get("sources") or []),
        "ym_filled": sum(1 for k in ("rating", "reviews_count", "hours") if ym.get(k) not in (None, "", 0)),
    }


SOCIAL_PLATFORMS = ["vk", "telegram", "instagram", "youtube", "linkedin", "habr"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(ZIP)
    names = [n for n in z.namelist() if "/research/" in n]
    R = []
    for n in names:
        try:
            R.append(json.loads(z.read(n)))
        except Exception:
            pass
    N = len(R)

    # --- успешность ---
    status = Counter(d.get("status", "?") for d in R)
    cards = [d.get("submitted_card") or {} for d in R]
    nonempty_card = sum(1 for c in cards if any(card_fields(c).values()))
    submit_attempts = Counter(d.get("submit_attempts", 0) for d in R)
    no_submit = sum(1 for d in R if (d.get("submit_attempts", 0) or 0) == 0)

    # --- тулы ---
    serp = [(d.get("tool_call_counts") or {}).get("web_serp", 0) for d in R]
    scrape = [(d.get("tool_call_counts") or {}).get("web_scrape", 0) for d in R]
    submit = [(d.get("tool_call_counts") or {}).get("submit_org_card", 0) for d in R]
    ratios = [s / max(1, sc) for s, sc in zip(serp, scrape)]

    # --- дубль-запросы (ties to W1 fix) ---
    dup_frac = []
    for d in R:
        qs = d.get("queries_history") or []
        if not qs:
            dup_frac.append(0.0); continue
        norms = [norm_q(q) for q in qs]
        dup = len(norms) - len(set(norms))
        dup_frac.append(dup / len(norms))
    high_dup = sum(1 for f in dup_frac if f >= 0.3)

    # --- критик / турны / время / токены ---
    scores = [(d.get("critic_events") or [{}])[-1].get("score") for d in R if d.get("critic_events")]
    scores = [s for s in scores if s is not None]
    turns = [d.get("turns", 0) for d in R]
    elapsed = [d.get("elapsed_s", 0) for d in R]
    tokens = [((d.get("tokens") or {}).get("grand_total") or 0) for d in R]
    compactions = [d.get("compactions", 0) for d in R]
    refraser = [d.get("refraser_runs", 0) for d in R]

    # --- заполняемость полей ---
    field_keys = ["what_they_do", "scale_indicators", "tech_stack", "vacancies",
                  "social", "phones", "emails", "websites", "problems_signals",
                  "sources", "ym_filled"]
    fill_rate = {k: round(100 * sum(1 for c in cards if card_fields(c)[k]) / N, 1) for k in field_keys}

    # --- контакты ---
    with_email = sum(1 for c in cards if card_fields(c)["emails"])
    with_phone = sum(1 for c in cards if card_fields(c)["phones"])
    only_phone = sum(1 for c in cards if card_fields(c)["phones"] and not card_fields(c)["emails"])
    with_social = sum(1 for c in cards if card_fields(c)["social"])
    no_contact = sum(1 for c in cards if not card_fields(c)["phones"] and not card_fields(c)["emails"] and not card_fields(c)["social"])
    social_by_platform = Counter()
    for c in cards:
        soc = (c or {}).get("social") or {}
        for p in SOCIAL_PLATFORMS:
            social_by_platform[p] += len(soc.get(p) or [])

    def d(xs):
        xs = [x for x in xs if x is not None]
        if not xs:
            return {}
        return {"mean": round(statistics.mean(xs), 1), "median": statistics.median(xs),
                "min": min(xs), "max": max(xs)}

    rep = {
        "N": N,
        "status": dict(status),
        "nonempty_card": nonempty_card, "nonempty_card_pct": round(100 * nonempty_card / N, 1),
        "no_submit_attempt": no_submit,
        "submit_attempts_dist": dict(sorted(submit_attempts.items())),
        "tools": {
            "web_serp": d(serp), "web_scrape": d(scrape), "submit": d(submit),
            "serp_total": sum(serp), "scrape_total": sum(scrape),
            "serp_per_scrape_ratio": d(ratios),
        },
        "duplicate_queries": {"mean_dup_frac": round(statistics.mean(dup_frac), 3),
                               "researches_with_>=30%_dups": high_dup},
        "critic_score": d(scores),
        "turns": d(turns), "elapsed_s": d(elapsed), "tokens_grand_total": d(tokens),
        "compactions": d(compactions), "refraser_runs": d(refraser),
        "field_fill_rate_pct": fill_rate,
        "contacts": {
            "with_email": with_email, "with_email_pct": round(100 * with_email / N, 1),
            "with_phone": with_phone, "only_phone_no_email": only_phone,
            "only_phone_pct": round(100 * only_phone / N, 1),
            "with_social": with_social, "with_social_pct": round(100 * with_social / N, 1),
            "no_contact_at_all": no_contact,
            "social_by_platform": dict(social_by_platform),
        },
    }
    (OUT / "stats_517.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- печать ---
    print(f"N={N}  status={dict(status)}  непустых карт={nonempty_card} ({rep['nonempty_card_pct']}%)")
    print(f"submit_attempts==0: {no_submit}")
    print(f"ТУЛЫ: serp {rep['tools']['web_serp']}  scrape {rep['tools']['web_scrape']}  "
          f"serp/scrape ratio {rep['tools']['serp_per_scrape_ratio']}")
    print(f"дубль-запросы: mean_frac={rep['duplicate_queries']['mean_dup_frac']}  "
          f"с >=30% дублей: {high_dup}")
    print(f"critic={rep['critic_score']}  turns={rep['turns']}  elapsed={rep['elapsed_s']}  tokens={rep['tokens_grand_total']}")
    print("ЗАПОЛНЯЕМОСТЬ ПОЛЕЙ (%):")
    for k, v in fill_rate.items():
        print(f"   {k:18} {v}")
    print("КОНТАКТЫ:", json.dumps(rep["contacts"], ensure_ascii=False))

    # --- графики ---
    fig, ax = plt.subplots(2, 2, figsize=(15, 11))
    # field fill
    ks = list(fill_rate.keys()); vs = list(fill_rate.values())
    ax[0, 0].barh(ks, vs, color="#2a6"); ax[0, 0].set_title("Заполняемость полей схемы, %")
    ax[0, 0].invert_yaxis(); ax[0, 0].grid(alpha=.3, axis="x")
    for i, v in enumerate(vs):
        ax[0, 0].text(v + 1, i, str(v), va="center", fontsize=8)
    # critic hist
    ax[0, 1].hist(scores, bins=20, color="#39c"); ax[0, 1].set_title(f"Оценка критика (mean {rep['critic_score'].get('mean')})")
    ax[0, 1].grid(alpha=.3)
    # tools
    ax[1, 0].hist(serp, bins=20, alpha=.7, label="web_serp", color="#c33")
    ax[1, 0].hist(scrape, bins=20, alpha=.7, label="web_scrape", color="#39c")
    ax[1, 0].set_title("Вызовы тулов на ресёрч"); ax[1, 0].legend(); ax[1, 0].grid(alpha=.3)
    # contacts pie
    cdata = [with_email, only_phone, with_social - with_email, no_contact]
    ax[1, 1].bar(["email", "только\nтелефон", "соцсети", "нет\nконтактов"],
                 [with_email, only_phone, with_social, no_contact], color=["#2a6", "#c33", "#39c", "#999"])
    ax[1, 1].set_title("Контакты (число орг из 517)"); ax[1, 1].grid(alpha=.3, axis="y")
    fig.tight_layout()
    fig.savefig(OUT / "stats_517.png", dpi=120)
    print(f"\n[+] {OUT/'stats_517.json'}\n[+] {OUT/'stats_517.png'}")


if __name__ == "__main__":
    main()
