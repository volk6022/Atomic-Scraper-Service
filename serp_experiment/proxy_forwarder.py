"""Local HTTP-CONNECT → SOCKS5 forwarder.

Chromium (and therefore Playwright) does not support **authenticated** SOCKS5
proxies through the `proxy={...}` option. The workaround is to expose the
upstream proxy as an unauthenticated local HTTP proxy and let Playwright talk
to that.

`HttpToSocksForwarder` listens on `127.0.0.1:<random-port>`, accepts HTTPS
CONNECT tunnels from Playwright, and pipes them through the upstream
SOCKS5 proxy (with username/password baked in). The forwarder is an async
context manager so its lifetime is tied to a single scrape.

`PlaywrightProxySource` is the public abstraction the approaches use:

    async with PlaywrightProxySource(proxy_url) as pw_proxy:
        await browser_type.launch(proxy=pw_proxy, ...)

For an HTTP upstream proxy it returns Playwright's native
`{"server", "username", "password"}` dict — no forwarder is spun up.
For a SOCKS5 upstream it spins up the forwarder and returns
`{"server": "http://127.0.0.1:<port>"}`.
For `proxy_url=None` it returns `None` (no proxy at all).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from python_socks.async_.asyncio import Proxy as AsyncSocksProxy

from .proxies import split_proxy_url

log = logging.getLogger(__name__)


# --- Reusable CONNECT helpers (used by router too) ----------------------------


async def read_connect_target(
    reader: asyncio.StreamReader,
) -> tuple[str | None, int | None, bytes | None]:
    """Read & parse HTTP CONNECT request line + drain headers.

    Returns:
        (host, port, None) on success — caller must still write 200/4xx response.
        (None, None, error_response) on bad request — caller should write that
        response and close.
    """
    request_line = await reader.readline()
    if not request_line:
        return None, None, b""

    parts = request_line.decode("iso-8859-1", errors="replace").split()
    if len(parts) < 2 or parts[0].upper() != "CONNECT":
        return None, None, b"HTTP/1.1 405 Method Not Allowed\r\n\r\n"

    target = parts[1]
    host, _, port_s = target.partition(":")
    try:
        port = int(port_s) if port_s else 443
    except ValueError:
        return None, None, b"HTTP/1.1 400 Bad Request\r\n\r\n"

    # drain remaining request headers
    while True:
        hdr = await reader.readline()
        if not hdr or hdr in (b"\r\n", b"\n", b""):
            break

    return host, port, None


async def pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    byte_counter: list[int] | None = None,
) -> None:
    """Pipe bytes from reader to writer. Optional byte_counter is a 1-element
    list that gets incremented (for caller observability)."""
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            if byte_counter is not None:
                byte_counter[0] += len(data)
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


class HttpToSocksForwarder:
    """Local HTTP CONNECT proxy → upstream SOCKS5 (or HTTP) proxy."""

    def __init__(self, upstream_url: str, *, host: str = "127.0.0.1") -> None:
        self.upstream_url = upstream_url
        self.host = host
        self._server: asyncio.base_events.Server | None = None
        self._port: int = 0

    # --- public ----------------------------------------------------------
    @property
    def local_url(self) -> str:
        return f"http://{self.host}:{self._port}"

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, host=self.host, port=0
        )
        # asyncio.start_server returns; pick the bound port
        sock = self._server.sockets[0]
        self._port = sock.getsockname()[1]
        log.debug("forwarder listening on %s -> %s", self.local_url, self.upstream_url)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

    async def __aenter__(self) -> "HttpToSocksForwarder":
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stop()

    # --- internals -------------------------------------------------------
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            host, port, err = await read_connect_target(reader)
            if err is not None:
                if err:
                    writer.write(err)
                    await writer.drain()
                writer.close()
                return
            assert host is not None and port is not None

            # Open upstream tunnel
            try:
                proxy = AsyncSocksProxy.from_url(self.upstream_url)
                upstream_sock = await proxy.connect(dest_host=host, dest_port=port)
            except Exception as e:  # noqa: BLE001
                log.warning("forwarder: upstream connect failed: %s", e)
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                writer.close()
                return

            up_reader, up_writer = await asyncio.open_connection(sock=upstream_sock)

            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            await asyncio.gather(
                pipe(reader, up_writer),
                pipe(up_reader, writer),
                return_exceptions=True,
            )
        except Exception as e:  # noqa: BLE001
            log.debug("forwarder client handler error: %s", e)
        finally:
            try:
                writer.close()
            except Exception:
                pass


class PlaywrightProxySource:
    """Abstraction that yields a Playwright-compatible proxy dict.

    For SOCKS5 upstreams it transparently spins up a local HTTP→SOCKS5
    forwarder so Chromium sees an unauthenticated HTTP proxy.
    """

    def __init__(self, proxy_url: str | None) -> None:
        self.proxy_url = proxy_url
        self._forwarder: HttpToSocksForwarder | None = None

    async def __aenter__(self) -> dict[str, str] | None:
        if not self.proxy_url:
            return None
        scheme = self.proxy_url.split("://", 1)[0].lower()
        if scheme.startswith("socks"):
            self._forwarder = HttpToSocksForwarder(self.proxy_url)
            await self._forwarder.start()
            return {"server": self._forwarder.local_url}
        # HTTP/HTTPS upstream: Playwright handles auth natively
        return split_proxy_url(self.proxy_url)

    async def __aexit__(self, *exc: Any) -> None:
        if self._forwarder is not None:
            await self._forwarder.stop()
            self._forwarder = None
