"""Parse Google SERP HTML → unified dict format (Serper-compatible)."""
from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup


# Markers that strongly suggest Google blocked / captcha-walled us.
BLOCK_MARKERS = (
    "/sorry/",
    "Our systems have detected unusual traffic",
    "About this page",
    "captcha-form",
    "g-recaptcha",
    "if you are not redirected within",  # consent interstitial without JS
    "enable javascript on your web browser",
)


def looks_blocked(html: str) -> bool:
    h = html[:8000]
    return any(m in h for m in BLOCK_MARKERS)


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _extract_blocks(soup: BeautifulSoup) -> list:
    """Find organic result containers using a layered fallback."""
    blocks = soup.select("div.tF2Cxc")
    if blocks:
        return blocks

    # Newer Google layout: each result root contains a .yuRUbf wrapper for the title link
    blocks = []
    for yu in soup.select("div.yuRUbf"):
        root = yu
        for _ in range(6):
            root = root.parent
            if root is None:
                break
            if root.select_one(".VwiC3b, [data-sncf]"):
                blocks.append(root)
                break
    if blocks:
        return blocks

    # Last resort: every h3 with an ancestor anchor; container is the closest div ancestor with a snippet
    seen = set()
    for h3 in soup.find_all("h3"):
        a = h3.find_parent("a")
        if not a or not a.get("href"):
            continue
        node = h3
        for _ in range(8):
            node = node.parent
            if node is None:
                break
            if node.select_one(".VwiC3b, [data-sncf]"):
                if id(node) not in seen:
                    seen.add(id(node))
                    blocks.append(node)
                break
    return blocks


def parse_serp_html(html: str, query: str, num: int = 10) -> dict[str, Any]:
    """Return Serper-compatible dict from raw Google SERP HTML."""
    soup = BeautifulSoup(html, "lxml")
    organic: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for blk in _extract_blocks(soup):
        a = blk.find("a", href=True)
        h3 = blk.find("h3")
        if not (a and h3):
            continue
        link = a["href"]
        if not link.startswith("http"):
            continue
        if "google." in link.split("/")[2]:
            continue
        if link in seen_links:
            continue
        seen_links.add(link)

        title = _clean(h3.get_text(" "))
        sn_el = blk.select_one(".VwiC3b") or blk.select_one("[data-sncf]")
        snippet = _clean(sn_el.get_text(" ")) if sn_el else ""

        organic.append(
            {
                "title": title,
                "link": link,
                "snippet": snippet,
                "position": len(organic) + 1,
            }
        )
        if len(organic) >= num:
            break

    return {
        "searchParameters": {
            "q": query,
            "type": "search",
            "engine": "google",
            "num": num,
        },
        "organic": organic,
    }
