"""W2+W3 для 3-зонного прогона: per-research анализ локальной моделью.

Аналог analyze_research.py, адаптированный под НОВЫЙ формат карточек сервиса:
- источник: data_2026-06-10_{optikov,petrogradka,kirovsky}/research/*.json
- anchor берётся из organizations_dedup.json зоны (title/categories/address/
  phones/site из Яндекс-карт)
- digest: result.structured_output + stats.tool_calls + trace_summary
- та же OUTPUT_SHAPE, что и для 517 (сравнимость), + поле depth_assessment.

Идемпотентно (analysis_3zones/{oid}.json). CONCURRENCY=N параллельных запросов
(default 3 = np llama-server; ресёрч-прогон должен быть ЗАВЕРШЁН).

ENV: LIMIT=N, OIDS=a,b,c, CONCURRENCY=N
Запуск: PYTHONIOENCODING=utf-8 uv run python research_analysis/analyze_research_3zones.py
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

REPO = Path(__file__).resolve().parents[1]
ZONES = ["optikov", "petrogradka", "kirovsky"]
BASE = REPO / "yandex_enrichment_experiment"
OUTDIR = Path(__file__).parent / "analysis_3zones"

BASE_URL = "http://localhost:20022/v1/"
API_KEY = "lm-studio"
MODEL = "qwen3.5-9b-claude-4.6-opus-reasoning-distilled"
TIMEOUT = 480

ORG_CARD_FIELDS = [
    "what_they_do", "scale_indicators", "vacancies", "social",
    "contacts.phones", "contacts.emails", "contacts.websites", "yandex_maps",
    "problems_signals", "sources", "deep_dive (типовые поля архетипа)",
    "legal_entity (inn/ogrn/registered_name/founded_year/employee_count/revenue)",
]

OUTPUT_SHAPE = {
    "overall": "good | partial | poor",
    "problems": [{"issue": "...", "evidence": "...", "severity": "low|med|high"}],
    "root_cause_tags": ["no_website|serp_weak|scrape_blocked|schema_gap|only_mobile_phone|over_search|no_email_anywhere|sparse_web_presence|registry_unreachable|other"],
    "missing_fields": ["имена полей схемы, которые СТОИЛО заполнить, но пусто"],
    "multi_branch": "true|false — у организации больше одного филиала / это сеть",
    "is_chain_or_brand": "true|false — крупный бренд/франшиза",
    "is_government": "true|false — гос-/муниципальная организация",
    "contact_quality": "email | landline | mobile_only | social_only | none",
    "depth_assessment": "глубоко | поверхностно | пусто — насколько раскрыта внутренняя кухня (масштаб/спецификация/юрлицо), 1 фраза почему",
}

SYSTEM = (
    "Ты — старший аналитик, проверяющий работу автономного research-агента, который "
    "обогащает карточки организаций. У агента есть тулы web_serp (поиск SearXNG), "
    "web_scrape (httpx/Playwright, извлечение текста страницы) и submit_result "
    "(отправка карточки по JSON-схеме; карточку оценивает критик, включая depth_score "
    "за глубину). Поля схемы карточки: " + ", ".join(ORG_CARD_FIELDS) + ". "
    "Тебе дают РЕЗУЛЬТАТ одного запуска агента. Проанализируй, с какими ПРОБЛЕМАМИ "
    "столкнулся агент и почему, какие поля недозаполнены и можно ли было их найти, "
    "и проставь флаги. Опирайся ТОЛЬКО на предоставленные данные, не выдумывай. "
    "Ответь СТРОГО одним JSON-объектом по форме (без markdown, без пояснений):\n"
    + json.dumps(OUTPUT_SHAPE, ensure_ascii=False)
)


def load_anchors() -> dict[str, dict]:
    anchors: dict[str, dict] = {}
    for z in ZONES:
        f = BASE / f"data_2026-06-10_{z}" / "organizations_dedup.json"
        if not f.exists():
            continue
        for o in json.loads(f.read_text(encoding="utf-8")).get("organizations", []):
            oid = str(o.get("oid"))
            anchors[oid] = {
                "zone": z,
                "name": o.get("title"),
                "categories": [c.get("name") for c in (o.get("categories") or [])][:5],
                "address": o.get("address"),
                "yandex_phones": [p.get("number") for p in (o.get("phones") or [])][:3],
                "yandex_site": o.get("site"),
                "rating": o.get("rating"), "reviews": o.get("reviewsCount"),
            }
    return anchors


def digest(j: dict, anchor: dict) -> str:
    r = j.get("result") or {}
    st = r.get("stats") or {}
    tr = r.get("trace_summary") or {}
    visited = tr.get("visited_urls") or []
    domains = sorted({re.sub(r"^https?://", "", u).split("/")[0] for u in visited})[:25]
    obj = {
        "anchor": anchor,
        "tool_call_counts": st.get("tool_calls"),
        "turns": st.get("turns"), "elapsed_s": round(st.get("elapsed_seconds") or 0),
        "submit_attempts": st.get("submit_attempts"),
        "critic": r.get("critic"),
        "queries_history": (tr.get("queries_history") or [])[:40],
        "visited_domains": domains,
        "blocked_domains": tr.get("blocked_domains"),
        "submitted_card": r.get("structured_output"),
    }
    return json.dumps(obj, ensure_ascii=False)[:14000]


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?result>", " ", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        s = m.group(0)
        for end in range(len(s), 0, -1):
            if s[end - 1] == "}":
                try:
                    return json.loads(s[:end])
                except Exception:
                    continue
        return None


_lock = threading.Lock()
_counters = {"done": 0, "ok": 0, "fail": 0}
_t0 = time.time()


def process(client: OpenAI, system: str, f: Path, anchors: dict) -> None:
    oid = f.stem
    out = OUTDIR / f"{oid}.json"
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return
    anchor = anchors.get(oid) or {"name": j.get("title")}
    parsed = None
    try:
        resp = client.chat.completions.create(
            model=MODEL, temperature=0.2,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": digest(j, anchor)},
                      {"role": "assistant", "content": "{"}],  # prefill → форсим JSON
        )
        content = resp.choices[0].message.content or ""
        if not content.lstrip().startswith("{"):
            content = "{" + content
        parsed = extract_json(content)
    except Exception as e:
        print(f"  [{oid}] LLM error: {str(e)[:120]}", flush=True)
    rec = {"oid": oid, "name": anchor.get("name"), "zone": anchor.get("zone"),
           "analysis": parsed, "raw_ok": parsed is not None}
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    with _lock:
        _counters["done"] += 1
        _counters["ok" if parsed else "fail"] += 1
        n = _counters["done"]
        rate = (time.time() - _t0) / max(1, n)
        print(f"[{n}] {oid} {'OK' if parsed else 'PARSE_FAIL'} "
              f"({rate:.0f}s/шт, ok={_counters['ok']} fail={_counters['fail']})", flush=True)


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    anchors = load_anchors()
    files = []
    for z in ZONES:
        files += sorted((BASE / f"data_2026-06-10_{z}" / "research").glob("*.json"))
    oids_filter = set(filter(None, os.getenv("OIDS", "").split(",")))
    todo = []
    for f in files:
        if oids_filter and f.stem not in oids_filter:
            continue
        if (OUTDIR / f.name).exists():
            continue
        todo.append(f)
    limit = int(os.getenv("LIMIT", "0") or 0)
    if limit:
        todo = todo[:limit]
    conc = int(os.getenv("CONCURRENCY", "3") or 3)
    print(f"всего файлов={len(files)}, к обработке={len(todo)}, concurrency={conc}", flush=True)

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=TIMEOUT)
    with ThreadPoolExecutor(max_workers=conc) as ex:
        for f in todo:
            ex.submit(process, client, SYSTEM, f, anchors)
    print(f"\n[готово] обработано={_counters['done']} ok={_counters['ok']} "
          f"parse_fail={_counters['fail']}")


if __name__ == "__main__":
    main()
