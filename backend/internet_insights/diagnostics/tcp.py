"""TCP connect diagnostic."""

from __future__ import annotations

import asyncio
import socket
import time

from . import PROBE_TIMEOUT_CAP_MS, validate_target, validate_timeout_ms

MIN_PORT = 1
MAX_PORT = 65535


def _connect_sync(host: str, port: int, timeout_sec: float) -> None:
    with socket.create_connection((host, port), timeout=timeout_sec):
        return None


async def tcp_connect(target: str, port: int, timeout_ms: int = 3000) -> dict:
    """Connect to target:port; returns payload with status success|refused|timeout|error."""
    cleaned = validate_target(target)
    if not MIN_PORT <= port <= MAX_PORT:
        raise ValueError(f"Port out of range ({MIN_PORT}-{MAX_PORT}): {port}")
    timeout_ms = validate_timeout_ms(timeout_ms, PROBE_TIMEOUT_CAP_MS)
    timeout_sec = timeout_ms / 1000

    start = time.monotonic()
    status = "success"
    error_code: str | None = None
    try:
        await asyncio.wait_for(asyncio.to_thread(_connect_sync, cleaned, port, timeout_sec), timeout=timeout_sec + 0.5)
    except TimeoutError:
        status = "timeout"
        error_code = "TimeoutError"
    except ConnectionRefusedError:
        status = "refused"
        error_code = "ConnectionRefusedError"
    except OSError as e:
        status = "error"
        error_code = type(e).__name__
    except Exception as e:
        status = "error"
        error_code = type(e).__name__
    duration_ms = round((time.monotonic() - start) * 1000, 1)

    return {
        "target": cleaned,
        "port": port,
        "duration_ms": duration_ms,
        "status": status,
        "error_code": error_code,
    }
