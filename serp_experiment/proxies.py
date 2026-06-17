"""Load proxies from puls.txt and convert to per-tool formats."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


_REPO_ROOT = Path(__file__).resolve().parents[1]
# Override with env: PULS_FILE=puls_sticky_30min.txt
PROXY_FILE = _REPO_ROOT / os.environ.get("PULS_FILE", "puls.txt")


def _load_raw() -> dict[str, str]:
    """Return {'http': '...', 'socks5': '...'} from puls.txt."""
    if not PROXY_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in PROXY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        scheme = line.split("://", 1)[0].lower()
        if scheme in ("http", "https"):
            out["http"] = line
        elif scheme.startswith("socks"):
            out["socks5"] = line
    return out


def get_proxy_url(kind: str) -> str | None:
    """kind ∈ {'http', 'socks5'} -> full proxy URL or None."""
    return _load_raw().get(kind)


def split_proxy_url(url: str) -> dict[str, str]:
    """Parse 'scheme://user:pass@host:port' into Playwright proxy dict.

    Returns: {'server': 'scheme://host:port', 'username': '...', 'password': '...'}
    """
    parsed = urlparse(url)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    out = {"server": server}
    if parsed.username:
        out["username"] = parsed.username
    if parsed.password:
        out["password"] = parsed.password
    return out


def requests_proxies_dict(url: str) -> dict[str, str]:
    """Build dict expected by requests.get(proxies=...)."""
    return {"http": url, "https": url}


if __name__ == "__main__":
    print(_load_raw())
    for k in ("http", "socks5"):
        u = get_proxy_url(k)
        if u:
            print(k, "->", split_proxy_url(u))
