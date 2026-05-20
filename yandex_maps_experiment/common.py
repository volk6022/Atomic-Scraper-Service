"""Shared helpers for Yandex Maps experiments."""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = EXPERIMENT_ROOT / "results"
LOGS_DIR = EXPERIMENT_ROOT / "logs"
RESULTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# --- target ------------------------------------------------------------------
# SPB-focused medical/dental — matches the use case described in the research doc
TARGET_QUERY = "стоматология"
TARGET_CITY = "Санкт-Петербург"
SPB_REGION_ID = 2  # yandex lr=2
# A loose bbox over central + south SPB; trimmed for smoke testing
SPB_BBOX = (30.190, 59.830, 30.520, 59.990)  # (lon_min, lat_min, lon_max, lat_max)
TARGET_PAGES = 50  # ~one search page worth; aiming "medium" depth ~20-50 items

# --- proxy -------------------------------------------------------------------
PROXY_FILE = REPO_ROOT / os.environ.get("PULS_FILE", "puls_sticky_30min.txt")


def load_proxies() -> dict[str, str]:
    """Return {'http': '...', 'socks5': '...'} from the sticky proxy file."""
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


def http_proxy_url() -> str:
    p = load_proxies().get("http")
    if not p:
        raise RuntimeError(f"No http proxy in {PROXY_FILE}")
    return p


def socks_proxy_url() -> str | None:
    return load_proxies().get("socks5")


def playwright_proxy() -> dict[str, str]:
    """Convert proxy URL to Playwright proxy dict."""
    url = http_proxy_url()
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


def requests_proxies() -> dict[str, str]:
    url = http_proxy_url()
    return {"http": url, "https": url}


# --- reporting ---------------------------------------------------------------
@dataclass
class ExperimentResult:
    approach: str
    success: bool = False
    captcha_detected: bool = False
    http_status: int | None = None
    items_collected: int = 0
    fields_per_item: list[str] = field(default_factory=list)
    egress_ip: str | None = None
    duration_s: float = 0.0
    notes: str = ""
    sample: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def save(self, name: str) -> Path:
        path = RESULTS_DIR / f"{name}.json"
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def log_line(name: str, msg: str) -> None:
    print(f"[{name}] {msg}", flush=True)
    (LOGS_DIR / f"{name}.log").open("a", encoding="utf-8").write(
        f"{datetime.now(timezone.utc).isoformat()}  {msg}\n"
    )


def utf8_stdout() -> None:
    """Avoid Windows cp1251 mojibake when printing Cyrillic."""
    import io as _io
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# --- small utils -------------------------------------------------------------
def get_egress_ip(proxies: dict[str, str], timeout: int = 15) -> str | None:
    import requests
    try:
        r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=timeout, verify=False)
        r.raise_for_status()
        return r.json().get("ip")
    except Exception:
        return None


def now() -> float:
    return time.perf_counter()
