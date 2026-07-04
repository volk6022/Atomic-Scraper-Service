"""
kwork_profiles_scrape.py — scrape SELLER PROFILES of the top players, to benchmark
Ivan's own profile against successful competitors.

Reuses networking helpers from kwork_services_scrape.py (same folder). Two sources
per seller:
  - GET  /user/<name>          -> profile meta from window.stateData
        (profession, description/bio, skills, seller level, reviews, tenure).
  - POST /user_kworks/<name>   -> full gig portfolio (JSON, paginated offset/limit)
        {"username":..,"offset":0,"limit":24} -> data.total + data.data[gigs].

Seller candidates are taken from the ALREADY-scraped catalog (samples/services* —
"те кворки, которые уже парсились"), ranked by userRatingCount, deduped by userId.

Run from repo root:
  uv run python experiment_monitoring/experiment-kwork/kwork_profiles_scrape.py
  uv run python experiment_monitoring/experiment-kwork/kwork_profiles_scrape.py --top 15 --from services
"""
from __future__ import annotations

import argparse
import importlib.util as ilu
import json
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "samples" / "profiles"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# reuse the services scraper's proven networking / parsing helpers.
# NOTE: importing kws installs the win32 UTF-8 stdout wrapper — don't wrap here too
# (double-wrapping the same buffer closes it on GC).
_spec = ilu.spec_from_file_location("kws", HERE / "kwork_services_scrape.py")
kws = ilu.module_from_spec(_spec)
_spec.loader.exec_module(kws)


def top_sellers(sample_dirs: list[str], top: int) -> list[dict]:
    """Rank sellers across already-scraped catalog gigs by review count."""
    sellers: dict[int, dict] = {}
    for d in sample_dirs:
        fp = HERE / "samples" / d / "all_gigs.jsonl"
        if not fp.exists():
            # fall back to concatenating list_*.jsonl
            files = list((HERE / "samples" / d).glob("list_*.jsonl"))
        else:
            files = [fp]
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                g = json.loads(line)
                uid = g.get("userId")
                if not uid:
                    continue
                s = sellers.setdefault(uid, {
                    "userId": uid, "userName": g.get("userName"),
                    "reviews": int(g.get("userRatingCount") or 0),
                    "sellerLevel": g.get("sellerLevel"),
                    "sample_categories": set(),
                })
                s["sample_categories"].add(g.get("leaf") or g.get("parent"))
    ranked = sorted(sellers.values(), key=lambda s: s["reviews"], reverse=True)[:top]
    for s in ranked:
        s["sample_categories"] = sorted(x for x in s["sample_categories"] if x)
    return ranked


def fetch_profile_meta(name: str) -> dict | None:
    try:
        r = kws._request("GET", f"https://kwork.ru/user/{name}", headers=kws.CARD_HEADERS)
    except Exception as exc:  # noqa: BLE001
        print(f"  meta fail {name}: {exc}")
        return None
    sd = kws._extract_js_object(r.text, "window.stateData")
    if not sd:
        return None
    return {
        "userName": sd.get("userProfileName"),
        "fullName": sd.get("userProfileFullName"),
        "profession": sd.get("userProfileProfession"),
        "description": kws.html_to_text(sd.get("userProfileDescription")),
        "addTime": sd.get("userProfileAddTime"),
        "rating": sd.get("userRating"),
        "sellerLevel": sd.get("userSellerLevel"),
        "totalReviews": sd.get("totalReviewsCount"),
        "totalKworks": sd.get("totalKworks"),
        "skills": [s.get("name") for s in (sd.get("userSkills") or []) if isinstance(s, dict)],
        "location": sd.get("userLocation"),
    }


def fetch_user_gigs(name: str, page_limit: int = 24) -> list[dict]:
    gigs: list[dict] = []
    offset = 0
    headers = dict(kws.LIST_HEADERS)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "application/json, text/plain, */*"
    headers["Referer"] = f"https://kwork.ru/user/{name}"
    while True:
        try:
            r = kws._request(
                "POST", f"https://kwork.ru/user_kworks/{name}", headers=headers,
                json={"username": name, "offset": offset, "limit": page_limit},
            )
            payload = r.json()
        except Exception as exc:  # noqa: BLE001
            print(f"  gigs fail {name} @offset {offset}: {exc}")
            break
        data = (payload.get("data") or {})
        total = data.get("total") or 0
        batch = data.get("data") or []
        for g in batch:
            gigs.append({
                "id": g.get("id"), "url": g.get("url"), "gtitle": g.get("gtitle"),
                "price": g.get("price"), "days": g.get("days"),
                "categoryName": g.get("categoryName"), "categoryId": g.get("categoryId"),
                "baseVolume": g.get("baseVolume"), "baseVolumeShortName": g.get("baseVolumeShortName"),
                "conversion": g.get("conversion"), "queueCount": g.get("queueCount"),
            })
        offset += len(batch)
        if not batch or offset >= total:
            break
        kws._throttle()
    return gigs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15, help="how many top sellers")
    ap.add_argument("--from", dest="dirs", default="services",
                    help="comma-sep sample dirs to pick sellers from (Ivan's lane = services)")
    args = ap.parse_args()

    dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
    sellers = top_sellers(dirs, args.top)
    print(f"Selected {len(sellers)} top sellers from {dirs}:\n")

    profiles: list[dict] = []
    for s in sellers:
        name = s["userName"]
        print(f"[{name}] reviews={s['reviews']} lvl={s['sellerLevel']} "
              f"seen_in={s['sample_categories']}")
        kws._throttle()
        meta = fetch_profile_meta(name) or {}
        kws._throttle()
        gigs = fetch_user_gigs(name)
        prof = {**s, "meta": meta, "gigs": gigs, "gig_count": len(gigs)}
        profiles.append(prof)
        (OUT_DIR / f"profile_{name}.json").write_text(
            json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  -> {meta.get('profession')!r} | {len(gigs)} gigs | "
              f"{meta.get('totalReviews')} reviews since {meta.get('addTime')}")

    (OUT_DIR / "profiles.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in profiles), encoding="utf-8")
    print(f"\nSaved {len(profiles)} profiles to {OUT_DIR}")


if __name__ == "__main__":
    main()
