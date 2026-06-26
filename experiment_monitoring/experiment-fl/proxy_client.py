"""
proxy_client.py - rotating-proxy httpx helper for experiment-fl.

Adapted from experiment-hh/proxy_client.py.  Same proxy format:
  http://efea0cd216087051c2e6__cr.ru;sessttl.10:fc6a3125b4c606fa@np.puls-proxy.com:PORT

The `;` and `.` in the username must be URL-encoded for httpx's proxy URL.
"""
from __future__ import annotations

import random
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Proxy parsing
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r"^https?://"
    r"(?P<user>[^:@]+)"
    r":"
    r"(?P<password>[^@]+)"
    r"@"
    r"(?P<host>[^:]+)"
    r":"
    r"(?P<port>\d+)$"
)

PROXIES_FILE = Path(__file__).parent.parent / "proxies.txt"


def _encode_proxy_url(user: str, password: str, host: str, port: str) -> str:
    """Build a valid proxy URL with URL-encoded userinfo."""
    enc_user = urllib.parse.quote(user, safe="")
    enc_pass = urllib.parse.quote(password, safe="")
    return f"http://{enc_user}:{enc_pass}@{host}:{port}"


def load_proxies(path: Path = PROXIES_FILE) -> list[str]:
    proxies: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        proxies.append(
            _encode_proxy_url(
                m.group("user"),
                m.group("password"),
                m.group("host"),
                m.group("port"),
            )
        )
    return proxies


def proxy_credentials() -> tuple[str, str, str]:
    """Return (host_base, username_raw, password) for Playwright proxy config."""
    # Parse first live proxy entry for credentials
    for raw_line in PROXIES_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            return m.group("host"), m.group("user"), m.group("password")
    raise RuntimeError("No proxies found in proxies.txt")


# ---------------------------------------------------------------------------
# Rotating client
# ---------------------------------------------------------------------------

_INFRA_ERRORS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ProxyError,
)

_RETRY_STATUS = {407, 500, 502, 503, 504}

FL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

FL_HEADERS_JSON = {
    **FL_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}


class ProxyRotatingClient:
    """
    Thin wrapper around httpx that rotates proxies on infra failures.

    Usage:
        client = ProxyRotatingClient()
        resp = client.get("https://www.fl.ru/rss/all.xml")
    """

    def __init__(
        self,
        proxies: list[str] | None = None,
        timeout: float = 25.0,
        max_retries: int = 12,
        shuffle: bool = True,
        headers: dict[str, str] | None = None,
    ):
        self._proxies = proxies if proxies is not None else load_proxies()
        if shuffle:
            random.shuffle(self._proxies)
        self._timeout = timeout
        self._max_retries = max_retries
        self._idx = 0
        self._default_headers: dict[str, str] = {
            **FL_HEADERS,
            **(headers or {}),
        }

    def _next_proxy(self) -> str:
        p = self._proxies[self._idx % len(self._proxies)]
        self._idx += 1
        return p

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        tried: list[str] = []
        last_exc: Exception | None = None

        limit = min(self._max_retries, len(self._proxies))
        for attempt in range(limit):
            proxy_url = self._next_proxy()
            tried.append(proxy_url)
            proxy_display = proxy_url.split("@")[-1]
            try:
                with httpx.Client(
                    proxy=proxy_url,
                    timeout=self._timeout,
                    headers=self._default_headers,
                    follow_redirects=True,
                ) as client:
                    response = client.request(method, url, **kwargs)
                    if response.status_code in _RETRY_STATUS:
                        print(
                            f"  [proxy {attempt+1}/{limit}] HTTP {response.status_code} "
                            f"on {proxy_display} — retrying"
                        )
                        last_exc = RuntimeError(f"HTTP {response.status_code}")
                        continue
                    print(
                        f"  [proxy {attempt+1}] HTTP {response.status_code} "
                        f"on {proxy_display} — OK"
                    )
                    return response
            except _INFRA_ERRORS as exc:
                print(
                    f"  [proxy {attempt+1}/{limit}] {type(exc).__name__}: {exc} "
                    f"on {proxy_display} — retrying"
                )
                last_exc = exc
                time.sleep(0.5)

        raise RuntimeError(
            f"All {len(tried)} proxies failed for {url}. Last error: {last_exc}"
        )

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)
