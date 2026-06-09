"""Scale test: t.me (rewrite t.me/X -> t.me/s/X, pure SSR channel preview)."""
import asyncio
from urllib.parse import urlparse
from _common import run_site


def rewrite(url: str) -> str:
    p = urlparse(url)
    if p.netloc.lower() in ("t.me", "www.t.me") and not p.path.startswith("/s/"):
        if len(p.path.strip("/")) > 0:
            return f"https://t.me/s{p.path}"
    return url


def validate(html: str) -> dict:
    low = html.lower()
    has_posts = "tgme_widget_message" in low
    has_title = "tgme_channel_info" in low or "tgme_page_title" in low or "tgme_header_title" in low
    # a public channel preview renders either posts or at least the channel header
    return {"content_ok": has_posts or has_title,
            "has_posts": has_posts, "has_title": has_title}


if __name__ == "__main__":
    asyncio.run(run_site("t.me", rewrite, validate))
