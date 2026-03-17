import random
from typing import Optional, List
from pathlib import Path


class ProxyProvider:
    def __init__(self, proxy_file: str = "proxies.txt"):
        self.proxy_file = Path(proxy_file)
        self._proxies: List[str] = []
        self._load_proxies()

    def _load_proxies(self):
        if self.proxy_file.exists():
            with open(self.proxy_file, "r") as f:
                self._proxies = [line.strip() for line in f if line.strip()]

    def get_proxy(self) -> Optional[str]:
        if not self._proxies:
            return None
        return random.choice(self._proxies)


proxy_provider = ProxyProvider()
