"""Scale test: orgzz.ru org pages — address, hours, payment, metro."""
import asyncio
from _common import run_site, has_phone


def rewrite(url: str) -> str:
    return url


def validate(html: str) -> dict:
    has_addr = "Адрес" in html or "дрес" in html
    has_extra = "Часы" in html or "Метро" in html or "Оплата" in html or "круглосуточно" in html.lower()
    return {"content_ok": has_addr and has_extra,
            "phone": has_phone(html), "has_address": has_addr, "has_extra": has_extra}


if __name__ == "__main__":
    asyncio.run(run_site("orgzz.ru", rewrite, validate))
