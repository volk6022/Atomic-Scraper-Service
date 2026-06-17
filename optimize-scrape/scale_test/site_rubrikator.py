"""Scale test: rubrikator.org catalog pages — name, phones, addresses, reviews."""
import asyncio
from _common import run_site, has_phone


def rewrite(url: str) -> str:
    return url


def validate(html: str) -> dict:
    phone = has_phone(html)
    has_addr = "дрес" in html  # Адрес/адреса
    return {"content_ok": phone or has_addr, "phone": phone, "has_address": has_addr}


if __name__ == "__main__":
    asyncio.run(run_site("rubrikator.org", rewrite, validate))
