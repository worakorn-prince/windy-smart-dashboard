"""Disk cleanup targets ported from `updater/lib/cleaner.js`.

The PowerShell scripts are byte-for-byte ports of the Node originals so the
numbers reported here match the desktop updater. Nothing runs unless the caller
explicitly passes `confirm=True` and an allowlisted target list.
"""
from __future__ import annotations

import json
import time
from typing import Any

from . import history
from .powershell import run_powershell

ALLOWED_TARGETS: tuple[str, ...] = ("user-temp", "windows-temp", "recycle-bin")

CLEAN_TIMEOUT = 120.0
SUMMARY_TIMEOUT = 90.0

CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
INVALID_TARGETS = "INVALID_TARGETS"
CLEAN_FAILED = "CLEAN_FAILED"
SUMMARY_FAILED = "SUMMARY_FAILED"

CLEAN_USER_TEMP_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$p=$env:TEMP;$del=0;$skip=0;$bytes=[long]0;"
    "foreach($f in (Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue)){"
    "try{$b=[long]$f.Length;Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop;$del++;$bytes+=$b}"
    "catch{$skip++}};"
    "@{filesDeleted=$del;filesSkipped=$skip;bytesFreed=$bytes} | ConvertTo-Json -Compress"
)

CLEAN_WINDOWS_TEMP_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$p=Join-Path $env:SystemRoot 'Temp';$del=0;$skip=0;$bytes=[long]0;"
    "foreach($f in (Get-ChildItem -LiteralPath $p -Recurse -Force -File -ErrorAction SilentlyContinue)){"
    "try{$b=[long]$f.Length;Remove-Item -LiteralPath $f.FullName -Force -ErrorAction Stop;$del++;$bytes+=$b}"
    "catch{$skip++}};"
    "@{filesDeleted=$del;filesSkipped=$skip;bytesFreed=$bytes} | ConvertTo-Json -Compress"
)

CLEAN_RECYCLE_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';$before=[long]0;"
    "foreach($d in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)){"
    "$rp=Join-Path $d.Root '$Recycle.Bin';"
    "if(Test-Path -LiteralPath $rp){"
    "$m=Get-ChildItem -LiteralPath $rp -Recurse -Force -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum;"
    "if($m.Sum){$before+=[long]$m.Sum}}};"
    "try{Clear-RecycleBin -Force -ErrorAction Stop}catch{};"
    "@{filesDeleted=0;filesSkipped=0;bytesFreed=$before} | ConvertTo-Json -Compress"
)

SUMMARY_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$out=@();"
    "$ut=$env:TEMP;"
    "if($ut){"
    "$m=Get-ChildItem -LiteralPath $ut -Recurse -Force -File -ErrorAction SilentlyContinue"
    " | Measure-Object -Property Length -Sum;"
    "$b=[long]0;if($m.Sum){$b=[long]$m.Sum};"
    "$out+=[pscustomobject]@{target='user-temp';path=$ut;bytes=$b}};"
    "$wt=Join-Path $env:SystemRoot 'Temp';"
    "if($wt){"
    "$m=Get-ChildItem -LiteralPath $wt -Recurse -Force -File -ErrorAction SilentlyContinue"
    " | Measure-Object -Property Length -Sum;"
    "$b=[long]0;if($m.Sum){$b=[long]$m.Sum};"
    "$out+=[pscustomobject]@{target='windows-temp';path=$wt;bytes=$b}};"
    "foreach($d in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)){"
    "$rp=Join-Path $d.Root '$Recycle.Bin';"
    "if(Test-Path -LiteralPath $rp){"
    "$m=Get-ChildItem -LiteralPath $rp -Recurse -Force -File -ErrorAction SilentlyContinue"
    " | Measure-Object -Property Length -Sum;"
    "$b=[long]0;if($m.Sum){$b=[long]$m.Sum};"
    "$out+=[pscustomobject]@{target='recycle-bin';path=$rp;bytes=$b}}};"
    "ConvertTo-Json -InputObject @($out) -Compress"
)

CLEAN_SCRIPTS: dict[str, str] = {
    "user-temp": CLEAN_USER_TEMP_SCRIPT,
    "windows-temp": CLEAN_WINDOWS_TEMP_SCRIPT,
    "recycle-bin": CLEAN_RECYCLE_SCRIPT,
}

_TEXT = {
    CONFIRM_REQUIRED: "ต้องยืนยันก่อนลบไฟล์ (confirm=true)",
    INVALID_TARGETS: "targets ไม่ถูกต้อง",
    CLEAN_FAILED: "ลบไฟล์ไม่สำเร็จ",
    SUMMARY_FAILED: "อ่านขนาดไฟล์ไม่สำเร็จ",
}
_HINT = {
    CONFIRM_REQUIRED: "ส่ง confirm=true มาพร้อม targets เพื่อยืนยันการลบ",
    INVALID_TARGETS: "อนุญาตเฉพาะ " + ", ".join(ALLOWED_TARGETS),
    CLEAN_FAILED: "ตรวจสอบสิทธิ์ผู้ดูแลระบบและลองใหม่อีกครั้ง",
    SUMMARY_FAILED: "ตรวจสอบว่า PowerShell ใช้งานได้ แล้วลองใหม่อีกครั้ง",
}


class CleanError(Exception):
    """Cleanup failure carrying a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int = 400,
        hint: str | None = None,
        text: str | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.text = text or _TEXT.get(code, code)
        self.hint = hint or _HINT.get(code, "")
        super().__init__(self.text)


def _duration_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _rows(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except ValueError:
        value = None
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line.startswith(("{", "[")):
                continue
            try:
                value = json.loads(line)
                break
            except ValueError:
                continue
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def _norm_result(raw: str) -> dict[str, int]:
    rows = _rows(raw)
    row = rows[0] if rows else {}

    def _int(key: str) -> int:
        try:
            return max(0, int(row.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    return {
        "filesDeleted": _int("filesDeleted"),
        "filesSkipped": _int("filesSkipped"),
        "bytesFreed": _int("bytesFreed"),
    }


def _valid_targets(targets: Any) -> list[str]:
    if not isinstance(targets, (list, tuple)) or not targets:
        return []
    cleaned: list[str] = []
    for item in targets:
        if not isinstance(item, str):
            return []
        name = item.strip()
        if name not in ALLOWED_TARGETS:
            return []
        if name not in cleaned:
            cleaned.append(name)
    return cleaned


async def clean(targets: list[str], *, confirm: bool) -> dict[str, Any]:
    """Delete the requested allowlisted targets. Requires `confirm is True`."""
    started = time.perf_counter()
    if confirm is not True:
        history.record(
            "clean",
            ok=False,
            duration_ms=_duration_ms(started),
            detail={"targets": targets},
            error=CONFIRM_REQUIRED,
        )
        raise CleanError(CONFIRM_REQUIRED)

    requested = _valid_targets(targets)
    if not requested:
        history.record(
            "clean",
            ok=False,
            duration_ms=_duration_ms(started),
            detail={"targets": targets},
            error=INVALID_TARGETS,
        )
        raise CleanError(INVALID_TARGETS)

    details: dict[str, dict[str, int]] = {}
    totals = {"filesDeleted": 0, "filesSkipped": 0, "bytesFreed": 0}
    errors: dict[str, str] = {}

    for target in requested:
        target_started = time.perf_counter()
        try:
            raw = await run_powershell(CLEAN_SCRIPTS[target], timeout=CLEAN_TIMEOUT)
            result = _norm_result(raw)
        except Exception as exc:
            errors[target] = str(exc) or CLEAN_FAILED
            history.record(
                "clean",
                target=target,
                ok=False,
                duration_ms=_duration_ms(target_started),
                error=errors[target],
            )
            continue

        details[target] = result
        for key in totals:
            totals[key] += result[key]
        history.record(
            "clean",
            target=target,
            ok=True,
            duration_ms=_duration_ms(target_started),
            detail=result,
        )

    duration = _duration_ms(started)
    if errors and not details:
        raise CleanError(
            CLEAN_FAILED,
            status_code=502,
            text="ลบไฟล์ไม่สำเร็จ: " + "; ".join(f"{k}: {v}" for k, v in errors.items()),
        )

    body: dict[str, Any] = {
        "ok": not errors,
        "filesDeleted": totals["filesDeleted"],
        "filesSkipped": totals["filesSkipped"],
        "bytesFreed": totals["bytesFreed"],
        "details": details,
        "total": dict(totals),
        "targets": requested,
        "durationMs": duration,
    }
    if errors:
        body["errors"] = errors
    return body


async def summary() -> dict[str, Any]:
    """Report how much space the cleanup targets currently occupy (read-only)."""
    started = time.perf_counter()
    try:
        raw = await run_powershell(SUMMARY_SCRIPT, timeout=SUMMARY_TIMEOUT)
        rows = _rows(raw)
    except Exception as exc:
        history.record(
            "clean-summary",
            ok=False,
            duration_ms=_duration_ms(started),
            error=SUMMARY_FAILED,
        )
        raise CleanError(
            SUMMARY_FAILED,
            status_code=502,
            text="อ่านขนาดไฟล์ไม่สำเร็จ: " + str(exc),
        ) from exc

    categories: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    total = 0
    for row in rows:
        target = str(row.get("target") or "").strip()
        path = str(row.get("path") or "").strip()
        try:
            size = max(0, int(row.get("bytes") or 0))
        except (TypeError, ValueError):
            size = 0
        key = target or path
        if not key:
            continue
        if key in index:
            categories[index[key]]["bytes"] += size
            total += size
            continue
        index[key] = len(categories)
        categories.append({"target": target, "path": path, "bytes": size})
        total += size

    duration = _duration_ms(started)
    history.record(
        "clean-summary",
        ok=True,
        duration_ms=duration,
        detail={"totalBytes": total, "categories": len(categories)},
    )
    return {
        "ok": True,
        "categories": categories,
        "totalBytes": total,
        "durationMs": duration,
    }
