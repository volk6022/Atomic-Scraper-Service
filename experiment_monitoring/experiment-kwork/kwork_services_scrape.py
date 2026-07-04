"""
kwork_services_scrape.py — SUPPLY-side catalog scraper for Kwork market analysis.

Standalone experiment script (does NOT import atomic-scraper `src/`). Collects the
gig catalog (услуги продавцов) for the «Разработка и IT» subcategories, for
competition/price analysis. Endpoint spec: wiki/auto-monitor/kwork-services-endpoint.md.

Two data levels:
  - LIST  : POST /catalog_kworks_filters/<parent>/<leaf>  (page=N) -> 24 gigs/page
            fields: id, gtitle, price, days, queueCount, seller rating/reviews/level.
  - CARD  : GET /<parent>/<id>/<slug>  -> inline `window.stateData` blob
            fields: gdesc (описание), ginst, packages, extras (доп-опции).

httpx-direct, no proxy (QRATOR passes). Proxy is a fallback only, taken from the
existing proxies.txt via load_proxies() (the ONLY external dependency).

Run from repo root:
  uv run python experiment_monitoring/experiment-kwork/kwork_services_scrape.py
  uv run python experiment_monitoring/experiment-kwork/kwork_services_scrape.py --cards 20
  uv run python experiment_monitoring/experiment-kwork/kwork_services_scrape.py --only mashinnoe-obuchenie
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
OUT_DIR = HERE / "samples" / "services"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PROXIES_FILE = HERE.parent.parent / "proxies.txt"  # repo-root proxies.txt (puls RU residential)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

# «Разработка и IT» → «Скрипты, боты и mini apps» (script-programming) leaves —
# the subcategories that map directly onto Ivan's gig catalog. Extend later with
# other parents (website-repair, software, mobile-apps, ...) for the full sweep.
CATEGORIES: list[tuple[str, str]] = [
    ("script-programming", "mashinnoe-obuchenie"),  # Машинное обучение
    ("script-programming", "parsery"),              # Парсеры
    ("script-programming", "ii-agenty"),            # ИИ-агенты
    ("script-programming", "ii-boty"),              # ИИ-боты
    ("script-programming", "chat-boty"),            # Чат-боты
    ("script-programming", "skripty"),              # Скрипты
    ("script-programming", "telegram-mini-apps"),   # Telegram Mini Apps
]

# Remaining «Разработка и IT» (programming) parents — scraped at PARENT level
# (leaf="") for a broad, proxy-economical market map. Slugs from the section nav.
DEV_PARENTS: list[tuple[str, str]] = [
    ("website-repair", ""),        # Доработка и настройка сайта
    ("website-development", ""),   # Создание сайтов
    ("frontend", ""),              # Верстка
    ("software", ""),             # Программы (десктоп/офис/1С/на заказ)
    ("mobile-apps", ""),           # Мобильные приложения
    ("game-dev", ""),              # Игры
]

# «Разработка и IT» parents missed in the first DEV_PARENTS pass.
DEV_EXTRA: list[tuple[str, str]] = [
    ("server-administration", ""),  # Сервера и хостинг
    ("usability-testing", ""),      # Юзабилити, тесты и помощь
]

# «Соцсети и маркетинг» — SMM scraped per-platform (prices/competition differ a
# lot by platform); other parents at their natural leaf/parent level. Slugs from
# the mega-menu JSON (/categories/<parent>/<leaf>).
MARKETING: list[tuple[str, str]] = [
    ("smm", "youtube"), ("smm", "vkontakte"), ("smm", "telegram"),
    ("smm", "max"), ("smm", "odnoklassniki"), ("smm", "yandeks-dzen"),
    ("smm", "tiktok"), ("smm", "vc-ru"), ("smm", "reddit"), ("smm", "drugie"),
    ("context", ""),                              # Google Ads + Яндекс Директ
    ("information-bases", "sbor-dannykh"),        # Сбор данных (parsing-adjacent)
    ("information-bases", "gotovie-bazy"),        # Готовые базы
    ("information-bases", "proverka-chistka-bazy"),  # Проверка/чистка базы
    ("email-marketing", ""),                      # E-mail рассылки
    ("bulletin-boards", "torgovie-ploshchadki"),  # Маркетплейсы
    ("bulletin-boards", "doski-obyavlenii"),      # Доски объявлений
    ("bulletin-boards", "spravochniki-katalogi"),  # Справочники и каталоги
    ("marketing", ""),                            # Маркетинг и PR
]

# The remaining 5 top-level sections — parent-level, for the full market map.
# Ivan-irrelevant (no ML/dev/parsing lane here), so overview granularity only.
DESIGN = ["logo", "presentations-infographics", "illustrations",
          "web-plus-mobile-design", "e-commerce-social-network",
          "interior-exterior-design", "vector-tracing", "graphic-design",
          "packaging", "outdoor-advertising", "imagegeneration"]
WRITING = ["creative-writing", "translations", "typing",
           "business-copywriting", "resumes-and-letters", "textgeneration"]
SEO = ["seo", "links", "integrated-promotion", "optimization", "keywords",
       "audit", "traffic", "analytics"]
AUDIO = ["audio", "music", "editing-audio", "intro", "animation",
         "editing-media", "videogeneration"]
BUSINESS = ["personal-assistant", "financial-consulting", "calls-sales",
            "lawyer-consulting", "sites-for-sale", "recruitment",
            "training-consulting", "engineering"]
OTHER_SECTIONS = [(p, "") for p in DESIGN + WRITING + SEO + AUDIO + BUSINESS]

# Named sets selectable via --set.
CATSETS: dict[str, list[tuple[str, str]]] = {
    "it-scripts": CATEGORIES,   # already scraped -> samples/services
    "it-rest": DEV_PARENTS,     # already scraped -> samples/services-dev
    "it-extra": DEV_EXTRA,      # -> samples/services-dev (append)
    "marketing": MARKETING,     # -> samples/services-mkt
    "other": OTHER_SECTIONS,    # design/writing/seo/audio/business -> samples/services-other
}

LIST_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://kwork.ru",
}

CARD_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

THROTTLE_SEC = 2.0   # polite base pause between requests (+ jitter)
BLOCK_BACKOFF = 25.0  # sleep after a soft-block (not_access.php) before retry


class BlockedError(Exception):
    """kwork soft-block: redirect to not_access.php / 403."""


def _throttle() -> None:
    time.sleep(THROTTLE_SEC + random.uniform(0, 1.0))


# --------------------------------------------------------------------------- #
# proxies.txt — the only external dependency (fallback only)
# --------------------------------------------------------------------------- #
def load_proxies() -> list[str]:
    line_re = re.compile(
        r"^https?://(?P<user>[^:@]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
    )
    proxies: list[str] = []
    if not PROXIES_FILE.exists():
        return proxies
    for raw in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = line_re.match(line)
        if not m:
            continue
        u = urllib.parse.quote(m.group("user"), safe="")
        p = urllib.parse.quote(m.group("password"), safe="")
        proxies.append(f"http://{u}:{p}@{m.group('host')}:{m.group('port')}")
    return proxies


_PROXIES = load_proxies()
if not _PROXIES:
    print("WARNING: no proxies loaded — sustained catalog paging WILL get IP-banned "
          "by QRATOR. Put puls RU residential proxies in repo-root proxies.txt.")


def _is_block(r: httpx.Response) -> bool:
    return "not_access" in str(r.url) or r.status_code in (403, 429)


def _request(method: str, url: str, *, tries: int = 4, **kw) -> httpx.Response:
    """Issue a request through a FRESH RANDOM proxy each attempt.

    kwork/QRATOR IP-bans a client after ~8 rapid catalog requests, so we rotate a
    fresh RU residential IP per request (each IP does ~1 call → never trips the
    volume ban). Pagination stays correct because `excludeIds` is passed explicitly
    (stateless — no shared cookies needed). Retries on soft-block/error.
    """
    last: Exception | None = None
    for _ in range(tries):
        proxy = random.choice(_PROXIES) if _PROXIES else None
        try:
            with httpx.Client(proxy=proxy, follow_redirects=True, timeout=35.0) as c:
                r = c.request(method, url, **kw)
            if _is_block(r):
                last = BlockedError(f"{method} {url} -> {r.url} [{r.status_code}]")
                continue
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            last = exc
            continue
    raise last if last else RuntimeError("request failed")


# --------------------------------------------------------------------------- #
# LIST level
# --------------------------------------------------------------------------- #
def fetch_catalog_page(parent: str, leaf: str, page: int, exclude_ids: str = "") -> dict:
    """One page of the catalog via the persistent session.

    `exclude_ids` (csv of already-seen ids) is REQUIRED for real pagination —
    the endpoint re-returns overlapping sets otherwise (mirrors the site client).
    Raises BlockedError on soft-block so the caller can back off.
    """
    # leaf="" → parent-level catalog (single-segment path). The endpoint accepts
    # /catalog_kworks_filters/<parent> and returns the whole parent's gigs.
    path = f"{parent}/{leaf}" if leaf else parent
    url = f"https://kwork.ru/catalog_kworks_filters/{path}"
    headers = dict(LIST_HEADERS)
    headers["Referer"] = f"https://kwork.ru/categories/{path}"
    data = {"page": str(page), "onePage": "1"}
    if exclude_ids:
        data["excludeIds"] = exclude_ids
    r = _request("POST", url, headers=headers, data=data)
    return r.json()


def gigs_from_response(payload: dict) -> tuple[list[dict], dict]:
    kw = payload.get("data", {}).get("stateData", {}).get("viewData", {}).get("kworks", {})
    posts = kw.get("posts", {})
    gigs = posts.get("data", []) if isinstance(posts, dict) else []
    meta = {
        "currentpage": kw.get("currentpage"),
        "total": kw.get("total"),
        "total_found": kw.get("total_found"),
        "items_per_page": kw.get("items_per_page"),
    }
    return gigs, meta


LIST_FIELDS = (
    "id", "url", "gtitle", "price", "days", "queueCount",
    "userId", "userName", "convertedUserRating", "userRating",
    "userRatingCount", "sellerLevel", "rating", "topBadge",
    "baseVolume", "baseVolumeShortName",
)


def slim_gig(g: dict, parent: str, leaf: str) -> dict:
    out = {k: g.get(k) for k in LIST_FIELDS}
    out["parent"] = parent
    out["leaf"] = leaf
    return out


def _fetch_page_safe(parent: str, leaf: str, page: int, exclude: str) -> dict | None:
    """Fetch a page via proxy rotation. Returns None if it ultimately failed."""
    try:
        return fetch_catalog_page(parent, leaf, page, exclude_ids=exclude)
    except Exception as exc:  # noqa: BLE001
        print(f"    page {page} failed after retries: {exc}")
        return None


def scrape_category(parent: str, leaf: str, max_pages: int = 8) -> list[dict]:
    print(f"\n[LIST] {parent}/{leaf}")
    first = _fetch_page_safe(parent, leaf, 1, "")
    if not first:
        return []
    gigs, meta = gigs_from_response(first)
    total = meta.get("total") or 0
    per = meta.get("items_per_page") or 24
    pages = min(max_pages, -(-total // per) if total else 1)
    print(f"  total={total}  per_page={per}  scraping up to {pages} pages")
    all_gigs = [slim_gig(g, parent, leaf) for g in gigs]
    seen = {g["id"] for g in all_gigs}
    empty_streak = 0
    for page in range(2, pages + 1):
        _throttle()
        exclude = ",".join(str(i) for i in seen)
        payload = _fetch_page_safe(parent, leaf, page, exclude)
        if payload is None:
            break
        page_gigs, _ = gigs_from_response(payload)
        new = [slim_gig(g, parent, leaf) for g in page_gigs if g.get("id") not in seen]
        seen.update(g["id"] for g in new)
        all_gigs.extend(new)
        print(f"  page {page}: +{len(new)} (total {len(all_gigs)})")
        if not new:
            empty_streak += 1
            if empty_streak >= 2:  # exhausted / dedup wall
                break
        else:
            empty_streak = 0
    return all_gigs


# --------------------------------------------------------------------------- #
# CARD level
# --------------------------------------------------------------------------- #
def _extract_js_object(text: str, anchor: str) -> dict | None:
    """Extract a balanced {...} JS object literal following `anchor` (e.g.
    'window.stateData ='), string/escape aware."""
    i = text.find(anchor)
    if i == -1:
        return None
    i = text.find("{", i)
    if i == -1:
        return None
    depth, in_str, esc, quote = 0, False, False, ""
    start = i
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
        else:
            if ch in ('"', "'"):
                in_str, quote = True, ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    blob = text[start : j + 1]
                    try:
                        return json.loads(blob)
                    except json.JSONDecodeError:
                        return None
    return None


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()


def fetch_card(url_path: str) -> dict | None:
    url = "https://kwork.ru" + url_path if url_path.startswith("/") else url_path
    try:
            r = _request("GET", url, headers=CARD_HEADERS)
            sd = _extract_js_object(r.text, "window.stateData")
            if not sd:
                return None
            k = sd.get("kwork", {}) or {}
            # served HTML is flat (sd.extras); browser rehydrates to sd.viewData.extras
            extras = sd.get("extras") or (sd.get("viewData", {}) or {}).get("extras") or []
            return {
                "id": k.get("id"),
                "url": url_path,
                "gtitle": k.get("gtitle"),
                "price": k.get("price"),
                "displayedPrice": k.get("displayedPrice"),
                "days": k.get("days"),
                "queueCount": k.get("queueCount"),
                "bookmarkCount": k.get("bookmarkCount"),
                "categoryTitle": k.get("categoryTitle"),
                "gdesc_text": html_to_text(k.get("gdesc") or k.get("gdesc_source")),
                "ginst_text": html_to_text(k.get("ginst")),
                "packages": [
                    {"title": p.get("title") or p.get("name"), "price": p.get("price")}
                    for p in (k.get("packages") or [])
                    if isinstance(p, dict)
                ],
                "extras": [
                    {
                        "title": e.get("title") or e.get("name"),
                        "price": e.get("price"),
                        "duration": e.get("duration"),
                        "description": html_to_text(e.get("description")),
                    }
                    for e in extras
                    if isinstance(e, dict)
                ],
            }
    except Exception as exc:  # noqa: BLE001
        print(f"    card fail {url_path}: {exc}")
        return None


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", type=int, default=15,
                    help="cards to fetch per category (0 = skip cards)")
    ap.add_argument("--max-pages", type=int, default=8,
                    help="max catalog pages per category (24 gigs/page)")
    ap.add_argument("--only", type=str, default=None, help="single leaf/parent slug")
    ap.add_argument("--set", dest="catset", default="it-scripts", choices=list(CATSETS),
                    help="which named category set to scrape")
    ap.add_argument("--outdir", type=str, default=None,
                    help="output subfolder under samples/ (default: services)")
    args = ap.parse_args()

    out_dir = Path(args.outdir) if args.outdir and Path(args.outdir).is_absolute() else \
        (HERE / "samples" / (args.outdir or "services"))
    out_dir.mkdir(parents=True, exist_ok=True)

    source = CATSETS[args.catset]
    cats = [(p, l) for (p, l) in source if not args.only or (l or p) == args.only]
    combined: list[dict] = []
    summary: list[dict] = []

    for parent, leaf in cats:
        label = leaf or parent  # parent-level units are labelled by parent slug
        gigs = scrape_category(parent, leaf, max_pages=args.max_pages)
        (out_dir / f"list_{label}.jsonl").write_text(
            "\n".join(json.dumps(g, ensure_ascii=False) for g in gigs), encoding="utf-8"
        )
        combined.extend(gigs)

        cards: list[dict] = []
        if args.cards:
            # sample by seller trust: highest userRatingCount first (the real players)
            ranked = sorted(gigs, key=lambda g: int(g.get("userRatingCount") or 0), reverse=True)
            for g in ranked[: args.cards]:
                _throttle()
                card = fetch_card(g["url"])
                if card:
                    card["leaf"] = label
                    cards.append(card)
            (out_dir / f"cards_{label}.jsonl").write_text(
                "\n".join(json.dumps(c, ensure_ascii=False) for c in cards), encoding="utf-8"
            )

        prices = sorted(int(g["price"]) for g in gigs if g.get("price"))
        summary.append({
            "leaf": label,
            "gig_count": len(gigs),
            "price_min": prices[0] if prices else None,
            "price_median": prices[len(prices) // 2] if prices else None,
            "price_max": prices[-1] if prices else None,
            "cards_fetched": len(cards),
        })
        print(f"  -> {len(gigs)} gigs, {len(cards)} cards saved")

    (out_dir / "all_gigs.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in combined), encoding="utf-8"
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== SUMMARY ===")
    for s in summary:
        print(f"  {s['leaf']:22s} gigs={s['gig_count']:4d}  "
              f"price min/med/max = {s['price_min']}/{s['price_median']}/{s['price_max']}  "
              f"cards={s['cards_fetched']}")
    print(f"\nSaved to {out_dir}")


if __name__ == "__main__":
    main()
