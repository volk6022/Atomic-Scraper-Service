"""W2+W3: per-research анализ локальной моделью (ОДИН проход на ресёрч).

Для каждого из 517 ресёрчей модель получает: компактный дайджест результата
(+ опц. исходник агента) и схему карточки, и возвращает СТРУКТУРИРОВАННЫЙ разбор:
проблемы агента, корневые причины, недозаполненные поля, и флаги W3
(мультифилиал / сеть-бренд / гос / тип контакта).

Идемпотентно: пропускает уже готовые analysis/{oid}.json. Последовательно (1 GPU).

ENV:
  LIMIT=N               — обработать только первые N (smoke)
  INCLUDE_AGENT_SOURCE=1 — вложить полный исходник simple_agent_v2.py в систему
  OIDS=a,b,c            — только указанные oid

Запуск (когда GPU свободна):
  PYTHONIOENCODING=utf-8 python research_analysis/analyze_research.py
  LIMIT=3 python research_analysis/analyze_research.py   # smoke
"""

from __future__ import annotations

import json
import os
import re
import time
import zipfile
from pathlib import Path

from openai import OpenAI

REPO = Path(__file__).resolve().parents[1]
ZIP = REPO / "yandex_enrichment_experiment" / "data_backup.zip"
OUTDIR = Path(__file__).parent / "analysis"

BASE_URL = "http://localhost:20022/v1/"
API_KEY = "lm-studio"
MODEL = "qwen3.5-9b-claude-4.6-opus-reasoning-distilled"
TIMEOUT = 240

ORG_CARD_FIELDS = [
    "what_they_do", "scale_indicators", "tech_stack", "vacancies", "social",
    "contacts.phones", "contacts.emails", "contacts.websites", "yandex_maps",
    "problems_signals", "sources",
]

# Структура, которую модель должна вернуть (описываем в промпте; парсим робастно)
OUTPUT_SHAPE = {
    "overall": "good | partial | poor",
    "problems": [{"issue": "...", "evidence": "...", "severity": "low|med|high"}],
    "root_cause_tags": ["no_website|serp_weak|scrape_blocked|schema_gap|only_mobile_phone|over_search|no_email_anywhere|sparse_web_presence|other"],
    "missing_fields": ["имена полей схемы, которые СТОИЛО заполнить, но пусто"],
    "multi_branch": "true|false — у организации больше одного филиала / это сеть",
    "is_chain_or_brand": "true|false — крупный бренд/франшиза",
    "is_government": "true|false — гос-/муниципальная организация",
    "contact_quality": "email | landline | mobile_only | social_only | none",
}

SYSTEM = (
    "Ты — старший аналитик, проверяющий работу автономного research-агента, который "
    "обогащает карточки организаций. У агента есть тулы web_serp (поиск SearXNG), "
    "web_scrape (Playwright, извлечение текста страницы) и submit (отправка карточки "
    "по JSON-схеме; карточку оценивает критик). Поля схемы карточки: "
    + ", ".join(ORG_CARD_FIELDS) + ". "
    "Тебе дают РЕЗУЛЬТАТ одного запуска агента. Проанализируй, с какими ПРОБЛЕМАМИ "
    "столкнулся агент и почему, какие поля недозаполнены и можно ли было их найти, "
    "и проставь флаги. Опирайся ТОЛЬКО на предоставленные данные, не выдумывай. "
    "Ответь СТРОГО одним JSON-объектом по форме (без markdown, без пояснений):\n"
    + json.dumps(OUTPUT_SHAPE, ensure_ascii=False)
)


def digest(d: dict) -> str:
    anchor = d.get("anchor") or {}
    crit = (d.get("critic_events") or [{}])[-1]
    card = d.get("submitted_card") or {}
    visited = d.get("visited_urls") or []
    domains = sorted({re.sub(r"^https?://", "", u).split("/")[0] for u in visited})[:25]
    obj = {
        "anchor": {k: anchor.get(k) for k in ("name", "categories", "address", "yandex_phones", "yandex_site")},
        "tool_call_counts": d.get("tool_call_counts"),
        "turns": d.get("turns"), "elapsed_s": d.get("elapsed_s"),
        "submit_attempts": d.get("submit_attempts"),
        "critic": {k: crit.get(k) for k in ("score", "verdict", "missing", "wrong", "feedback")},
        "queries_history": (d.get("queries_history") or [])[:40],
        "visited_domains": domains,
        "blocked_domains": d.get("blocked_domains_at_end"),
        "submitted_card": card,
    }
    return json.dumps(obj, ensure_ascii=False)[:14000]


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    # убрать reasoning <think>...</think> и теги
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?result>", " ", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # последняя попытка: до последней '}'
        s = m.group(0)
        for end in range(len(s), 0, -1):
            if s[end - 1] == "}":
                try:
                    return json.loads(s[:end])
                except Exception:
                    continue
        return None


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=TIMEOUT)
    z = zipfile.ZipFile(ZIP)
    names = sorted(n for n in z.namelist() if "/research/" in n)

    oids_filter = set(filter(None, os.getenv("OIDS", "").split(",")))
    system = SYSTEM
    if os.getenv("INCLUDE_AGENT_SOURCE") == "1":
        src = (REPO / "yandex_enrichment_experiment" / "simple_agent_v2.py").read_text(encoding="utf-8")
        system += "\n\n=== ИСХОДНИК АГЕНТА (simple_agent_v2.py) ===\n" + src[:30000]

    limit = int(os.getenv("LIMIT", "0") or 0)
    done = ok = fail = 0
    t0 = time.time()
    for n in names:
        oid = n.split("/")[-1].replace("__local.json", "")
        if oids_filter and oid not in oids_filter:
            continue
        out = OUTDIR / f"{oid}.json"
        if out.exists():
            done += 1
            continue
        if limit and done >= limit:
            break
        try:
            d = json.loads(z.read(n))
        except Exception:
            continue
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0.2,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": digest(d)},
                          {"role": "assistant", "content": "{"}],  # prefill → форсим JSON
            )
            content = resp.choices[0].message.content or ""
            if not content.lstrip().startswith("{"):
                content = "{" + content
            parsed = extract_json(content)
        except Exception as e:
            parsed = None
            print(f"  [{oid}] LLM error: {str(e)[:120]}")
        rec = {"oid": oid, "name": (d.get("anchor") or {}).get("name"),
               "analysis": parsed, "raw_ok": parsed is not None}
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        done += 1
        if parsed:
            ok += 1
        else:
            fail += 1
        rate = (time.time() - t0) / max(1, ok + fail)
        print(f"[{done}] {oid} {'OK' if parsed else 'PARSE_FAIL'}  "
              f"({rate:.0f}s/шт, ok={ok} fail={fail})", flush=True)

    print(f"\n[готово] обработано={done} ok={ok} parse_fail={fail}")


if __name__ == "__main__":
    main()
