"""Scale test: zoon.ru org cards — name, phones, address, hours, reviews."""
import asyncio
from _common import run_site, has_phone


def rewrite(url: str) -> str:
    return url


def validate(html: str) -> dict:
    phone = has_phone(html)
    has_addr = "Адрес" in html or "дрес" in html
    has_extra = "Отзыв" in html or "Часы" in html or "ейтинг" in html
    return {"content_ok": phone or (has_addr and has_extra),
            "phone": phone, "has_address": has_addr, "has_extra": has_extra}


if __name__ == "__main__":
    asyncio.run(run_site("zoon.ru", rewrite, validate))
