"""Scale test: vk.com (rewrite -> m.vk.com). CONTROL — expected to be a stub
('Ваш браузер устарел'); content_ok stays low, proving httpx is NOT viable for VK
without a dedicated adapter. We still measure traffic/stability of the stub at scale."""
import asyncio
from urllib.parse import urlparse
from _common import run_site, has_phone


def rewrite(url: str) -> str:
    p = urlparse(url)
    if p.netloc.lower() in ("vk.com", "www.vk.com"):
        return f"https://m.vk.com{p.path}"
    return url


def validate(html: str) -> dict:
    stub = "браузер устарел" in html.lower()
    # real profile would expose og:description text or wall content
    has_profile = ("og:description" in html.lower() and "content=\"\"" not in html.lower())
    return {"content_ok": (not stub) and has_profile,
            "is_outdated_stub": stub, "phone": has_phone(html)}


if __name__ == "__main__":
    asyncio.run(run_site("vk.com", rewrite, validate))
