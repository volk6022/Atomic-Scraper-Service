"""Scale test: hh.ru / spb.hh.ru employer pages (SSR company card + vacancies)."""
import asyncio
from _common import run_site


def rewrite(url: str) -> str:
    return url  # employer page is SSR as-is


def validate(html: str) -> dict:
    has_company = ("employerview" in html.lower() or "О компании" in html
                   or "employer-sidebar" in html.lower())
    has_vacancies = "аканси" in html  # 'Вакансии'/'вакансий'
    return {"content_ok": has_company or has_vacancies,
            "has_company": has_company, "has_vacancies": has_vacancies}


if __name__ == "__main__":
    asyncio.run(run_site("hh.ru", rewrite, validate))
