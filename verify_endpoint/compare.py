"""Сравнение карт: ЭНДПОИНТ (result.structured_output) vs BACKUP (submitted_card).

Для каждой орг и поля схемы считаем «насыщенность» (число непустых значений),
оценку критика и число источников. Выносим вердикт «не хуже / хуже / лучше».

Запуск: python verify_endpoint/compare.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
BAK = HERE / "backup_cards"

# поля схемы и как считать «насыщенность»
def richness(card: dict) -> dict:
    card = card or {}
    contacts = card.get("contacts") or {}
    social = card.get("social") or {}
    ym = card.get("yandex_maps") or {}
    return {
        "what_they_do": 1 if (card.get("what_they_do") or "").strip() else 0,
        "scale_indicators": len(card.get("scale_indicators") or []),
        "tech_stack": len(card.get("tech_stack") or []),
        "vacancies": len(card.get("vacancies") or []),
        "social": sum(len(v) for v in social.values() if isinstance(v, list)),
        "phones": len(contacts.get("phones") or []),
        "emails": len(contacts.get("emails") or []),
        "websites": len(contacts.get("websites") or []),
        "problems_signals": len(card.get("problems_signals") or []),
        "sources": len(card.get("sources") or []),
        "ym_filled": sum(1 for k in ("rating", "reviews_count", "hours") if ym.get(k) not in (None, "", 0)),
    }


KEY_FIELDS = ["what_they_do", "social", "emails", "websites", "vacancies", "sources"]


def critic_score_new(res: dict):
    c = ((res.get("result") or {}).get("critic")) or {}
    return c.get("score")


def critic_score_bak(bak: dict):
    ev = bak.get("critic_events") or []
    return ev[-1].get("score") if ev else None


def main():
    sel = json.load((HERE / "selected_orgs.json").open(encoding="utf-8"))
    names = {str(o["oid"]): o.get("title", "?") for o in sel["orgs"]}
    print(f"{'oid':>14} {'name':22} {'crit_bak':>8} {'crit_new':>8}  verdict")
    print("-" * 80)
    rows = []
    for oid in sel["oids"]:
        rp = RES / f"{oid}.json"
        bp = BAK / f"{oid}.json"
        if not rp.exists():
            print(f"{oid:>14} {names.get(oid,'?')[:22]:22} — нет результата эндпоинта")
            continue
        res = json.loads(rp.read_text(encoding="utf-8"))
        bak = json.loads(bp.read_text(encoding="utf-8"))
        new_card = (res.get("result") or {}).get("structured_output") or {}
        bak_card = bak.get("submitted_card") or {}
        rn, rb = richness(new_card), richness(bak_card)
        # вердикт по ключевым полям
        worse = [f for f in KEY_FIELDS if rn[f] < rb[f]]
        better = [f for f in KEY_FIELDS if rn[f] > rb[f]]
        if res.get("status") != "completed":
            verdict = f"!! status={res.get('status')}"
        elif not worse:
            verdict = "OK (не хуже)" + (f"; лучше: {better}" if better else "")
        else:
            verdict = f"ХУЖЕ по: {worse}" + (f"; лучше: {better}" if better else "")
        cb, cn = critic_score_bak(bak), critic_score_new(res)
        print(f"{oid:>14} {names.get(oid,'?')[:22]:22} {str(cb):>8} {str(cn):>8}  {verdict}")
        rows.append({"oid": oid, "name": names.get(oid), "critic_bak": cb, "critic_new": cn,
                     "richness_bak": rb, "richness_new": rn, "worse": worse, "better": better,
                     "status": res.get("status"),
                     "elapsed_new": res.get("elapsed_s"), "elapsed_bak": bak.get("elapsed_s")})

    print()
    # поле-за-полем агрегат
    if rows:
        print("Суммарно по полям (bak -> new):")
        for f in KEY_FIELDS + ["scale_indicators", "phones", "problems_signals", "ym_filled"]:
            tb = sum(r["richness_bak"][f] for r in rows)
            tn = sum(r["richness_new"][f] for r in rows)
            flag = "  <-- регресс" if tn < tb else ("  ++" if tn > tb else "")
            print(f"  {f:18} {tb:4d} -> {tn:4d}{flag}")
    json.dump(rows, (HERE / "comparison.json").open("w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n[+] {HERE / 'comparison.json'}")


if __name__ == "__main__":
    main()
