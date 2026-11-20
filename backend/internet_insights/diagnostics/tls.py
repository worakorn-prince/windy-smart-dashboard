"""TLS handshake diagnostic."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import ssl
import time
from datetime import UTC, datetime

from . import PROBE_TIMEOUT_CAP_MS, validate_target, validate_timeout_ms


class _TlsResult:
    __slots__ = ("cert_expiry", "cert_not_after", "cipher", "version")

    def __init__(self) -> None:
        self.version: str | None = None
        self.cipher: str | None = None
        self.cert_expiry: str | None = None
        self.cert_not_after: float | None = None


def _extract_peer_info(sock: ssl.SSLSocket, result: _TlsResult) -> None:
    with contextlib.suppress(Exception):
        result.version = sock.version()
    with contextlib.suppress(Exception):
        cipher = sock.cipher()
        if cipher:
            result.cipher = cipher[0]
    with contextlib.suppress(Exception):
        cert = sock.getpeercert()
        if cert and cert.get("notAfter"):
            not_after_ts = ssl.cert_time_to_seconds(cert["notAfter"])
            result.cert_not_after = not_after_ts
            result.cert_expiry = datetime.fromtimestamp(not_after_ts, tz=UTC).isoformat()


def _handshake_sync(host: str, port: int, timeout_sec: float, server_name: str | None, context: ssl.SSLContext) -> _TlsResult:
    result = _TlsResult()
    sni = server_name or host
    with socket.create_connection((host, port), timeout=timeout_sec) as raw:
        raw.settimeout(timeout_sec)
        with context.wrap_socket(raw, server_hostname=sni) as tls_sock:
            _extract_peer_info(tls_sock, result)
    return result


async def tls_handshake(
    target: str,
    port: int = 443,
    timeout_ms: int = 5000,
    server_name: str | None = None,
) -> dict:
    """Perform a TLS handshake; returns version, cipher and certificate validity."""
    cleaned = validate_target(target)
    if server_name:
        validate_target(server_name)
    if not 1 <= port <= 65535:
        raise ValueError(f"Port out of range (1-65535): {port}")
    timeout_ms = validate_timeout_ms(timeout_ms, PROBE_TIMEOUT_CAP_MS)
    timeout_sec = timeout_ms / 1000
    context = ssl.create_default_context()

    start = time.monotonic()
    status = "success"
    error_code: str | None = None
    info = _TlsResult()
    try:
        info = await asyncio.wait_for(
            asyncio.to_thread(_handshake_sync, cleaned, port, timeout_sec, server_name, context),
            timeout=timeout_sec + 0.5,
        )
    except TimeoutError:
        status = "timeout"
        error_code = "TimeoutError"
    except ConnectionRefusedError:
        status = "refused"
        error_code = "ConnectionRefusedError"
    except ssl.SSLError as e:
        status = "error"
        error_code = type(e).__name__
    except OSError as e:
        status = "error"
        error_code = type(e).__name__
    except Exception as e:
        status = "error"
        error_code = type(e).__name__
    duration_ms = round((time.monotonic() - start) * 1000, 1)

    cert_valid: bool | None = None
    if info.cert_not_after is not None:
        cert_valid = info.cert_not_after > time.time()

    return {
        "target": cleaned,
        "port": port,
        "duration_ms": duration_ms,
        "version": info.version,
        "cipher": info.cipher,
        "cert_valid": cert_valid,
        "cert_expiry": info.cert_expiry,
        "status": status,
        "error_code": error_code,
    }
