"""Driver scan ported from updater/lib/scanner.js (read-only CIM queries)."""
from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timezone
from typing import Any

from . import error_codes
from .powershell import (
    DEFAULT_TIMEOUT,
    PowerShellError,
    parse_json_list,
    run_powershell,
)

DRIVER_QUERY = (
    "Get-CimInstance Win32_PnPSignedDriver | "
    "Select-Object DeviceName,DriverVersion,DriverDate,DriverProviderName,Status,DeviceID "
    "| ConvertTo-Json -Depth 2 -Compress"
)

PROBLEM_QUERY = (
    "Get-CimInstance Win32_PnPEntity | "
    "Where-Object { $_.ConfigManagerErrorCode -ne 0 } | "
    "Select-Object Name,DeviceID,ConfigManagerErrorCode "
    "| ConvertTo-Json -Depth 2 -Compress"
)

CACHE_TTL_SECONDS = 30.0

_lock: asyncio.Lock | None = None
_lock_loop: asyncio.AbstractEventLoop | None = None
_state: dict[str, Any] = {"at": 0.0, "result": None}


class ScanError(RuntimeError):
    """Readable scan failure."""


def _get_lock() -> asyncio.Lock:
    global _lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _lock is None or _lock_loop is not loop:
        _lock = asyncio.Lock()
        _lock_loop = loop
    return _lock


def reset_cache() -> None:
    global _lock, _lock_loop
    _state["at"] = 0.0
    _state["result"] = None
    _lock = None
    _lock_loop = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_date(raw: Any) -> str:
    if not raw:
        return ""
    text = str(raw)
    if text.startswith("/Date("):
        inner = text[6:]
        end = inner.find(")")
        digits = inner[:end] if end != -1 else inner
        try:
            return date.fromtimestamp(int(digits) / 1000).isoformat()
        except (ValueError, OSError, OverflowError):
            return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def _describe_error(code: int) -> tuple[str, str]:
    info = error_codes.describe(code)
    text = str(info.get("text") or "")
    hint = str(info.get("hint") or "")
    if not text and code:
        text = f"Device reported problem code {code}"
    return text, hint


def _merge(drivers: list[dict[str, Any]], problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    problem_map: dict[str, Any] = {}
    for item in problems:
        device_id = item.get("DeviceID")
        if device_id:
            problem_map[str(device_id)] = item.get("ConfigManagerErrorCode")

    devices: list[dict[str, Any]] = []
    for index, driver in enumerate(drivers):
        device_id = str(driver.get("DeviceID") or f"idx-{index}")
        raw_code = problem_map.get(device_id)
        raw_status = _as_str(driver.get("Status"))
        has_issue = raw_code is not None or (raw_status != "" and raw_status.upper() != "OK")
        error_code = _as_int(raw_code) if raw_code is not None else 0
        text, hint = _describe_error(error_code)
        devices.append(
            {
                "name": _as_str(driver.get("DeviceName")) or "(unknown device)",
                "status": "issue" if has_issue else "ok",
                "class": _as_str(driver.get("Class")) or "driver",
                "problemCode": error_code,
                "errorText": text,
                "errorHint": hint,
                "deviceId": device_id,
                "driverName": _as_str(driver.get("DriverProviderName")),
                "version": _as_str(driver.get("DriverVersion")),
                "date": normalize_date(driver.get("DriverDate")),
            }
        )
    return devices


def _counts(devices: list[dict[str, Any]]) -> dict[str, int]:
    issues = sum(1 for device in devices if device["status"] == "issue")
    return {"total": len(devices), "ok": len(devices) - issues, "issues": issues}


async def _query_drivers() -> list[dict[str, Any]]:
    try:
        raw = await run_powershell(DRIVER_QUERY, timeout=DEFAULT_TIMEOUT)
    except PowerShellError as exc:
        raise ScanError(f"CIM driver scan failed: {exc}") from exc
    except Exception as exc:
        raise ScanError(f"CIM driver scan failed: {exc}") from exc
    return parse_json_list(raw)


async def _query_problems() -> list[dict[str, Any]]:
    try:
        raw = await run_powershell(PROBLEM_QUERY, timeout=DEFAULT_TIMEOUT)
    except Exception:
        return []
    return parse_json_list(raw)


async def scan(force: bool = False) -> dict[str, Any]:
    async with _get_lock():
        now = time.monotonic()
        cached_result = _state["result"]
        if (
            not force
            and cached_result is not None
            and now - _state["at"] < CACHE_TTL_SECONDS
        ):
            return {**cached_result, "cached": True}

        drivers = await _query_drivers()
        problems = await _query_problems()
        devices = _merge(drivers, problems)
        result = {
            "devices": devices,
            "counts": _counts(devices),
            "scannedAt": _now_iso(),
            "cached": False,
        }
        _state["at"] = time.monotonic()
        _state["result"] = result
        return dict(result)
