"""Path MTU discovery via Windows ping with DF flag and bounded binary search."""

from __future__ import annotations

import asyncio
import contextlib

from . import PROBE_TIMEOUT_CAP_MS, validate_target, validate_timeout_ms

MAX_PROBES = 10
MIN_MTU_SIZE = 68
MAX_MTU_SIZE = 1500


async def _ping_size_probe(target: str, size: int, timeout_sec: float) -> str:
    """Run `ping -n 1 -f -l <size>` once; returns success|timeout|error (returncode 0 = success)."""
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "ping",
                "-n",
                "1",
                "-f",
                "-l",
                str(size),
                target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout_sec,
        )
    except TimeoutError:
        return "timeout"
    except OSError:
        return "error"
    try:
        await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError, OSError):
            proc.kill()
        return "timeout"
    return "success" if proc.returncode == 0 else "error"


async def mtu_discovery(
    target: str,
    timeout_ms: int = 3000,
    max_size: int = 1500,
    min_size: int = 576,
) -> dict:
    """Binary-search the path MTU using DF-set pings; bounded to MAX_PROBES probes."""
    cleaned = validate_target(target)
    timeout_ms = validate_timeout_ms(timeout_ms, PROBE_TIMEOUT_CAP_MS)
    if min_size < MIN_MTU_SIZE:
        raise ValueError(f"min_size must be >= {MIN_MTU_SIZE}: {min_size}")
    if max_size > MAX_MTU_SIZE:
        raise ValueError(f"max_size must be <= {MAX_MTU_SIZE}: {max_size}")
    if min_size > max_size:
        raise ValueError(f"min_size must not exceed max_size: {min_size} > {max_size}")
    timeout_sec = timeout_ms / 1000

    probes: list[dict] = []
    path_mtu: int | None = None
    statuses: list[str] = []

    async def probe(size: int) -> str:
        status = await _ping_size_probe(cleaned, size, timeout_sec)
        probes.append({"size": size, "status": status})
        statuses.append(status)
        if status == "success":
            nonlocal path_mtu
            path_mtu = max(path_mtu or 0, size)
        return status

    test_size = max_size
    first_status = await probe(max_size)
    if first_status != "success":
        lo, hi = min_size, max_size - 1
        while lo <= hi and len(probes) < MAX_PROBES:
            mid = (lo + hi) // 2
            if await probe(mid) == "success":
                lo = mid + 1
            else:
                hi = mid - 1

    if path_mtu is not None:
        status = "success"
    elif any(s == "timeout" for s in statuses):
        status = "timeout"
    else:
        status = "error"

    return {
        "target": cleaned,
        "test_size": test_size,
        "path_mtu": path_mtu,
        "status": status,
        "probes": probes,
    }
