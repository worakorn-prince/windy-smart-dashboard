"""HTTP diagnostic with SSRF guard, redirect validation and timing breakdown."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import time
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx

from . import HTTP_TIMEOUT_CAP_MS, is_blocked_ip, validate_timeout_ms

SAFE_METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH")
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
USERINFO_RE = re.compile(r"^(?P<scheme>https?://)(?P<userinfo>[^/@\s:]+:[^/@\s]+@)(?P<rest>.*)", re.IGNORECASE)
MAX_PAYLOAD_URL_LENGTH = 2048
MAX_RESPONSE_BODY_BYTES = 2 * 1024 * 1024


class SsrfBlockedError(ValueError):
    """Raised when a URL resolves to a blocked (private/loopback/link-local) address."""


def redact_url(url: str) -> str:
    match = USERINFO_RE.match(url)
    if match:
        return f"{match.group('scheme')}REDACTED@{match.group('rest')}"
    return url


def _validate_http_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string")
    cleaned = url.strip()
    parts = urlsplit(cleaned)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Only http(s) URLs are allowed: {redact_url(cleaned)}")
    if not parts.hostname:
        raise ValueError(f"URL is missing a hostname: {redact_url(cleaned)}")
    if parts.username or parts.password:
        raise ValueError("URL must not contain credentials (user:pass@)")
    return cleaned


async def _resolve_and_guard(hostname: str, allow_private: bool) -> float:
    start = time.monotonic()
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for {hostname}: {e}") from e
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    seen: set[str] = set()
    for info in infos:
        addr = info[4][0]
        if addr in seen:
            continue
        seen.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if not allow_private and is_blocked_ip(ip):
            raise SsrfBlockedError(f"Blocked URL host resolves to private/loopback/link-local address: {hostname} -> {addr}")
    if not seen:
        raise ValueError(f"No usable addresses resolved for {hostname}")
    return duration_ms


class _PinnedIpNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connect only to IPs that pass the SSRF guard (TOCTOU closure).

    Every dial re-resolves and re-validates all IPs before connecting to
    the exact validated address; SNI/Host keep the original hostname.
    """

    def __init__(self, delegate: httpcore.AsyncNetworkBackend, allow_private: bool):
        self._delegate = delegate
        self._allow_private = allow_private

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        seen: list[str] = []
        for info in infos:
            addr = info[4][0]
            if addr not in seen:
                seen.append(addr)
        candidates: list[str] = []
        for addr in seen:
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if not self._allow_private and is_blocked_ip(ip):
                raise SsrfBlockedError(f"Blocked URL host resolves to private/loopback/link-local address: {host} -> {addr}")
            candidates.append(addr)
        if not candidates:
            raise ValueError(f"No usable addresses resolved for {host}")
        last_exc: Exception | None = None
        deadline = None if timeout is None else time.monotonic() + timeout
        for addr in candidates:
            dial_timeout = timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    last_exc = last_exc if last_exc is not None else httpcore.ConnectTimeout(
                        f"connect budget exhausted before trying {host} -> {addr}"
                    )
                    break
                dial_timeout = remaining
            try:
                return await self._delegate.connect_tcp(
                    addr,
                    port,
                    timeout=dial_timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (OSError, httpcore.ConnectError, httpcore.ConnectTimeout) as e:
                last_exc = e
        raise last_exc if last_exc is not None else OSError(f"connect failed for {host}")


def _pinned_transport(allow_private: bool) -> httpx.AsyncBaseTransport:
    """httpx transport whose network layer dials only SSRF-validated IPs."""
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    delegate = getattr(transport._pool, "_network_backend", None)
    if delegate is None:
        raise RuntimeError(
            "httpcore internals changed: _network_backend not found on pool; "
            "IP-pinned transport cannot be constructed (fail-closed, refusing unpinned dial)"
        )
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=transport._pool._ssl_context,
        max_connections=transport._pool._max_connections,
        max_keepalive_connections=transport._pool._max_keepalive_connections,
        keepalive_expiry=transport._pool._keepalive_expiry,
        http1=transport._pool._http1,
        http2=transport._pool._http2,
        uds=transport._pool._uds,
        local_address=transport._pool._local_address,
        retries=transport._pool._retries,
        socket_options=transport._pool._socket_options,
        network_backend=_PinnedIpNetworkBackend(delegate, allow_private),
    )
    return transport


def _timing_collector(timings: dict[str, float | None]) -> object:
    events: dict[str, float] = {}

    async def on_trace(name: str, _info: dict) -> None:
        now = time.monotonic()
        events[name] = now
        if name.endswith("connect_tcp.complete"):
            started = next((t for k, t in events.items() if k.endswith("connect_tcp.started")), None)
            if started is not None:
                timings["connect_ms"] = round((now - started) * 1000, 1)
        elif name.endswith("start_tls.complete"):
            started = next((t for k, t in events.items() if k.endswith("start_tls.started")), None)
            if started is not None:
                timings["tls_ms"] = round((now - started) * 1000, 1)

    return on_trace


async def http_diagnostic(
    url: str,
    method: str = "GET",
    timeout_ms: int = 10000,
    follow_redirects: bool = True,
    max_redirects: int = 5,
    allow_private: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Run an HTTP request with per-redirect SSRF validation and timing breakdown."""
    if method.upper() not in SAFE_METHODS:
        raise ValueError(f"Unsupported HTTP method: {method}")
    timeout_ms = validate_timeout_ms(timeout_ms, HTTP_TIMEOUT_CAP_MS)
    if max_redirects < 0:
        raise ValueError("max_redirects must be >= 0")
    timeout_sec = timeout_ms / 1000
    method = method.upper()

    timings: dict[str, float | None] = {"dns_ms": None, "connect_ms": None, "tls_ms": None, "ttfb_ms": None, "total_ms": None}
    trace_cb = _timing_collector(timings)
    redirect_chain: list[dict] = []

    current_url = _validate_http_url(url)
    current_method = method
    status = "success"
    error_code: str | None = None
    response: httpx.Response | None = None
    body = b""
    truncated = False
    total_start = time.monotonic()

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout_sec,
            transport=transport if transport is not None else _pinned_transport(allow_private),
            headers={"User-Agent": "windy-dashboard-diagnostics/1.0"},
            trust_env=False,
        ) as client:
            for _hop in range(max_redirects + 1):
                parts = urlsplit(current_url)
                timings["dns_ms"] = await _resolve_and_guard(parts.hostname, allow_private)
                request = client.build_request(current_method, current_url, extensions={"trace": trace_cb})
                send_start = time.monotonic()
                response = await client.send(request, stream=True)
                if response.is_redirect and follow_redirects:
                    await response.aclose()
                    timings["ttfb_ms"] = round((time.monotonic() - send_start) * 1000, 1)
                    location = response.headers.get("location", "")
                    redirect_chain.append({"url": redact_url(str(response.url))[:MAX_PAYLOAD_URL_LENGTH], "status_code": response.status_code})
                    if not location:
                        break
                    next_url = str(httpx.URL(str(response.url)).join(location))
                    current_url = _validate_http_url(next_url)
                    if response.status_code == 303:
                        current_method = "GET"
                    continue
                chunks: list[bytes] = []
                received = 0
                truncated = False
                async for chunk in response.aiter_bytes():
                    if received + len(chunk) > MAX_RESPONSE_BODY_BYTES:
                        chunks.append(chunk[: MAX_RESPONSE_BODY_BYTES - received])
                        truncated = True
                        break
                    chunks.append(chunk)
                    received += len(chunk)
                await response.aclose()
                timings["ttfb_ms"] = round((time.monotonic() - send_start) * 1000, 1)
                body = b"".join(chunks)
                break
            else:
                status = "error"
                error_code = "TooManyRedirects"
    except SsrfBlockedError:
        raise
    except ValueError:
        raise
    except httpx.TimeoutException as e:
        status = "timeout"
        error_code = type(e).__name__
    except httpx.HTTPError as e:
        status = "error"
        error_code = type(e).__name__
    except Exception as e:
        status = "error"
        error_code = type(e).__name__
    timings["total_ms"] = round((time.monotonic() - total_start) * 1000, 1)

    payload: dict = {
        "url": redact_url(url),
        "method": method,
        "status": status,
        "status_code": response.status_code if response is not None else None,
        "final_url": redact_url(str(response.url))[:MAX_PAYLOAD_URL_LENGTH] if response is not None else None,
        "redirect_chain": redirect_chain,
        "error_code": error_code,
        **timings,
    }
    if response is not None:
        payload["http_version"] = response.http_version
        payload["content_length"] = len(body)
        payload["body_truncated"] = truncated
        payload["server"] = response.headers.get("server")
    return payload
