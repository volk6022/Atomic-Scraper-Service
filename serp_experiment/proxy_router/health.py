"""HealthProber — атомарная per-worker проверка через probe-SearXNG."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import httpx
from python_socks.async_.asyncio import Proxy as AsyncSocksProxy

from .worker import ProbeResult, Worker

if TYPE_CHECKING:
    from .config import RouterConfig
    from .probe_slots import ProbeSlotPool
    from .metrics import MetricsCollector


log = logging.getLogger(__name__)


class HealthProber:
    """Probes workers через probe-SearXNG'и.

    Использование:
        prober = HealthProber(config, slot_pool, metrics)
        result = await prober.probe(worker)
    """

    def __init__(
        self,
        config: RouterConfig,
        slot_pool: ProbeSlotPool,
        metrics: MetricsCollector,
    ) -> None:
        self.config = config
        self.slot_pool = slot_pool
        self.metrics = metrics
        # shared httpx client (HTTP/1.1, не идём через прокси — это локальный
        # вызов до probe-SearXNG)
        self._http = httpx.AsyncClient(timeout=config.probe_http_timeout)

    async def close(self) -> None:
        await self._http.aclose()

    async def probe(self, worker: Worker) -> ProbeResult:
        """Один атомарный probe конкретного worker'а.

        Алгоритм:
          1. acquire probe-slot
          2. router.set_slot_worker(slot.id, worker)  — мутируем mapping
          3. httpx.GET к probe-SearXNG'у на slot.searxng_port
          4. парсим JSON, определяем clean/dirty
          5. release slot
          6. record_probe + metrics.probe_event
        """
        slot = await self.slot_pool.acquire()
        t0 = time.monotonic()
        result: ProbeResult
        try:
            # привязка слота к worker'у
            self.slot_pool.set_worker(slot.id, worker)

            url = (
                f"http://localhost:{slot.searxng_port}/search"
                f"?q={self._urlencode(self.config.probe_query)}&format=json&language=en"
            )
            try:
                resp = await self._http.get(
                    url,
                    headers={"Accept": "application/json"},
                    timeout=self.config.probe_http_timeout,
                )
                latency_ms = int((time.monotonic() - t0) * 1000)
                result = self._evaluate_response(resp, latency_ms)
            except (httpx.TimeoutException, asyncio.TimeoutError):
                latency_ms = int((time.monotonic() - t0) * 1000)
                result = ProbeResult(
                    clean=False, latency_ms=latency_ms, marker="timeout"
                )
            except httpx.HTTPError as e:
                latency_ms = int((time.monotonic() - t0) * 1000)
                result = ProbeResult(
                    clean=False,
                    latency_ms=latency_ms,
                    marker=f"http_err:{type(e).__name__}",
                )
            except Exception as e:  # noqa: BLE001
                latency_ms = int((time.monotonic() - t0) * 1000)
                log.warning("probe unexpected error for %s: %s", worker.short_id, e)
                result = ProbeResult(
                    clean=False, latency_ms=latency_ms, marker=f"err:{type(e).__name__}"
                )
        finally:
            await self.slot_pool.release(slot.id)

        # запись метрик
        worker.record_probe(result)
        self.metrics.probe_event(
            worker_id=worker.short_id,
            external_ip=worker.external_ip,
            clean=result.clean,
            marker=result.marker,
            latency_ms=result.latency_ms,
            organic_count=result.organic_count,
            http_status=result.http_status,
            unresponsive=result.unresponsive,
        )
        return result

    def _evaluate_response(
        self, resp: httpx.Response, latency_ms: int
    ) -> ProbeResult:
        http_status = resp.status_code
        if http_status >= 400:
            return ProbeResult(
                clean=False,
                latency_ms=latency_ms,
                marker=f"http_{http_status}",
                http_status=http_status,
            )
        try:
            data = resp.json()
        except Exception:
            return ProbeResult(
                clean=False,
                latency_ms=latency_ms,
                marker="bad_json",
                http_status=http_status,
            )

        organic = data.get("results") or data.get("organic") or []
        # SearXNG возвращает 'results', а наш searxng_local конвертирует в 'organic'.
        # Здесь идём напрямую к /search → ключ 'results'.
        organic_count = len(organic)
        unresponsive_raw = data.get("unresponsive_engines") or []
        # unresponsive_engines в JSON-формате — список [engine_name, reason] пар
        unresponsive = []
        for item in unresponsive_raw:
            if isinstance(item, (list, tuple)) and item:
                unresponsive.append(str(item[0]))
            elif isinstance(item, str):
                unresponsive.append(item)

        # критерии чистоты:
        # - HTTP 200 (✓ уже выше)
        # - organic >= probe_min_organic
        # - не "оба" критичных engine упали одновременно
        critical_engines = {"google", "duckduckgo"}
        critical_down = critical_engines.intersection(unresponsive)
        both_critical_down = critical_down == critical_engines

        if organic_count >= self.config.probe_min_organic and not both_critical_down:
            return ProbeResult(
                clean=True,
                latency_ms=latency_ms,
                marker="ok",
                organic_count=organic_count,
                http_status=http_status,
                unresponsive=unresponsive,
            )
        # dirty варианты
        if organic_count == 0:
            marker = "empty"
        elif organic_count < self.config.probe_min_organic:
            marker = f"low_organic_{organic_count}"
        elif both_critical_down:
            marker = "all_critical_down"
        else:
            marker = "mixed"
        return ProbeResult(
            clean=False,
            latency_ms=latency_ms,
            marker=marker,
            organic_count=organic_count,
            http_status=http_status,
            unresponsive=unresponsive,
        )

    @staticmethod
    def _urlencode(s: str) -> str:
        from urllib.parse import quote_plus
        return quote_plus(s)

    # ---- internal IP detection (опц.) ----
    async def refresh_external_ip(self, worker: Worker) -> str | None:
        """Узнать external IP воркера напрямую через socks5 (минуя SearXNG).

        Не пишет в metrics — это служебное поле для логов и /metrics.
        Возвращает IP или None при сбое.
        """
        try:
            # python-socks: открываем connection к ipify через socks5,
            # шлём HTTP/1.1 GET, читаем ответ.
            proxy = AsyncSocksProxy.from_url(worker.socks5_url)
            from urllib.parse import urlparse
            parsed = urlparse(self.config.external_ip_url)
            target_host = parsed.hostname
            target_port = 443 if parsed.scheme == "https" else 80
            sock = await asyncio.wait_for(
                proxy.connect(dest_host=target_host, dest_port=target_port),
                timeout=10,
            )
            # для https — нужен TLS handshake. Чтобы не таскать TLS-обвязку,
            # просим http (api.ipify.org поддерживает оба). Если scheme https,
            # упрощённо открываем TLS через asyncio.open_connection(ssl=True).
            ssl_ctx = None
            if parsed.scheme == "https":
                import ssl
                ssl_ctx = ssl.create_default_context()
            up_reader, up_writer = await asyncio.open_connection(
                sock=sock, ssl=ssl_ctx, server_hostname=target_host if ssl_ctx else None
            )
            req = (
                f"GET {parsed.path or '/'} HTTP/1.1\r\n"
                f"Host: {target_host}\r\n"
                f"User-Agent: serp-exp-router/1.0\r\n"
                f"Accept: text/plain\r\n"
                f"Connection: close\r\n\r\n"
            )
            up_writer.write(req.encode("ascii"))
            await up_writer.drain()
            raw = await asyncio.wait_for(up_reader.read(4096), timeout=8)
            up_writer.close()
            # ответ примерно "HTTP/1.1 200 OK\r\n...\r\n\r\n95.x.x.x"
            head, _, body = raw.partition(b"\r\n\r\n")
            ip = body.decode("ascii", errors="replace").strip()
            if ip and all(part.isdigit() for part in ip.replace(":", ".").split(".")[:4]):
                worker.external_ip = ip
                return ip
        except Exception as e:  # noqa: BLE001
            log.debug("ipify probe failed for %s: %s", worker.short_id, e)
        return None
