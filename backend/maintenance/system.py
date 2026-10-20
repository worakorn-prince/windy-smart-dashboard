"""System information ported from updater/lib/system.js (read-only, no UAC)."""
from __future__ import annotations

import asyncio
import platform
import time
from datetime import UTC, datetime
from typing import Any

from .powershell import (
    PowerShellError,
    parse_json_list,
    run_powershell,
)

SYSTEM_QUERY = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$admin=$false;"
    "try{$id=[Security.Principal.WindowsIdentity]::GetCurrent();"
    "$admin=(New-Object Security.Principal.WindowsPrincipal($id)).IsInRole("
    "[Security.Principal.WindowsBuiltInRole]::Administrator)}"
    "catch{$admin=$false};"
    "$os=Get-CimInstance -ClassName Win32_OperatingSystem;"
    "$cpu=Get-CimInstance -ClassName Win32_Processor | Select-Object -First 1;"
    "$disks=Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' "
    "| Select-Object DeviceID,Size,FreeSpace;"
    "$psv='';try{$psv=$PSVersionTable.PSVersion.ToString()}catch{};"
    "@{isAdmin=[bool]$admin;"
    "osCaption=[string]$os.Caption;osVersion=[string]$os.Version;"
    "osBuild=[string]$os.BuildNumber;osArch=[string]$os.OSArchitecture;"
    "cpuName=[string]$cpu.Name;cpuCores=[int]$cpu.NumberOfCores;"
    "cpuThreads=[int]$cpu.NumberOfLogicalProcessors;"
    "ramTotalBytes=([int64]$os.TotalVisibleMemorySize*1024);"
    "ramFreeBytes=([int64]$os.FreePhysicalMemory*1024);"
    "psVersion=$psv;"
    "disks=@($disks | ForEach-Object { @{name=[string]$_.DeviceID;"
    "sizeBytes=[int64]$_.Size;freeBytes=[int64]$_.FreeSpace} })"
    "} | ConvertTo-Json -Depth 4 -Compress"
)

SYSTEM_TIMEOUT_SECONDS = 30.0
CACHE_TTL_SECONDS = 60.0

_lock: asyncio.Lock | None = None
_lock_loop: asyncio.AbstractEventLoop | None = None
_state: dict[str, Any] = {"at": 0.0, "data": None}


class SystemInfoError(RuntimeError):
    """Readable system-info failure."""


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
    _state["data"] = None
    _lock = None
    _lock_loop = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _percent(free: int, total: int) -> float | None:
    if total <= 0:
        return None
    used = max(total - free, 0)
    return round(used / total * 100, 1)


def _build(raw: dict[str, Any]) -> dict[str, Any]:
    is_admin = raw.get("isAdmin")
    ram_total = _as_int(raw.get("ramTotalBytes"))
    ram_free = _as_int(raw.get("ramFreeBytes"))
    disks: list[dict[str, Any]] = []
    for disk in raw.get("disks") or []:
        if not isinstance(disk, dict):
            continue
        size = _as_int(disk.get("sizeBytes"))
        free = _as_int(disk.get("freeBytes"))
        disks.append(
            {
                "name": _as_str(disk.get("name")),
                "sizeBytes": size,
                "freeBytes": free,
                "usedPercent": _percent(free, size),
            }
        )
    return {
        "isAdmin": is_admin if isinstance(is_admin, bool) else None,
        "os": {
            "caption": _as_str(raw.get("osCaption")),
            "version": _as_str(raw.get("osVersion")),
            "build": _as_str(raw.get("osBuild")),
            "arch": _as_str(raw.get("osArch")),
        },
        "cpu": {
            "name": _as_str(raw.get("cpuName")),
            "cores": _as_int(raw.get("cpuCores")),
            "threads": _as_int(raw.get("cpuThreads")),
        },
        "memory": {
            "totalBytes": ram_total,
            "freeBytes": ram_free,
            "usedPercent": _percent(ram_free, ram_total),
        },
        "disks": disks,
        "psVersion": _as_str(raw.get("psVersion")),
        "pythonVersion": platform.python_version(),
        "collectedAt": _now_iso(),
        "cached": False,
    }


async def system_info(force: bool = False) -> dict[str, Any]:
    async with _get_lock():
        now = time.monotonic()
        cached_data = _state["data"]
        if (
            not force
            and cached_data is not None
            and now - _state["at"] < CACHE_TTL_SECONDS
        ):
            return {**cached_data, "cached": True}

        try:
            raw = await run_powershell(SYSTEM_QUERY, timeout=SYSTEM_TIMEOUT_SECONDS)
        except PowerShellError as exc:
            raise SystemInfoError(f"system info query failed: {exc}") from exc
        except Exception as exc:
            raise SystemInfoError(f"system info query failed: {exc}") from exc

        rows = parse_json_list(raw)
        data = _build(rows[0] if rows else {})
        _state["at"] = time.monotonic()
        _state["data"] = data
        return dict(data)
