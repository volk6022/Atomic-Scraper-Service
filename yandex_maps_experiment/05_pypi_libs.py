"""Approach 5 — survey of public PyPI libraries (introspection only).

Both libraries are imported and their surface inspected. Live invocation is
**skipped** because:

  * `ymrp` (Yet another Yandex Maps Reviews Parser) hard-codes `headless=False`
    and has no proxy/UA/stealth knobs — it pops a real Chrome window on the
    host, which is impractical on a headless server and unstable on Windows.
  * `yandex-maps-reviews-parser` (arsenyvolodko, GitHub) hard-codes
    `YANDEX_MAPS_API_TOKEN = ""` and uses the **official paid Geosearch API**
    for org-name → org-id lookup. With no key it returns 400. The reviews
    pathway then opens a visible Selenium-Chrome session (same problem as
    YMRP) and only extracts `(rate, text)` per review.

Verdict: both are dominated by Approach 4 (Playwright + XHR intercept) which
   * runs headless,
   * routes through our RU residential proxy,
   * yields 65+ fields per organisation including phones, coordinates, photos,
     hours, services, INN — and reviews via fetchReviews replay (Approach 6).
"""
from __future__ import annotations

import inspect
import json
import time
from typing import Any

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import ExperimentResult, log_line, utf8_stdout

NAME = "05_pypi_libs"


def survey():
    findings: dict[str, dict[str, Any]] = {}

    # --- ymrp -----------------------------------------------------------------
    try:
        import ymrp.parser as ymp
        cls = ymp.YandexMapReviewsParser
        meth = [m for m in dir(cls) if not m.startswith("_") and callable(getattr(cls, m))]
        src = inspect.getsource(cls.get_reviews_html_content)
        findings["ymrp"] = {
            "installed": True,
            "version": getattr(__import__("ymrp"), "__version__", "0.6.0 (PyPI)"),
            "engine": "Playwright (sync)",
            "headless": "False — hard-coded",
            "proxy_support": False,
            "stealth": False,
            "fields_per_review": ["rating", "text", "author_handle", "date (partial)"],
            "useful_classes": [
                "YandexMapParser", "YandexMapReviewsParser",
                "YandexMapProductsAndServicesParser",
            ],
            "method_excerpt": src[:600],
            "limits": [
                "headless=False — opens a visible Chrome window",
                "no proxy / no UA override",
                "scrolls full page until no new reviews — slow",
                "no built-in pagination by date",
            ],
        }
    except Exception as e:
        findings["ymrp"] = {"installed": False, "error": repr(e)}

    # --- yandex-maps-reviews-parser (arsenyvolodko) ---------------------------
    try:
        from yandex_maps_reviews_parser import YandexMapsReviewsParser as ARP
        import yandex_maps_reviews_parser.consts as consts
        meth = [m for m in dir(ARP) if not m.startswith("_") and callable(getattr(ARP, m))]
        token = consts.YANDEX_MAPS_API_TOKEN
        findings["yandex_maps_reviews_parser"] = {
            "installed": True,
            "source": "git+https://github.com/arsenyvolodko/yandex-maps-reviews-parser",
            "version": "0.1.0",
            "engine": "Selenium (visible Chrome) + bs4",
            "api_token_baked_in": bool(token),
            "lookup_by_name_works": False,
            "lookup_by_name_reason": "consts.YANDEX_MAPS_API_TOKEN is empty; "
                                     "requires paid Yandex apikey",
            "fields_per_review": ["rating", "text"],
            "methods": meth,
            "limits": [
                "needs apikey for get_reviews_by_organisation_name()",
                "opens visible Chrome via selenium.webdriver.Chrome()",
                "no proxy support",
                "extracts only (rating, text) per review",
            ],
        }
    except Exception as e:
        findings["yandex_maps_reviews_parser"] = {"installed": False, "error": repr(e)}

    return findings


def main() -> int:
    utf8_stdout()
    res = ExperimentResult(approach="PyPI / GitHub library survey (no live run)")
    t0 = time.perf_counter()
    f = survey()
    for k, v in f.items():
        log_line(NAME, f"{k}: installed={v.get('installed')}")
    res.success = all(f[k].get("installed") for k in f)
    res.notes = (
        "Both libraries are dominated by Approach 4 (Playwright headless + XHR "
        "intercept + RU residential proxy). YMRP needs a visible browser; "
        "arsenyvolodko's lib needs a paid apikey for name lookup and Selenium "
        "Chrome for reviews, returning only (rating, text)."
    )
    res.sample = [{"library_survey": f}]
    res.fields_per_item = sorted(f.keys())
    res.duration_s = round(time.perf_counter() - t0, 2)
    res.save(NAME)
    log_line(NAME, f"verdict: surveyed {len(f)} libs; both have hard-blocking limitations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
