"""W2+W3 stage-2: сводка по per-research анализам.

1) ДЕТЕРМИНИРОВАННО (без GPU): tally флагов и тегов из analysis/{oid}.json →
   статистика + списки W3: multi_branch_orgs.json, government_orgs.json,
   chains_brands.json, contact_quality распределение, топ root_cause_tags,
   топ недозаполненных полей.
2) LLM-ТЕМАТИЧЕСКАЯ СВОДКА (нужна GPU): батчами по 10 «problems» → темы →
   финальная мета-сводка. Включается RUN_LLM_SUMMARY=1.

Запуск:
  python research_analysis/summarize_analyses.py            # только tally
  RUN_LLM_SUMMARY=1 python research_analysis/summarize_analyses.py
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADIR = HERE / "analysis"
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
        print("Нет analysis/*.json — сначала запусти analyze_research.py")
        return

    overall = Counter()
    contact_q = Counter()
    tags = Counter()
    missing = Counter()
    severity = Counter()
    multi_branch, government, chains = [], [], []
    for r in recs:
        a = r.get("analysis") or {}
        name, oid = r.get("name"), r.get("oid")
        overall[str(a.get("overall"))] += 1
        contact_q[str(a.get("contact_quality"))] += 1
        for t in a.get("root_cause_tags") or []:
            tags[str(t)] += 1
        for m in a.get("missing_fields") or []:
            missing[str(m)] += 1
        for p in a.get("problems") or []:
            severity[str(p.get("severity"))] += 1
        if as_bool(a.get("multi_branch")):
            multi_branch.append({"oid": oid, "name": name})
        if as_bool(a.get("is_government")):
            government.append({"oid": oid, "name": name})
        if as_bool(a.get("is_chain_or_brand")):
            chains.append({"oid": oid, "name": name})

    summary = {
        "analyzed": N,
        "overall": dict(overall),
        "contact_quality": dict(contact_q),
        "top_root_cause_tags": tags.most_common(20),
        "top_missing_fields": missing.most_common(15),
        "problem_severity": dict(severity),
        "counts": {"multi_branch": len(multi_branch), "government": len(government),
                   "chains_brands": len(chains)},
    }
    (OUT / "analysis_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "multi_branch_orgs.json").write_text(json.dumps(multi_branch, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "government_orgs.json").write_text(json.dumps(government, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "chains_brands.json").write_text(json.dumps(chains, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Проанализировано: {N}")
    print("overall:", dict(overall))
    print("contact_quality:", dict(contact_q))
    print("counts:", summary["counts"])
    print("top root_cause_tags:", tags.most_common(10))
    print("top missing_fields:", missing.most_common(10))
    print(f"[+] {OUT/'analysis_summary.json'} (+ multi_branch / government / chains)")

    if os.getenv("RUN_LLM_SUMMARY") != "1":
        print("\n(LLM-тематическая сводка пропущена; RUN_LLM_SUMMARY=1 чтобы включить)")
        return

    # --- LLM-тематическая сводка батчами по 10 ---
    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=240)
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
        print(f"  батч {i//10+1}/{(len(problems_blobs)+9)//10}")
    # финальная мета-сводка
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
    (OUT / "themes_summary.md").write_text(
        "# Тематическая сводка проблем агента\n\n## Итог\n" + meta +
        "\n\n## По батчам\n" + "\n\n---\n\n".join(batch_summaries), encoding="utf-8")
    print(f"[+] {OUT/'themes_summary.md'}")


if __name__ == "__main__":
    main()
