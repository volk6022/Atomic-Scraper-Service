"""Scale test: rusprofile.ru registry pages — ИНН/ОГРН/director/address."""
import asyncio
from _common import run_site


def rewrite(url: str) -> str:
    return url


def validate(html: str) -> dict:
    has_ogrn = "ОГРН" in html
    has_inn = "ИНН" in html
    has_dir = "иректор" in html or "уковод" in html  # Директор / Руководитель
    return {"content_ok": has_ogrn and has_inn,
            "has_ogrn": has_ogrn, "has_inn": has_inn, "has_director": has_dir}


if __name__ == "__main__":
    asyncio.run(run_site("rusprofile.ru", rewrite, validate))
