"""Эксперимент 9 (ЖИВОЙ): что даёт КАРТОЧКА организации сверх выдачи поиска.

Гипотеза (наблюдение пользователя): страница орг /maps/org/{seoname}/{oid}/ при
«клике на иконку» отдаёт больше полей, чем item из выдачи поиска.

Сравниваем в лоб для одних и тех же орг:
  S = raw-объект из поиска (?ll=… + query=название)
  C = raw-объект из карточки /maps/org/{seoname}/{oid}/
Печатаем: C−S (поля только в карточке), размеры «богатых» полей (описание, фичи,
фото, меню/товары, ссылки, телефоны).
"""

from __future__ import annotations

import json
import re
import time
import random
from pathlib import Path
from urllib.parse import quote

import httpx

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "results"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "text/html", "Accept-Language": "ru-RU,ru;q=0.9",
     "Accept-Encoding": "gzip, deflate, br"}


def proxies():
    return [l.strip() for l in (REPO / "proxies.txt").read_text().splitlines()
            if l.strip().startswith("http://")]


def get(url):
    for _ in range(6):
        try:
            with httpx.Client(proxy=random.choice(proxies()), headers=H, timeout=30,
                              follow_redirects=True) as c:
                return c.get(url)
        except Exception:
            time.sleep(1)
    return None


def big_blob(html):
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S):
        t = m.group(1).strip()
        if len(t) < 20_000:
            continue
        try:
            return json.loads(t)
        except Exception:
            try:
                return json.loads(t[t.find("{"):])
            except Exception:
                continue
    return None


def search_items(blob):
    try:
        return blob["stack"][0]["results"]["items"]
    except Exception:
        return []


def fieldsize(v):
    """Грубая «насыщенность» поля."""
    if v is None:
        return 0
    if isinstance(v, (list, dict, str)):
        return len(v)
    return 1


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.load((REPO / "yandex_enrichment_experiment" / "data" /
                      "organizations.json").open(encoding="utf-8"))
    # пара орг с координатами и seoname
    picks = []
    for o in data["organizations"]:
        if o.get("seoname") and o.get("coordinates"):
            picks.append(o)
        if len(picks) >= 2:
            break

    report = []
    for o in picks:
        oid, seo = o["oid"], o["seoname"]
        lat, lon = o["coordinates"]["lat"], o["coordinates"]["lon"]
        title = o["title"]
        rec = {"oid": oid, "seoname": seo, "title": title}

        # --- поиск по названию рядом с орг ---
        surl = (f"https://yandex.ru/maps/2/saint-petersburg/search/"
                f"{quote(title, safe='')}/?ll={lon},{lat}&z=17")
        rs = get(surl)
        sitem = {}
        if rs:
            for it in search_items(big_blob(rs.text) or {}):
                if str(it.get("id") or it.get("oid") or "") == str(oid):
                    sitem = it
                    break
            rec["search_wire_kb"] = round(rs.num_bytes_downloaded / 1024, 1)
        # --- карточка орг ---
        curl = f"https://yandex.ru/maps/org/{seo}/{oid}/"
        rc = get(curl)
        citem = {}
        if rc:
            items = search_items(big_blob(rc.text) or {})
            citem = items[0] if items else {}
            rec["card_wire_kb"] = round(rc.num_bytes_downloaded / 1024, 1)

        sk, ck = set(sitem.keys()), set(citem.keys())
        rec["search_keys_n"] = len(sk)
        rec["card_keys_n"] = len(ck)
        rec["only_in_card"] = sorted(ck - sk)
        rec["only_in_search"] = sorted(sk - ck)
        # насыщенность общих + карточных полей
        rich = {}
        for k in sorted(ck):
            sv, cv = fieldsize(sitem.get(k)), fieldsize(citem.get(k))
            if cv > sv:  # карточка богаче по этому полю
                rich[k] = {"search": sv, "card": cv}
        rec["card_richer_fields"] = rich
        report.append(rec)

        rich_str = ", ".join(f"{k}({v['search']}->{v['card']})" for k, v in rich.items())
        print(f"\n=== {title[:40]} ({seo}) ===")
        print(f"  поиск: {len(sk)} полей ({rec.get('search_wire_kb')}KB)  |  "
              f"карточка: {len(ck)} полей ({rec.get('card_wire_kb')}KB)")
        print(f"  ТОЛЬКО в карточке ({len(rec['only_in_card'])}): {rec['only_in_card']}")
        print(f"  карточка богаче по полям: {rich_str}")
        time.sleep(2)

    (OUT / "09_org_card.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[+] {OUT / '09_org_card.json'}")


if __name__ == "__main__":
    main()
