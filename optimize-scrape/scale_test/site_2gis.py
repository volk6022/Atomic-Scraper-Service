"""Scale test: 2gis.ru firm pages. CONTROL — httpx hits an 'обновите браузер'
interstitial, not the firm card; content_ok stays low, proving 2gis needs the
browser path (or newer-UA / catalog API). Traffic/stability of the interstitial
is still measured at scale."""
import asyncio
from _common import run_site, has_phone


def rewrite(url: str) -> str:
    return url


def validate(html: str) -> dict:
    low = html.lower()
    interstitial = "обновить браузер" in low or "обновите браузер" in low or "советует обновить" in low
    has_firm = has_phone(html) or "Контакты" in html or "Часы работы" in html
    return {"content_ok": (not interstitial) and has_firm,
            "is_interstitial": interstitial, "phone": has_phone(html)}


if __name__ == "__main__":
    asyncio.run(run_site("2gis.ru", rewrite, validate))
