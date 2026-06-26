"""
proxy_client.py — reusable rotating-proxy httpx helper for experiment-hh.

Parses each line of proxies.txt (format:
  http://USER;sessttl.10:PASS@HOST:PORT
), URL-encodes the special chars in userinfo, and exposes a
`ProxyRotatingClient` that wraps httpx and auto-retries on infra errors
(timeout, connect error, 407, 5xx) by cycling to the next proxy.
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


class ProxyRotatingClient:
    """
    Thin wrapper around httpx that rotates proxies on infra failures.

    Usage:
        client = ProxyRotatingClient()
        resp = client.get("https://api.hh.ru/vacancies", params={...})
    """

    def __init__(
        self,
        proxies: list[str] | None = None,
        timeout: float = 20.0,
        max_retries: int = 10,
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
            "User-Agent": "HH-Verification-Agent/1.0 (research; contact vpncreatedakk@gmail.com)",
            "Accept": "application/json",
            **(headers or {}),
        }

    def _next_proxy(self) -> str:
        p = self._proxies[self._idx % len(self._proxies)]
        self._idx += 1
        return p

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        tried: list[str] = []
        last_exc: Exception | None = None

        for attempt in range(min(self._max_retries, len(self._proxies))):
            proxy_url = self._next_proxy()
            tried.append(proxy_url)
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
                            f"  [proxy {attempt+1}] HTTP {response.status_code} on "
                            f"{proxy_url.split('@')[-1]} — retrying"
                        )
                        last_exc = RuntimeError(f"HTTP {response.status_code}")
                        continue
                    return response
            except _INFRA_ERRORS as exc:
                print(
                    f"  [proxy {attempt+1}] {type(exc).__name__} on "
                    f"{proxy_url.split('@')[-1]} — retrying"
                )
                last_exc = exc
                time.sleep(0.5)

        raise RuntimeError(
            f"All {len(tried)} proxies failed for {url}. Last error: {last_exc}"
        )

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)
