"""GeoIP lookup and Tor exit list caching.

Uses the free ip-api.com endpoint and caches results to a local JSON file
with a TTL to stay within free-tier rate limits (45 req/min).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from config import (
    DEFAULT_SUSPICIOUS_COUNTRIES,
    GEOIP_CACHE_FILE,
    GEOIP_CACHE_TTL,
    GEOIP_ENDPOINT,
    GEOIP_RATE_PER_MIN,
    GEOIP_USER_AGENT,
    TOR_CACHE_FILE,
    TOR_EXIT_LIST_URL,
    TOR_REFRESH_INTERVAL,
)

logger = logging.getLogger("dashboard.geoip")

_cache: dict[str, dict[str, Any]] = {}
_cache_lock = asyncio.Lock()
_last_refresh = 0.0
_lookup_window: list[float] = []
_blocking_until = 0.0


def _load_cache() -> None:
    global _cache
    try:
        if GEOIP_CACHE_FILE.exists():
            with GEOIP_CACHE_FILE.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            now = time.time()
            _cache = {k: v for k, v in raw.items()
                       if now - v.get("ts", 0) < GEOIP_CACHE_TTL}
    except (OSError, json.JSONDecodeError):
        _cache = {}


def _persist_cache() -> None:
    try:
        with GEOIP_CACHE_FILE.open("w", encoding="utf-8") as fh:
            json.dump(_cache, fh)
    except OSError:
        pass


_load_cache()


def _is_rate_limited() -> bool:
    global _blocking_until
    now = time.time()
    if _blocking_until > now:
        return True
    # Drop entries older than 60 seconds.
    while _lookup_window and now - _lookup_window[0] > 60:
        _lookup_window.pop(0)
    if len(_lookup_window) >= GEOIP_RATE_PER_MIN:
        _blocking_until = now + 60
        logger.warning("geoIP rate limit hit; pausing for 60s")
        return True
    return False


# In-memory Tor exit set, refreshed daily.
_tor_exits: set[str] = set()
_tor_last_refresh = 0.0
_tor_lock = asyncio.Lock()


async def refresh_tor_exits() -> None:
    """Fetch the latest Tor exit node list (cached)."""
    global _tor_exits, _tor_last_refresh
    now = time.time()
    if now - _tor_last_refresh < TOR_REFRESH_INTERVAL and _tor_exits:
        return
    # Try disk cache first.
    if TOR_CACHE_FILE.exists():
        try:
            data = json.loads(TOR_CACHE_FILE.read_text(encoding="utf-8"))
            if now - data.get("ts", 0) < TOR_REFRESH_INTERVAL:
                _tor_exits = set(data.get("exits", []))
                _tor_last_refresh = data.get("ts", now)
                return
        except (OSError, json.JSONDecodeError):
            pass

    async with _tor_lock:
        # Re-check to avoid duplicate fetch.
        if now - _tor_last_refresh < TOR_REFRESH_INTERVAL and _tor_exits:
            return
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(TOR_EXIT_LIST_URL)
                resp.raise_for_status()
                ips = [line.strip() for line in resp.text.splitlines() if line.strip()]
                _tor_exits = set(ips)
                _tor_last_refresh = now
                TOR_CACHE_FILE.write_text(
                    json.dumps({"ts": now, "exits": list(_tor_exits)}),
                    encoding="utf-8",
                )
                logger.info("Loaded %d Tor exits", len(_tor_exits))
        except Exception as exc:
            logger.warning("Failed to refresh Tor exit list: %s", exc)


def is_tor_exit(ip: str) -> bool:
    return ip in _tor_exits


def is_suspicious_country(country_code: str | None, suspicious: list[str] | None = None) -> bool:
    if not country_code:
        return False
    sus = suspicious or DEFAULT_SUSPICIOUS_COUNTRIES
    return country_code.upper() in sus


async def lookup(ip: str, suspicious: list[str] | None = None) -> dict[str, Any]:
    """Lookup geo info for an IP. Returns cached object when available."""
    if not ip:
        return {"ip": ip, "available": False}
    # Skip private ranges immediately.
    if _is_private(ip):
        return {"ip": ip, "available": False, "private": True}

    async with _cache_lock:
        cached = _cache.get(ip)
        if cached and time.time() - cached.get("ts", 0) < GEOIP_CACHE_TTL:
            return cached

    if _is_rate_limited():
        return {"ip": ip, "available": False, "reason": "rate-limited"}

    url = GEOIP_ENDPOINT.format(ip=ip)
    try:
        async with httpx.AsyncClient(timeout=8.0,
                                     headers={"User-Agent": GEOIP_USER_AGENT}) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                # ip-api returns 403 on rate limit / HTTPS-batch hits.
                return {"ip": ip, "available": False,
                        "reason": f"HTTP {resp.status_code}"}
            data = resp.json()
    except Exception as exc:
        logger.debug("geoIP lookup for %s failed: %s", ip, exc)
        return {"ip": ip, "available": False, "reason": str(exc)}

    _lookup_window.append(time.time())

    if data.get("status") != "success":
        return {"ip": ip, "available": False, "reason": data.get("message", "unknown")}

    result = {
        "ip": ip,
        "available": True,
        "country": data.get("country"),
        "country_code": data.get("countryCode"),
        "region": data.get("regionName"),
        "city": data.get("city"),
        "isp": data.get("isp"),
        "org": data.get("org"),
        "as": data.get("as"),
        "ts": time.time(),
        "suspicious_country": is_suspicious_country(data.get("countryCode"), suspicious),
        "is_tor": is_tor_exit(ip),
    }
    async with _cache_lock:
        _cache[ip] = result
        _persist_cache()
    return result


def _is_private(ip: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved


async def lookup_many(ips: list[str], suspicious: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Rate-limited batch lookup."""
    results: dict[str, dict[str, Any]] = {}
    for ip in ips:
        results[ip] = await lookup(ip, suspicious=suspicious)
        # Small delay so we don't burst the rate limit.
        await asyncio.sleep(0.05)
    return results
