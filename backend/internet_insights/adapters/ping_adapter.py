"""Ping adapter - wraps main._quick_ping()."""

from __future__ import annotations

import asyncio
import logging
import socket
import time

logger = logging.getLogger("dashboard.internet_insights.adapters.ping")


class PingAdapter:
    """Wrap main._quick_ping() — same target, timeout, method."""

    def __init__(self):
        self._dns_cache: dict[str, tuple[float, str]] = {}  # host -> (ts, ip)
        self._dns_cache_ttl = 60.0  # seconds

    async def ping(self, host: str = "1.1.1.1", timeout: float = 1.0) -> float | None:
        """Quick latency probe using asyncio TCP connect latency (no raw ICMP)."""
        loop = asyncio.get_event_loop()
        start = loop.time()

        try:
            # Resolve hostname with caching
            addr = await self._resolve_host(host)
            if not addr:
                return None
        except socket.gaierror:
            return None

        try:
            # TCP connect to port 80 (HTTP) - measures connect latency
            # Returns RTT in ms (even on connection refused)
            # None on DNS failure or timeout
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(addr, 80),
                timeout=timeout,
            )
            writer.close()
            with asyncio.suppress(Exception):
                await writer.wait_closed()
            return round((loop.time() - start) * 1000, 1)
        except (TimeoutError, ConnectionRefusedError, OSError):
            # A refused/failed TCP connect still yields a latency estimate
            elapsed = loop.time() - start
            if elapsed < timeout:
                return round(elapsed * 1000, 1)
            return None

    async def _resolve_host(self, host: str) -> str | None:
        """Resolve hostname with caching."""
        now = time.time()
        if host in self._dns_cache:
            ts, ip = self._dns_cache[host]
            if now - ts < self._dns_cache_ttl:
                return ip

        try:
            loop = asyncio.get_event_loop()
            ip = await loop.run_in_executor(None, socket.gethostbyname, host)
            self._dns_cache[host] = (now, ip)
            return ip
        except socket.gaierror:
            return None

    async def ping_multiple(self, hosts: list[str], timeout: float = 1.0, max_concurrent: int = 3) -> dict[str, float | None]:
        """Ping multiple hosts concurrently."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _ping_one(host: str) -> tuple[str, float | None]:
            async with semaphore:
                return host, await self.ping(host, timeout)

        results = await asyncio.gather(*[_ping_one(h) for h in hosts])
        return dict(results)
