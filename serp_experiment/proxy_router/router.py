"""Router — listeners (main + K probe-portов), CONNECT handler, /metrics."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from ..proxy_forwarder import read_connect_target, pipe
from .worker import Worker

if TYPE_CHECKING:
    from .config import RouterConfig
    from .pool import WorkerPool
    from .probe_slots import ProbeSlotPool
    from .metrics import MetricsCollector


log = logging.getLogger(__name__)


class Router:
    def __init__(
        self,
        config: RouterConfig,
        pool: WorkerPool,
        slot_pool: ProbeSlotPool,
        metrics: MetricsCollector,
    ) -> None:
        self.config = config
        self.pool = pool
        self.slot_pool = slot_pool
        self.metrics = metrics

        self._main_server: asyncio.base_events.Server | None = None
        self._probe_servers: list[asyncio.base_events.Server] = []
        self._stopped = False

    # ---- lifecycle ----
    async def start(self) -> None:
        # main listener
        self._main_server = await asyncio.start_server(
            lambda r, w: self._handle_client(r, w, source="main"),
            host=self.config.listen_host,
            port=self.config.main_port,
        )
        log.info("Router main listener on %s:%d", self.config.listen_host, self.config.main_port)

        # K probe listeners
        for slot in self.slot_pool.slots:
            srv = await asyncio.start_server(
                lambda r, w, sid=slot.id: self._handle_client(r, w, source=sid),
                host=self.config.listen_host,
                port=slot.router_port,
            )
            self._probe_servers.append(srv)
            log.info(
                "Router probe listener slot=%d on %s:%d",
                slot.id, self.config.listen_host, slot.router_port,
            )

    async def stop(self) -> None:
        self._stopped = True
        if self._main_server:
            self._main_server.close()
            try:
                await self._main_server.wait_closed()
            except Exception:
                pass
        for srv in self._probe_servers:
            srv.close()
            try:
                await srv.wait_closed()
            except Exception:
                pass

    async def serve_forever(self) -> None:
        # Не нужно. asyncio.start_server возвращает уже-слушающий сервер;
        # close() в .stop() остановит. Метод оставлен для совместимости.
        return

    # ---- handler ----
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        source: object,  # "main" | int (slot_id)
    ) -> None:
        # Прочитать первую строку — определить, CONNECT это или GET /metrics
        try:
            first = await reader.readline()
        except Exception:
            try: writer.close()
            except Exception: pass
            return

        if not first:
            try: writer.close()
            except Exception: pass
            return

        first_str = first.decode("iso-8859-1", errors="replace")
        method = first_str.split(" ", 1)[0].upper()

        if method == "GET":
            await self._handle_get(reader, writer, first_str, source)
            return

        if method != "CONNECT":
            try:
                writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
            try: writer.close()
            except Exception: pass
            return

        # CONNECT — дочитываем target + headers
        parts = first_str.split()
        if len(parts) < 2:
            try:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
            try: writer.close()
            except Exception: pass
            return
        target = parts[1]
        host, _, port_s = target.partition(":")
        try:
            port = int(port_s) if port_s else 443
        except ValueError:
            try:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
            try: writer.close()
            except Exception: pass
            return
        # drain headers
        try:
            while True:
                hdr = await reader.readline()
                if not hdr or hdr in (b"\r\n", b"\n", b""):
                    break
        except Exception:
            pass

        await self._handle_connect(reader, writer, host, port, source)

    async def _handle_get(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        first_line: str,
        source: object,
    ) -> None:
        # Простой mini-router для /metrics, /healthz
        # /metrics поддерживаем только на main listener'е
        try:
            parts = first_line.split()
            path = parts[1] if len(parts) > 1 else "/"
            # drain headers
            while True:
                hdr = await reader.readline()
                if not hdr or hdr in (b"\r\n", b"\n", b""):
                    break

            if source != "main":
                self._write_http(writer, 404, b"not found on probe port")
                return

            if path == "/metrics":
                body = self.metrics.http_metrics_json()
                self._write_http(writer, 200, body, content_type="application/json")
            elif path == "/healthz":
                # 200 если есть хотя бы один ACTIVE
                from .worker import WorkerState
                ok = any(w.state == WorkerState.ACTIVE for w in self.pool.workers)
                self._write_http(writer, 200 if ok else 503, b"ok" if ok else b"no active workers")
            else:
                self._write_http(writer, 404, b"not found")
        except Exception as e:  # noqa: BLE001
            log.debug("GET handler error: %s", e)
        finally:
            try: writer.close()
            except Exception: pass

    def _write_http(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        content_type: str = "text/plain",
    ) -> None:
        reason = {200: "OK", 404: "Not Found", 503: "Service Unavailable"}.get(status, "ERROR")
        head = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        try:
            writer.write(head)
            writer.write(body)
        except Exception:
            pass

    async def _handle_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
        source: object,
    ) -> None:
        # Выбор воркера
        worker: Worker | None
        source_label: str
        if source == "main":
            source_label = "main"
            worker = await self.pool.acquire()
            if worker is None:
                self.metrics.connect_rejected("main", 503, "no_active_workers")
                try:
                    writer.write(b"HTTP/1.1 503 Service Unavailable\r\n\r\n")
                    await writer.drain()
                except Exception:
                    pass
                try: writer.close()
                except Exception: pass
                return
        else:
            # probe port
            slot_id = int(source)  # type: ignore
            source_label = f"probe-{slot_id}"
            worker = self.slot_pool.get_worker(slot_id)
            if worker is None:
                self.metrics.connect_rejected(source_label, 502, "no_worker_in_slot")
                try:
                    writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                    await writer.drain()
                except Exception:
                    pass
                try: writer.close()
                except Exception: pass
                return

        # Открываем upstream
        t0 = time.monotonic()
        bytes_up = [0]
        bytes_down = [0]
        try:
            up_reader, up_writer = await worker.open_tunnel(host, port)
        except Exception as e:  # noqa: BLE001
            worker.record_connect_fail("socks")
            self.metrics.connect_event(
                worker_id=worker.short_id,
                target=f"{host}:{port}",
                source=source_label,
                ok=False,
                bytes_up=0,
                bytes_down=0,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=f"socks:{type(e).__name__}",
            )
            try:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
            except Exception:
                pass
            try: writer.close()
            except Exception: pass
            return

        worker.record_connect_ok()
        try:
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
        except Exception:
            pass

        # Запускаем pipe и регистрируем in-flight
        async def _pipe_pair() -> None:
            await asyncio.gather(
                pipe(reader, up_writer, bytes_up),
                pipe(up_reader, writer, bytes_down),
                return_exceptions=True,
            )

        pipe_task = asyncio.create_task(_pipe_pair())
        worker.register_inflight(pipe_task)

        try:
            await pipe_task
        except asyncio.CancelledError:
            # drain'нули нас принудительно
            pass
        except Exception as e:  # noqa: BLE001
            worker.record_connect_fail("other")
            log.debug("pipe error %s: %s", worker.short_id, e)
        finally:
            worker.record_bytes(bytes_up[0], bytes_down[0])
            self.metrics.connect_event(
                worker_id=worker.short_id,
                target=f"{host}:{port}",
                source=source_label,
                ok=True,
                bytes_up=bytes_up[0],
                bytes_down=bytes_down[0],
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
            try: writer.close()
            except Exception: pass
            try: up_writer.close()
            except Exception: pass
