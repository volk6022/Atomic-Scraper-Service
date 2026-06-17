"""Filter Yandex orgs that an independent ML freelancer can't reasonably approach.

Two passes:
  1. **Regex prefilter** — drops orgs whose name matches obvious state-owned
     prefixes (ФГУП, ГБУ, ...) or mega-brand keywords (Сбербанк, Газпром, ...).
  2. **LLM judge** — local qwen3.5-9b classifies each survivor with a structured
     tool call. Asks: "Is this a state-owned / federally regulated body OR a
     very-large national/international brand that a solo ML engineer without
     legal-entity (no ИП/ООО) cannot reasonably serve?" → bool + reason.

Output: `data/organizations_filtered.json` with `keep` and `dropped` lists.

Usage:
    uv run python yandex_enrichment_experiment/02_filter_orgs.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA_DIR = Path(__file__).parent / "data"
ORGS_PATH = DATA_DIR / "organizations.json"
OUT_PATH = DATA_DIR / "organizations_filtered.json"

LLM_BASE = "http://localhost:20022/v1/"
LLM_KEY = "lm-studio"
LLM_MODEL = "qwen3.5-9b-claude-4.6-opus-reasoning-distilled"

CONCURRENCY = 3  # matches llama-server -np 3
LLM_TIMEOUT_S = 60.0

# --- regex prefilter --------------------------------------------------------

STATE_PATTERNS: list[re.Pattern] = [
    # explicit state prefixes
    re.compile(r"\b(?:ФГУП|ФГБУ|ФКУ|ГБУ|МКУ|ГУП|МУП|МУ|БУ|КГБУ|ОГБУ|ОГКУ|ГБОУ|МБОУ|МАОУ|МДОУ|ГБДОУ|МБДОУ)\b", re.IGNORECASE),
    re.compile(r"\bФГБОУ\b", re.IGNORECASE),
    # ministries / authorities
    re.compile(r"\b(?:Министерство|Управление\s+ФНС|Прокуратура|Полиция|УМВД|ОВД|ФССП|ФСБ|Росреестр|Роспотребнадзор|Роскомнадзор|Россельхознадзор|Налоговая|ИФНС|МФЦ|Военкомат|Военный\s+комиссариат|Пенсионный\s+фонд|ПФР|СФР|ФОМС)\b", re.IGNORECASE),
    re.compile(r"\b(?:Администрация|Муниципальное\s+образование|Совет\s+депутатов)\b", re.IGNORECASE),
    re.compile(r"\bРоссийск\w*\s+государствен\w*", re.IGNORECASE),
    re.compile(r"\bгосударствен(?:н|ый|ная|ное|ные)\b", re.IGNORECASE),
]

MEGA_BRAND_PATTERNS: list[re.Pattern] = [
    # banks
    re.compile(r"\b(?:Сбербанк|СберБанк|Сбер|Газпромбанк|ВТБ|Альфа[-\s]?Банк|Тинькофф|Т-Банк|Райффайзен|Россельхозбанк|Промсвязьбанк|ПСБ|Совкомбанк|Открытие|Росбанк|Юникредит|Уралсиб|Хоум\s*Кредит|ОТП)\b", re.IGNORECASE),
    # telecom
    re.compile(r"\b(?:Билайн|МТС|Мегафон|Tele2|Теле2|Йота|Yota|Ростелеком|МГТС|ЭР-Телеком|Дом\.ру|Дом\s+ру)\b", re.IGNORECASE),
    # oil/gas/utilities
    re.compile(r"\b(?:Газпром|Лукойл|Роснефть|Сургутнефтегаз|Татнефть|Башнефть|Транснефть|Россети|РусГидро|ФСК)\b", re.IGNORECASE),
    # retail chains
    re.compile(r"\b(?:Пятёрочка|Пятерочка|Магнит|Перекрёсток|Перекресток|Лента|Дикси|Ашан|Метро|Метро\s*Cash|Глобус|ВкусВилл|Окей|Карусель|Спар|SPAR|Spar|Лента|Виктория|Билла|BILLA)\b", re.IGNORECASE),
    # fast food / international chains
    re.compile(r"\b(?:McDonald|Макдоналдс|Вкусно[-—\s]и[\s]?точка|KFC|Бургер[-\s]?Кинг|Burger\s*King|Subway|Starbucks|Старбакс|Шоколадница|Coffee\s*Like|Кофехауз|Пицца\s*Хат|Pizza\s*Hut|Domino|Папа\s*Джонс|Papa\s*Johns|Теремок|Крошка[-\s]?Картошка)\b", re.IGNORECASE),
    # tech giants
    re.compile(r"\b(?:Яндекс|Yandex|Mail\.?ru|VK|ВКонтакте|Одноклассники|Касперский|Kaspersky|1С|1C(?!\d)|Софтлайн|Лаборатория\s+Касперского|Rambler|Рамблер|Wildberries|Озон|Ozon|Авито|Avito)\b", re.IGNORECASE),
    # aviation/transport mega
    re.compile(r"\b(?:Аэрофлот|Россия\s+\(авиа|S7\s+Airlines|Сапсан|РЖД|Российские\s+железные|Метрополитен)\b", re.IGNORECASE),
    # pharma chains (very large)
    re.compile(r"\b(?:36\.6|Ригла|Озерки|Невис|Здравсити|Аптечная\s+сеть)\b", re.IGNORECASE),
    # gas stations
    re.compile(r"\b(?:Shell|Шелл|Neste|Несте|ТНК|Лукойл-АЗС|ЕКА|Газпромнефть|Татнефть-АЗС)\b", re.IGNORECASE),
]

ALL_PATTERNS: list[tuple[re.Pattern, str]] = [
    *[(p, "state") for p in STATE_PATTERNS],
    *[(p, "mega_brand") for p in MEGA_BRAND_PATTERNS],
]


def regex_prefilter(org: dict) -> tuple[bool, str | None]:
    """Returns (drop_yes, reason)."""
    title = (org.get("title") or "") + " " + (org.get("seoname") or "")
    for pat, tag in ALL_PATTERNS:
        m = pat.search(title)
        if m:
            return True, f"regex:{tag}:{m.group(0)[:60]}"
    return False, None


# --- LLM judge --------------------------------------------------------------

LLM_SYSTEM = """You judge whether a Saint Petersburg local business is a viable client for a solo Machine Learning freelancer working without legal entity (no ИП, no ООО).

The freelancer offers custom ML/AI/automation services. They CANNOT realistically work with:
- State / federal / municipal bodies (any organ of government, public schools, kindergartens, hospitals under state ownership, social services).
- Very-large national or multinational corporate brands (Sberbank, Gazprom, Yandex, McDonald's, Pyaterochka, etc.) — they have their own ML teams or strict procurement.
- Banks and telecom operators (security/regulatory barriers).
- Federally regulated medical clinics or licensed pharmaceutical chains.

The freelancer CAN work with:
- Small/medium private businesses (single shop, single café, single clinic).
- Local independent restaurants, salons, repair shops, sport clubs, schools (private), driving schools.
- Solo professionals (lawyers, doctors, photographers).
- Small online stores or local e-commerce.

Call submit_judgment exactly once with your decision.
"""

JUDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_judgment",
        "description": "Submit your filtering decision for this organization.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["too_big_or_state", "reason"],
            "properties": {
                "too_big_or_state": {
                    "type": "boolean",
                    "description": "True if the org is state-owned OR a mega-brand. False if it's a viable client.",
                },
                "reason": {
                    "type": "string",
                    "description": "≤120 chars explaining the decision.",
                },
                "category": {
                    "type": "string",
                    "enum": ["state", "mega_brand", "regulated", "viable_small", "viable_medium", "uncertain"],
                },
            },
        },
    },
}


def build_org_brief(org: dict) -> str:
    title = org.get("title") or org.get("seoname") or "—"
    cats = [c.get("name", "?") for c in (org.get("categories") or [])][:5]
    address = org.get("fullAddress") or org.get("address") or "—"
    site = org.get("site") or "—"
    rating = org.get("rating", "—")
    reviews_count = org.get("reviewsCount", 0)
    return (
        f"name: {title}\n"
        f"address: {address}\n"
        f"categories: {', '.join(cats) or '—'}\n"
        f"site: {site}\n"
        f"yandex_rating: {rating} ({reviews_count} reviews)"
    )


async def llm_judge_one(client: AsyncOpenAI, org: dict, *, sem: asyncio.Semaphore) -> dict:
    brief = build_org_brief(org)
    async with sem:
        t0 = time.time()
        try:
            resp = await client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM},
                    {"role": "user", "content": brief},
                ],
                tools=[JUDGE_TOOL],
                tool_choice="auto",
                timeout=LLM_TIMEOUT_S,
            )
        except Exception as e:
            return {"oid": str(org.get("oid")), "title": org.get("title"),
                    "decision": "error", "reason": f"{type(e).__name__}", "elapsed_s": round(time.time()-t0, 1)}

    elapsed = round(time.time() - t0, 1)
    msg = resp.choices[0].message
    tcs = getattr(msg, "tool_calls", None) or []
    if not tcs:
        # fallback: parse from content
        content = (msg.content or "").strip()
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if not m:
            return {"oid": str(org.get("oid")), "title": org.get("title"),
                    "decision": "no_tool_call", "reason": content[:200], "elapsed_s": elapsed}
        try:
            args = json.loads(m.group(0))
        except Exception:
            args = {}
    else:
        try:
            args = json.loads(tcs[0].function.arguments or "{}")
        except Exception:
            args = {}

    too_big = bool(args.get("too_big_or_state", False))
    return {
        "oid": str(org.get("oid")),
        "title": org.get("title"),
        "decision": "drop" if too_big else "keep",
        "category": args.get("category", "uncertain"),
        "reason": str(args.get("reason", ""))[:200],
        "elapsed_s": elapsed,
    }


# --- main -------------------------------------------------------------------

async def main() -> int:
    if not ORGS_PATH.exists():
        print(f"[!] {ORGS_PATH} missing — run 01_scrape_yandex.py first.")
        return 1

    with ORGS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    orgs: list[dict] = data.get("organizations") or []
    print(f"[*] Loaded {len(orgs)} orgs.")

    # Pass 1: regex prefilter
    regex_dropped: list[dict] = []
    regex_survivors: list[dict] = []
    for o in orgs:
        drop, reason = regex_prefilter(o)
        if drop:
            regex_dropped.append({"oid": str(o.get("oid")), "title": o.get("title"),
                                  "decision": "drop", "category": "regex",
                                  "reason": reason})
        else:
            regex_survivors.append(o)
    print(f"[*] Regex prefilter: dropped {len(regex_dropped)}, kept {len(regex_survivors)}.")

    # Pass 2: LLM judge for survivors
    print(f"[*] LLM judging {len(regex_survivors)} orgs with concurrency={CONCURRENCY}...")
    client = AsyncOpenAI(base_url=LLM_BASE, api_key=LLM_KEY,
                        timeout=httpx.Timeout(LLM_TIMEOUT_S, connect=10.0), max_retries=2)
    sem = asyncio.Semaphore(CONCURRENCY)

    started = time.time()
    results: list[dict] = []
    progress_lock = asyncio.Lock()
    done_counter = {"n": 0}

    async def _run(o: dict) -> None:
        r = await llm_judge_one(client, o, sem=sem)
        results.append(r)
        async with progress_lock:
            done_counter["n"] += 1
            if done_counter["n"] % 25 == 0 or done_counter["n"] == len(regex_survivors):
                el = round(time.time() - started, 1)
                rate = done_counter["n"] / max(0.1, el)
                eta = round((len(regex_survivors) - done_counter["n"]) / max(0.001, rate), 0)
                print(f"  [{done_counter['n']:3d}/{len(regex_survivors)}] judged in {el}s ({rate:.2f}/s, ETA {eta}s)")

    await asyncio.gather(*[_run(o) for o in regex_survivors])
    total_elapsed = round(time.time() - started, 1)
    print(f"[+] LLM pass done in {total_elapsed}s.")

    # Aggregate
    decisions_by_oid = {r["oid"]: r for r in results}
    keep: list[dict] = []
    dropped: list[dict] = regex_dropped[:]
    errors: list[dict] = []

    for o in regex_survivors:
        oid = str(o.get("oid"))
        r = decisions_by_oid.get(oid, {"decision": "error", "reason": "no result"})
        if r["decision"] == "keep":
            o["_filter"] = {"decision": "keep", "category": r.get("category"), "reason": r.get("reason")}
            keep.append(o)
        elif r["decision"] == "drop":
            dropped.append({"oid": oid, "title": o.get("title"),
                            "decision": "drop", "category": r.get("category"),
                            "reason": r.get("reason")})
        else:
            errors.append({"oid": oid, "title": o.get("title"), **r})

    # Save
    output = {
        "source": str(ORGS_PATH),
        "total_in": len(orgs),
        "regex_dropped": len(regex_dropped),
        "llm_dropped": sum(1 for r in results if r["decision"] == "drop"),
        "llm_errors": len(errors),
        "kept": len(keep),
        "kept_orgs": keep,
        "dropped_summary": dropped,
        "errors": errors,
        "elapsed_s": total_elapsed,
    }
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print(f"[+] Total in       : {len(orgs)}")
    print(f"[+] Regex dropped  : {len(regex_dropped)}")
    print(f"[+] LLM dropped    : {output['llm_dropped']}")
    print(f"[+] LLM errors     : {len(errors)}")
    print(f"[+] **Kept**       : {len(keep)}")
    print(f"[+] Saved          : {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
