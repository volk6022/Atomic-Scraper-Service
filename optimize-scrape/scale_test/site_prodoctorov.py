"""Scale test: prodoctorov.ru clinic (lpu) pages — doctors, services, phone, legal entity."""
import asyncio
from _common import run_site, has_phone


def rewrite(url: str) -> str:
    return url


def validate(html: str) -> dict:
    low = html.lower()
    phone = has_phone(html)
    has_doctors = "врач" in low
    has_desc = "Описание" in html or "Услуги" in html
    return {"content_ok": (phone and has_doctors) or (has_doctors and has_desc),
            "phone": phone, "has_doctors": has_doctors, "has_desc": has_desc}


if __name__ == "__main__":
    asyncio.run(run_site("prodoctorov.ru", rewrite, validate))
