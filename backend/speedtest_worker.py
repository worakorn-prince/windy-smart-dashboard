"""On-demand Internet speed test using Cloudflare's public endpoint.

We avoid speedtest-cli because Ookla's HTTP API started blocking that
library's requests (HTTP 403). Cloudflare's speed.cloudflare.com endpoint
is free, has no API key, and is the same one fast.com and others use.

Endpoints used:
  Latency:   https://speed.cloudflare.com/cdn-cgi/trace       (text body)
  Download:  https://speed.cloudflare.com/__down?bytes=<N>     (binary stream)
  Upload:    https://speed.cloudflare.com/__up                  (POST binary)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("dashboard.speedtest")

TRACE_URL = "https://speed.cloudflare.com/cdn-cgi/trace"
DOWN_URL = "https://speed.cloudflare.com/__down?bytes={n}"
UP_URL = "https://speed.cloudflare.com/__up"

# Bytes for the throughput tests. 25 MB download / 10 MB upload gives a
# good balance between measurement quality and bandwidth used.
DOWN_BYTES = 25 * 1024 * 1024
UP_BYTES = 10 * 1024 * 1024
TIMEOUT = 60.0
LATENCY_PROBES = 5


async def _measure_latency() -> float | None:
    """Return median latency in ms to the trace endpoint."""
    samples: list[float] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(LATENCY_PROBES):
            t0 = time.monotonic()
            try:
                r = await client.get(TRACE_URL)
                r.raise_for_status()
                samples.append(round((time.monotonic() - t0) * 1000, 1))
            except Exception:
                continue
    if not samples:
        return None
    samples.sort()
    return samples[len(samples) // 2]


async def _measure_download() -> tuple[float, str | None]:
    """Return (mbps, server_loc) from a download test."""
    url = DOWN_URL.format(n=DOWN_BYTES)
    t0 = time.monotonic()
    received = 0
    server_loc: str | None = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # First, a tiny trace request to grab the POP location code.
        try:
            tr = await client.get(TRACE_URL)
            if tr.status_code == 200:
                for line in tr.text.splitlines():
                    if line.startswith("loc="):
                        server_loc = line.split("=", 1)[1]
                        break
        except Exception:
            pass
        # Now do the actual download.
        try:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes():
                    if chunk:
                        received += len(chunk)
        except Exception as exc:
            logger.warning("download test failed after %d bytes: %s", received, exc)
    dt = time.monotonic() - t0
    if dt <= 0 or received == 0:
        return 0.0, server_loc
    mbps = (received * 8) / dt / 1_000_000
    return round(mbps, 2), server_loc


async def _measure_upload() -> float:
    """Return Mbps from an upload test."""
    payload = b"\0" * UP_BYTES
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=TIMEOUT,
                                  headers={"Content-Type": "application/octet-stream"}) as client:
        try:
            r = await client.post(UP_URL, content=payload)
            r.raise_for_status()
        except Exception as exc:
            logger.warning("upload test failed: %s", exc)
            return 0.0
    dt = time.monotonic() - t0
    if dt <= 0:
        return 0.0
    return round((UP_BYTES * 8) / dt / 1_000_000, 2)


async def run_speedtest_async() -> dict[str, Any]:
    """Run the full test: latency, then download, then upload."""
    start = time.time()
    try:
        ping_ms = await _measure_latency()
        download_mbps, server_loc = await _measure_download()
        upload_mbps = await _measure_upload()
        return {
            "ok": True,
            "ping_ms": ping_ms,
            "download_mbps": download_mbps,
            "upload_mbps": upload_mbps,
            "download_bps": int(download_mbps * 1_000_000 / 8) if download_mbps else 0,
            "upload_bps": int(upload_mbps * 1_000_000 / 8) if upload_mbps else 0,
            "server": {
                "name": "Cloudflare",
                "sponsor": "Cloudflare, Inc.",
                "country": "Cloudflare Edge",
                "loc": server_loc,
            },
            "bytes_downloaded": DOWN_BYTES,
            "bytes_uploaded": UP_BYTES,
            "timestamp": start,
            "duration_ms": round((time.time() - start) * 1000, 0),
        }
    except Exception as exc:
        logger.exception("speedtest failed")
        return {"ok": False, "error": str(exc), "timestamp": start}


# Backward-compatible sync API (used nowhere currently, but kept for parity).
def _run_speedtest() -> dict[str, Any]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(run_speedtest_async())
    finally:
        loop.close()
