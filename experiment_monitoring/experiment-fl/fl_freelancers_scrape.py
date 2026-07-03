"""
fl_freelancers_scrape.py — SUPPLY-side (competition) scraper for fl.ru market analysis.

Standalone experiment script (does NOT import atomic-scraper `src/`). fl.ru is a
project-bidding marketplace (no fixed-gig catalog like Kwork), so the supply /
competition analog is the FREELANCER CATALOG: who competes in a niche, their
maturity (reviews, deals, portfolio, experience), PRO/verified status, and — from
a sampled profile — the declared rate. Endpoint spec: wiki/auto-monitor/fl-services-endpoint.md.

Two data levels:
  - LIST    : GET /freelancers/<profession>/page-<N>/  (SSR-HTML, 40 freelancers/page)
              per row: uid, login, name, spec (group/slug/text), experience,
              portfolio works, reviews, deals, is_pro, is_verified.
  - PROFILE : GET /users/<login>/  -> "Стоимость часа работы — N ₽" (hourly),
              "Стоимость месяца работы — N ₽" (monthly). ₽ = HTML entity &#8381;.

httpx-direct, NO proxy (DDoS-Guard is passive per auto-research-fl.md — plain
httpx returns full SSR-HTML). Proxy is a fallback only, from repo-root proxies.txt.

Run from repo root:
  uv run python experiment_monitoring/experiment-fl/fl_freelancers_scrape.py
  uv run python experiment_monitoring/experiment-fl/fl_freelancers_scrape.py --set it --max-pages 5 --profiles 12
  uv run python experiment_monitoring/experiment-fl/fl_freelancers_scrape.py --only ai-iskusstvenniy-intellekt
"""
from __future__ import annotations

import argparse
import html as htmllib
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
PROXIES_FILE = HERE.parent.parent / "proxies.txt"  # repo-root (fallback only)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

# fl.ru freelancer professions (flat single-segment slugs under /freelancers/).
# Ivan's lane: AI/ML, neural nets, chatbots, business automation, parsing/data,
# plus broad programming + fullstack as baselines.
IT_PROFESSIONS: list[str] = [
    "ai-iskusstvenniy-intellekt",             # AI — искусственный интеллект
    "neironnye-seti",                          # Нейронные сети
    "razrabotka-chat-botov",                   # Разработка чат-ботов
    "avtomatizaciya-biznesa",                  # Автоматизация бизнеса
    "specialist-sbor-obrabotka-informacii",    # Сбор и обработка информации (парсинг)
    "programmirovanie",                        # Программирование (broad baseline)
    "fullstack",                               # Fullstack
]

# Named sets selectable via --set.
CATSETS: dict[str, list[str]] = {
    "it": IT_PROFESSIONS,
}

THROTTLE_SEC = 1.2   # polite base pause between requests (+ jitter); httpx-direct, cheap


class BlockedError(Exception):
    """fl.ru block: DDoS-Guard JS challenge / 403 / 429."""


def _throttle() -> None:
    time.sleep(THROTTLE_SEC + random.uniform(0, 0.8))


# --------------------------------------------------------------------------- #
# proxies.txt — fallback only (fl.ru does not need a proxy)
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


def _is_block(r: httpx.Response) -> bool:
    if r.status_code in (403, 429, 503):
        return True
    # DDoS-Guard JS challenge page markers
    low = r.text[:2000].lower()
    return "ddos-guard" in low and "challenge" in low


def _request(method: str, url: str, *, tries: int = 4, use_proxy: bool = False, **kw) -> httpx.Response:
    """Issue a request. fl.ru works httpx-direct (no proxy) — use_proxy is a fallback
    for future anti-bot escalation. Retries on soft-block/error."""
    last: Exception | None = None
    for attempt in range(tries):
        proxy = random.choice(_PROXIES) if (use_proxy and _PROXIES) else None
        try:
            with httpx.Client(proxy=proxy, follow_redirects=True, timeout=35.0) as c:
                r = c.request(method, url, **kw)
            if _is_block(r):
                last = BlockedError(f"{method} {url} [{r.status_code}]")
                time.sleep(5.0 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2.0)
            continue
    raise last if last else RuntimeError("request failed")


# --------------------------------------------------------------------------- #
# LIST level — freelancer catalog rows
# --------------------------------------------------------------------------- #
_ROW_SPLIT = 'data-id="qa-content-tr"'


def _clean(s: str | None) -> str:
    if not s:
        return ""
    return htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def parse_rows(html: str, profession: str) -> list[dict]:
    """Parse freelancer rows from a catalog page. Each row starts at a
    `data-id="qa-content-tr"` marker; fields are taken as the FIRST match within
    the row's slice (fields appear once, near the row start).

    fl.ru shows TWO row types to anonymous visitors (a pay-to-be-visible model):
      - PRO rows (`cf-line is-pro`): full — named, /users/ profile link, rate reachable.
      - non-PRO rows (`cf-line limited-card`): anonymized ("Фрилансер", no profile
        link), but uid/reviews/deals/specialization/experience are still present.
    We keep both (maturity + density need all of them) and flag `is_pro`/`anonymized`.
    """
    parts = html.split(_ROW_SPLIT)
    rows: list[dict] = []
    for chunk in parts[1:]:
        head = chunk[:200]
        if "cf-line" not in head:
            continue  # header / non-data slice
        # uid + maturity from data-ga el string "<uid>,<N> deal,<N> reviews,..."
        mat = re.search(r'(\d+),(\d+)\s*deal,(\d+)\s*reviews', chunk)
        if mat:
            uid, deals, reviews = mat.group(1), int(mat.group(2)), int(mat.group(3))
        else:
            um = re.search(r"el:\s*['\"](\d+)['\"]", chunk) or re.search(r'\buid(\d+)\b', chunk)
            uid, deals, reviews = (um.group(1) if um else None), None, None
        if not uid:
            continue  # not a real freelancer row
        login_m = re.search(r'/users/([A-Za-z0-9_.\-]+)/', chunk)
        login = login_m.group(1) if login_m else None
        is_pro = "limited-card" not in head  # limited-card == non-PRO anonymized
        name_m = re.search(r'cf-title-card-new[^>]*>([^<]+)<', chunk)
        name = _clean(name_m.group(1)) if name_m else None
        anonymized = (login is None) or (name == "Фрилансер")
        if anonymized:
            login = login or None
            name = None
        # specialization cell (data-id="qa-content-tr-td-cf-spec"). On GROUP pages it
        # is an <a> linking a sub-specialization; on LEAF pages a plain <span> with
        # the category text. Handle both; strip nested tags robustly.
        spec_slug = spec_text = None
        sp = re.search(r'data-id="qa-content-tr-td-cf-spec"[^>]*>(.*?)</(?:a|span)>', chunk, re.S)
        if sp:
            spec_text = _clean(sp.group(1)) or None
        sl = re.search(
            r'href="/freelancers/([a-z0-9\-]+)/"[^>]*data-id="qa-content-tr-td-cf-spec"',
            chunk, re.S)
        spec_slug = sl.group(1) if sl else None
        grp_m = re.search(r'>\s*([А-ЯЁ][А-Яа-яёЁ ,/\-]{2,40}):\s*<a', chunk)
        spec_group = _clean(grp_m.group(1)) if grp_m else None
        exp_m = re.search(r'Опыт:\s*(\d+)\s*(?:лет|год|года)', chunk)
        experience = int(exp_m.group(1)) if exp_m else None
        pf_m = re.search(r'>(\d+)\s*работ', chunk)
        portfolio = int(pf_m.group(1)) if pf_m else None
        is_verified = ("#reward" in chunk) or ("Верифицированный" in chunk)
        rows.append({
            "uid": uid, "login": login, "name": name, "anonymized": anonymized,
            "spec_group": spec_group, "spec_slug": spec_slug, "spec_text": spec_text,
            "experience_years": experience, "portfolio_works": portfolio,
            "reviews": reviews, "deals": deals,
            "is_pro": is_pro, "is_verified": is_verified,
            "profession": profession,
        })
    return rows


def catalog_pagination(html: str, profession: str) -> tuple[int, bool]:
    """(max_visible_page, has_more_dots) — density estimator."""
    pages = [int(m) for m in re.findall(rf'/{re.escape(profession)}/page-(\d+)/', html)]
    return (max(pages) if pages else 1, "pagination-dots" in html)


def scrape_profession(profession: str, max_pages: int) -> tuple[list[dict], dict]:
    url1 = f"https://www.fl.ru/freelancers/{profession}/"
    print(f"\n[LIST] {profession}")
    try:
        r = _request("GET", url1, headers=HEADERS)
    except Exception as exc:  # noqa: BLE001
        print(f"  page 1 failed: {exc}")
        return [], {"profession": profession, "error": str(exc)}
    max_page, dots = catalog_pagination(r.text, profession)
    est_pages = max_page + (1 if dots else 0)  # dots → at least one more
    rows = parse_rows(r.text, profession)
    seen = {row["uid"] for row in rows}
    pages_to_get = min(max_pages, est_pages)
    n_pro = sum(1 for x in rows if x["is_pro"])
    print(f"  visible_max_page={max_page} dots={dots} est_pages≈{est_pages} "
          f"scraping {pages_to_get} pages; page1: {len(rows)} rows ({n_pro} PRO)")
    for p in range(2, pages_to_get + 1):
        _throttle()
        url = f"https://www.fl.ru/freelancers/{profession}/page-{p}/"
        try:
            rp = _request("GET", url, headers=HEADERS)
        except Exception as exc:  # noqa: BLE001
            print(f"  page {p} failed: {exc}")
            break
        new = [x for x in parse_rows(rp.text, profession) if x["uid"] not in seen]
        seen.update(x["uid"] for x in new)
        rows.extend(new)
        print(f"  page {p}: +{len(new)} (total {len(rows)})")
        if not new:
            break
    meta = {
        "profession": profession,
        "visible_max_page": max_page,
        "has_more": dots,
        "est_total_pages": est_pages,
        "est_total_freelancers": est_pages * 40,
        "scraped": len(rows),
        "pro_scraped": sum(1 for x in rows if x["is_pro"]),
    }
    return rows, meta


# --------------------------------------------------------------------------- #
# PROFILE level — declared rate (sampled)
# --------------------------------------------------------------------------- #
def _rub(after: str) -> int | None:
    m = re.search(r'([\d\s]+)(?:&#8381;|₽)', after)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    return int(digits) if digits else None


def fetch_profile_rate(login: str) -> dict | None:
    url = f"https://www.fl.ru/users/{login}/"
    try:
        r = _request("GET", url, headers=HEADERS)
    except Exception as exc:  # noqa: BLE001
        print(f"    profile fail {login}: {exc}")
        return None
    html = r.text
    hourly = monthly = None
    i = html.find("Стоимость часа работы")
    if i != -1:
        hourly = _rub(html[i:i + 120])
    j = html.find("Стоимость месяца работы")
    if j != -1:
        monthly = _rub(html[j:j + 120])
    return {"login": login, "hourly_rate": hourly, "monthly_rate": monthly}


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="catset", default="it", choices=list(CATSETS))
    ap.add_argument("--only", type=str, default=None, help="single profession slug")
    ap.add_argument("--max-pages", type=int, default=5, help="catalog pages/profession (40/page)")
    ap.add_argument("--profiles", type=int, default=12,
                    help="profiles to sample per profession for rate (0 = skip)")
    ap.add_argument("--outdir", type=str, default="freelancers")
    args = ap.parse_args()

    out_dir = HERE / "samples" / args.outdir
    out_dir.mkdir(parents=True, exist_ok=True)

    profs = [p for p in CATSETS[args.catset] if not args.only or p == args.only]
    combined: list[dict] = []
    summary: list[dict] = []

    for prof in profs:
        rows, meta = scrape_profession(prof, args.max_pages)
        (out_dir / f"list_{prof}.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in rows), encoding="utf-8")
        combined.extend(rows)

        # sample profiles for rate: top by reviews (the visible players)
        rates: list[dict] = []
        if args.profiles:
            # only PRO/named rows have a reachable profile (anonymized rows have no login)
            linkable = [x for x in rows if x.get("login")]
            ranked = sorted(linkable, key=lambda x: int(x.get("reviews") or 0), reverse=True)
            for x in ranked[: args.profiles]:
                _throttle()
                pr = fetch_profile_rate(x["login"])
                if pr:
                    pr["reviews"] = x.get("reviews")
                    pr["profession"] = prof
                    rates.append(pr)
            (out_dir / f"rates_{prof}.jsonl").write_text(
                "\n".join(json.dumps(x, ensure_ascii=False) for x in rates), encoding="utf-8")

        hourly = sorted(x["hourly_rate"] for x in rates if x.get("hourly_rate"))
        meta["rates_sampled"] = len(rates)
        meta["hourly_median"] = hourly[len(hourly) // 2] if hourly else None
        summary.append(meta)
        print(f"  -> {len(rows)} freelancers, {len(rates)} rates "
              f"(hourly median {meta['hourly_median']})")

    (out_dir / "all_freelancers.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in combined), encoding="utf-8")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    for s in summary:
        print(f"  {s['profession']:38s} scraped={s.get('scraped',0):4d} "
              f"est_total≈{s.get('est_total_freelancers','?'):>5} "
              f"hourly_med={s.get('hourly_median')}")
    print(f"\nSaved to {out_dir}")


if __name__ == "__main__":
    main()
