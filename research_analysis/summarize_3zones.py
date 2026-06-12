"""Stage-2 сводка по per-research анализам 3-зонного прогона.

Аналог summarize_analyses.py для analysis_3zones/. Tally флагов/тегов +
W3-списки (+ разбивка по зонам и depth_assessment) → results/*_3zones.json;
опционально LLM-тематическая сводка (RUN_LLM_SUMMARY=1) → themes_3zones.md.

Запуск: PYTHONIOENCODING=utf-8 uv run python research_analysis/summarize_3zones.py
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADIR = HERE / "analysis_3zones"
OUT = HERE / "results"

BASE_URL = "http://localhost:20022/v1/"
API_KEY = "lm-studio"
MODEL = "qwen3.5-9b-claude-4.6-opus-reasoning-distilled"


def as_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes", "да")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    recs = []
    for f in ADIR.glob("*.json"):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("analysis"):
            recs.append(r)
    N = len(recs)
    if not N:
        print("Нет analysis_3zones/*.json — сначала analyze_research_3zones.py")
        return

    overall = Counter()
    contact_q = Counter()
    tags = Counter()
    missing = Counter()
    severity = Counter()
    depth_assess = Counter()
    by_zone_overall: dict[str, Counter] = {}
    multi_branch, government, chains = [], [], []
    for r in recs:
        a = r.get("analysis") or {}
        name, oid, zone = r.get("name"), r.get("oid"), r.get("zone") or "?"
        overall[str(a.get("overall"))] += 1
        contact_q[str(a.get("contact_quality"))] += 1
        da = str(a.get("depth_assessment") or "?").split()[0].strip(" ,.;—-").lower()
        depth_assess[da] += 1
        by_zone_overall.setdefault(zone, Counter())[str(a.get("overall"))] += 1
        for t in a.get("root_cause_tags") or []:
            tags[str(t)] += 1
        for m in a.get("missing_fields") or []:
            missing[str(m)] += 1
        for p in a.get("problems") or []:
            severity[str(p.get("severity"))] += 1
        if as_bool(a.get("multi_branch")):
            multi_branch.append({"oid": oid, "name": name, "zone": zone})
        if as_bool(a.get("is_government")):
            government.append({"oid": oid, "name": name, "zone": zone})
        if as_bool(a.get("is_chain_or_brand")):
            chains.append({"oid": oid, "name": name, "zone": zone})

    summary = {
        "analyzed": N,
        "overall": dict(overall),
        "overall_by_zone": {z: dict(c) for z, c in by_zone_overall.items()},
        "contact_quality": dict(contact_q),
        "depth_assessment": dict(depth_assess),
        "top_root_cause_tags": tags.most_common(20),
        "top_missing_fields": missing.most_common(15),
        "problem_severity": dict(severity),
        "counts": {"multi_branch": len(multi_branch), "government": len(government),
                   "chains_brands": len(chains)},
    }
    (OUT / "analysis_3zones_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "multi_branch_orgs_3zones.json").write_text(json.dumps(multi_branch, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "government_orgs_3zones.json").write_text(json.dumps(government, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "chains_brands_3zones.json").write_text(json.dumps(chains, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Проанализировано: {N}")
    print("overall:", dict(overall))
    print("overall_by_zone:", json.dumps(summary["overall_by_zone"], ensure_ascii=False))
    print("contact_quality:", dict(contact_q))
    print("depth_assessment:", dict(depth_assess))
    print("counts:", summary["counts"])
    print("top root_cause_tags:", tags.most_common(10))
    print("top missing_fields:", missing.most_common(10))
    print(f"[+] {OUT/'analysis_3zones_summary.json'} (+ multi_branch / government / chains)")

    if os.getenv("RUN_LLM_SUMMARY") != "1":
        print("\n(LLM-тематическая сводка пропущена; RUN_LLM_SUMMARY=1 чтобы включить)")
        return

    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=480)
    problems_blobs = []
    for r in recs:
        a = r.get("analysis") or {}
        ps = "; ".join(f"{p.get('issue')} ({p.get('severity')})" for p in (a.get("problems") or []))
        if ps:
            problems_blobs.append(f"- {r.get('name')}: {ps}")
    batch_summaries = []
    for i in range(0, len(problems_blobs), 10):
        chunk = "\n".join(problems_blobs[i:i + 10])
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0.3,
                messages=[{"role": "system", "content":
                           "Сгруппируй проблемы research-агента в темы и кратко опиши каждую "
                           "с числом случаев. Ответь сжато, по-русски, маркированным списком."},
                          {"role": "user", "content": chunk}])
            batch_summaries.append(resp.choices[0].message.content or "")
        except Exception as e:
            batch_summaries.append(f"(batch error: {e})")
        print(f"  батч {i//10+1}/{(len(problems_blobs)+9)//10}", flush=True)
    meta = ""
    try:
        resp = client.chat.completions.create(
            model=MODEL, temperature=0.3,
            messages=[{"role": "system", "content":
                       "Сведи частные сводки проблем в ИТОГОВЫЙ список главных проблем "
                       "research-агента с приоритетами и рекомендациями по фиксу. По-русски."},
                      {"role": "user", "content": "\n\n".join(batch_summaries)[:30000]}])
        meta = resp.choices[0].message.content or ""
    except Exception as e:
        meta = f"(meta error: {e})"
    (OUT / "themes_3zones.md").write_text(
        "# Тематическая сводка проблем агента (3 зоны, 2026-06-12)\n\n## Итог\n" + meta +
        "\n\n## По батчам\n" + "\n\n---\n\n".join(batch_summaries), encoding="utf-8")
    print(f"[+] {OUT/'themes_3zones.md'}")


if __name__ == "__main__":
    main()
