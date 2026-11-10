"""Windows startup programs manager (registry Run keys + Startup folders).

Listing is read-only. Toggling is reversible by construction:

* disabling reads the real registry value with `reg query`, writes it to
  `BACKUP_PATH` **before** removing the value, and keeps or rolls back the
  backup entry depending on the *verified* registry state when the removal
  call raises;
* enabling re-adds the backed-up command through the PowerShell registry
  provider and only then removes the backup entry.

Nothing is ever deleted from disk and Task Scheduler is not touched. Every
PowerShell call goes through the injectable `runner` parameter, so tests use a
fake runner and never write to the real registry.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import config

from . import history
from .powershell import run_powershell

log = logging.getLogger(__name__)

Runner = Callable[..., Awaitable[str]]

CONFIRM_PHRASE = "startup"

BACKUP_PATH: Path = Path(str(config.CACHE_DIR)) / "startup_backup.json"

_LIST_TIMEOUT = 30.0
_REG_TIMEOUT = 20.0

LOCATION_HKCU_RUN = "HKCU\\Run"
LOCATION_HKCU_RUNONCE = "HKCU\\RunOnce"
LOCATION_HKLM_RUN = "HKLM\\Run"
LOCATION_HKLM_RUNONCE = "HKLM\\RunOnce"
LOCATION_STARTUP_FOLDER = "startup-folder"

LOCATIONS: tuple[str, ...] = (
    LOCATION_HKCU_RUN,
    LOCATION_HKCU_RUNONCE,
    LOCATION_HKLM_RUN,
    LOCATION_HKLM_RUNONCE,
    LOCATION_STARTUP_FOLDER,
)

WRITABLE_LOCATIONS = frozenset(
    {
        LOCATION_HKCU_RUN,
        LOCATION_HKCU_RUNONCE,
        LOCATION_HKLM_RUN,
        LOCATION_HKLM_RUNONCE,
    }
)

_REGISTRY_PATHS: dict[str, str] = {
    LOCATION_HKCU_RUN: "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    LOCATION_HKCU_RUNONCE: "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
    LOCATION_HKLM_RUN: "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    LOCATION_HKLM_RUNONCE: "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
}

_PROVIDER_PATHS: dict[str, str] = {
    LOCATION_HKCU_RUN: "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    LOCATION_HKCU_RUNONCE: "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
    LOCATION_HKLM_RUN: "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
    LOCATION_HKLM_RUNONCE: "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce",
}

LIST_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "function Emit($loc,$name,$cmd){ if($name){ \"$loc`t$name`t$cmd\" } };"
    "$keys=@("
    "@{Path='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run';Loc='HKCU\\Run'},"
    "@{Path='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce';Loc='HKCU\\RunOnce'},"
    "@{Path='HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run';Loc='HKLM\\Run'},"
    "@{Path='HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce';Loc='HKLM\\RunOnce'}"
    ");"
    "foreach($k in $keys){"
    "$item=Get-Item -LiteralPath $k.Path -ErrorAction SilentlyContinue;"
    "if($item){foreach($n in $item.GetValueNames()){$v=$item.GetValue($n);"
    "if($n -and $v){Emit $k.Loc $n ([string]$v)}}}"
    "};"
    "$folders=@("
    "@{Path=[Environment]::GetFolderPath('Startup');Loc='startup-folder'},"
    "@{Path=[Environment]::GetFolderPath('CommonStartup');Loc='startup-folder'}"
    ");"
    "foreach($f in $folders){"
    "if($f.Path -and (Test-Path -LiteralPath $f.Path)){"
    "foreach($file in (Get-ChildItem -LiteralPath $f.Path -File -ErrorAction SilentlyContinue)){"
    "Emit $f.Loc $file.Name $file.FullName"
    "}}}"
)

_TYPE_RE = re.compile(
    r"\bREG_(?:SZ|EXPAND_SZ|MULTI_SZ|BINARY|DWORD_BIG_ENDIAN|DWORD|QWORD|NONE)\b",
    re.IGNORECASE,
)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f]")

_BACKUP_LOCK = asyncio.Lock()

CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
INVALID_REQUEST = "INVALID_REQUEST"
INVALID_NAME = "INVALID_NAME"
NOT_FOUND = "NOT_FOUND"
UNSUPPORTED_LOCATION = "UNSUPPORTED_LOCATION"
ALREADY_ENABLED = "ALREADY_ENABLED"
WRITE_FAILED = "WRITE_FAILED"
LIST_FAILED = "LIST_FAILED"

_TEXT = {
    CONFIRM_REQUIRED: "ต้องยืนยันก่อนเปิด/ปิดรายการ startup",
    INVALID_REQUEST: "คำขอไม่ถูกต้อง",
    INVALID_NAME: "ชื่อรายการ startup ไม่ปลอดภัย",
    NOT_FOUND: "ไม่พบรายการ startup ที่ระบุ",
    UNSUPPORTED_LOCATION: "ตำแหน่งนี้ไม่รองรับการแก้ไข",
    ALREADY_ENABLED: "รายการนี้เปิดใช้งานอยู่แล้วใน registry",
    WRITE_FAILED: "แก้ไขรายการ startup ไม่สำเร็จ",
    LIST_FAILED: "อ่านรายการ startup ไม่สำเร็จ",
}
_HINT = {
    CONFIRM_REQUIRED: 'ส่ง confirm="startup" มาพร้อมคำขอ (พิมพ์คำว่า startup เพื่อยืนยัน)',
    INVALID_REQUEST: "ส่ง id เป็น string และ enabled เป็น true/false",
    INVALID_NAME: "ชื่อ value ต้องไม่ขึ้นต้นด้วย / และต้องไม่มีอักขระ control (0x00-0x1F)",
    NOT_FOUND: "กดรีเฟรชรายการแล้วลองใหม่อีกครั้ง",
    UNSUPPORTED_LOCATION: "รองรับเฉพาะ HKCU/HKLM Run และ RunOnce (โฟลเดอร์ Startup แก้ไม่ได้)",
    ALREADY_ENABLED: "ค่าจริงยังอยู่ใน registry — กดรีเฟรชก่อนตัดสินใจอีกครั้ง (backup ไม่ถูกแตะ)",
    WRITE_FAILED: "ตรวจสอบสิทธิ์ผู้ดูแลระบบ (HKLM ต้อง elevated) แล้วลองใหม่อีกครั้ง",
    LIST_FAILED: "ตรวจสอบว่า PowerShell ใช้งานได้ แล้วลองใหม่อีกครั้ง",
}


class StartupError(Exception):
    """Startup failure carrying a stable machine-readable code."""

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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _duration_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _record(
    target: str | None,
    *,
    ok: bool,
    started: float,
    detail: Any = None,
    error: str | None = None,
) -> None:
    try:
        history.record(
            "startup",
            target=target,
            ok=ok,
            duration_ms=_duration_ms(started),
            detail=detail,
            error=error,
        )
    except Exception:
        log.warning("startup history write failed", exc_info=True)


def _item_id(location: str, name: str) -> str:
    digest = hashlib.sha1(f"{location}|{name}".encode()).hexdigest()
    return digest[:12]


def _ps_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except ValueError:
        value = None
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                value = json.loads(line)
                break
            except ValueError:
                continue
    return value if isinstance(value, dict) else {}


def _exit_code(raw: str) -> int:
    payload = _payload(raw)
    if "exitCode" not in payload:
        raise RuntimeError("ไม่พบ exitCode จากผลลัพธ์ PowerShell")
    try:
        return int(payload.get("exitCode") or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"exitCode ไม่ถูกต้อง: {payload.get('exitCode')!r}") from exc


def _checked_ok(raw: str, label: str) -> None:
    payload = _payload(raw)
    if payload.get("ok") is True:
        return
    message = str(payload.get("error") or "ไม่ทราบสาเหตุ").strip()
    raise RuntimeError(f"{label} ล้มเหลว: {message}")


def _query_script(reg_path: str, name: str) -> str:
    return (
        "$ErrorActionPreference='SilentlyContinue';"
        f"$out=(& reg.exe query {_ps_literal(reg_path)} /v {_ps_literal(name)} 2>&1 | Out-String);"
        "$code=$LASTEXITCODE;"
        "@{exitCode=[int]$code;output=$out} | ConvertTo-Json -Compress"
    )


def _remove_script(provider_path: str, name: str) -> str:
    return (
        "$ErrorActionPreference='Stop';"
        "try{"
        f"Remove-ItemProperty -LiteralPath {_ps_literal(provider_path)}"
        f" -Name {_ps_literal(name)} -ErrorAction Stop;"
        "@{ok=$true;error=''} | ConvertTo-Json -Compress"
        "}catch{"
        "@{ok=$false;error=([string]$_.Exception.Message)} | ConvertTo-Json -Compress"
        "}"
    )


def _set_script(provider_path: str, name: str, command: str) -> str:
    return (
        "$ErrorActionPreference='Stop';"
        "try{"
        f"Set-ItemProperty -LiteralPath {_ps_literal(provider_path)}"
        f" -Name {_ps_literal(name)} -Value {_ps_literal(command)} -ErrorAction Stop;"
        "@{ok=$true;error=''} | ConvertTo-Json -Compress"
        "}catch{"
        "@{ok=$false;error=([string]$_.Exception.Message)} | ConvertTo-Json -Compress"
        "}"
    )


def _query_value(raw: str) -> str | None:
    """Registry data from a `reg query` payload, or None when the query failed.

    The value is whatever follows the `REG_*` type token on the data line; it is
    never split on whitespace, so value names containing spaces and quoted
    commands survive unchanged.
    """
    try:
        code = _exit_code(raw)
    except RuntimeError:
        return None
    if code != 0:
        return None
    output = str(_payload(raw).get("output") or "")
    for line in output.splitlines():
        match = _TYPE_RE.search(line)
        if match:
            return line[match.end() :].strip()
    return ""


def _require_query_value(raw: str) -> str:
    value = _query_value(raw)
    if value is None:
        raise RuntimeError("reg query ไม่คืนค่า (อาจถูกลบไปแล้ว)")
    return value


def _item(location: str, name: str, command: str, *, enabled: bool) -> dict[str, Any]:
    return {
        "id": _item_id(location, name),
        "name": name,
        "command": command,
        "location": location,
        "enabled": enabled,
        "writable": location in WRITABLE_LOCATIONS,
        "backup_stale": False,
    }


def _parse_listing(raw: str) -> list[dict[str, Any]]:
    """Parse the tab-separated listing; malformed lines are skipped, never raised."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in (raw or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        parts = text.split("\t")
        if len(parts) < 3:
            continue
        location = parts[0].strip()
        name = parts[1].strip()
        command = "\t".join(parts[2:]).strip()
        if location not in LOCATIONS or not name or not command:
            continue
        item = _item(location, name, command, enabled=True)
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
    return items


def _empty_backup() -> dict[str, Any]:
    return {"items": {}}


def _quarantine_backup() -> None:
    target = BACKUP_PATH.with_name(BACKUP_PATH.name + ".corrupt")
    try:
        shutil.copy2(BACKUP_PATH, target)
        log.warning("startup backup is not valid JSON; copied to %s", target)
    except OSError:
        log.warning("startup backup quarantine failed", exc_info=True)


def load_backup() -> dict[str, Any]:
    """Read the backup file defensively; a broken file is quarantined and ignored."""
    try:
        raw = BACKUP_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty_backup()
    except OSError as exc:
        log.warning("startup backup read failed: %s", exc)
        return _empty_backup()
    try:
        data = json.loads(raw)
    except ValueError:
        _quarantine_backup()
        return _empty_backup()
    entries = data.get("items") if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        log.warning("startup backup has no items map: %s", BACKUP_PATH)
        return _empty_backup()
    clean: dict[str, dict[str, str]] = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        location = str(entry.get("location") or "")
        name = str(entry.get("name") or "")
        if location not in LOCATIONS or not name:
            continue
        clean[str(key)] = {
            "location": location,
            "name": name,
            "command": str(entry.get("command") or ""),
            "disabled_at": str(entry.get("disabled_at") or ""),
        }
    return {"items": clean}


def _write_backup(data: dict[str, Any]) -> None:
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = BACKUP_PATH.with_name(BACKUP_PATH.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(BACKUP_PATH)


async def _backup_upsert(item_id: str, entry: dict[str, str]) -> dict[str, Any]:
    """Serially merge one entry into the backup; returns the previous snapshot."""
    async with _BACKUP_LOCK:
        previous = load_backup()
        merged = {"items": {**previous["items"], item_id: entry}}
        _write_backup(merged)
        return previous


async def _backup_remove(item_id: str) -> dict[str, Any]:
    """Serially drop one entry from the backup; returns the previous snapshot."""
    async with _BACKUP_LOCK:
        previous = load_backup()
        remaining = dict(previous["items"])
        remaining.pop(item_id, None)
        _write_backup({"items": remaining})
        return previous


async def _backup_restore(previous: dict[str, Any]) -> None:
    async with _BACKUP_LOCK:
        _write_backup(previous)


async def list_startup(*, runner: Runner = run_powershell) -> dict[str, Any]:
    """Registry Run/RunOnce values plus Startup-folder files, with backup merge."""
    try:
        raw = await runner(LIST_SCRIPT, timeout=_LIST_TIMEOUT)
    except Exception as exc:
        raise StartupError(
            LIST_FAILED,
            status_code=502,
            text=f"อ่านรายการ startup ไม่สำเร็จ: {exc}",
        ) from exc

    by_id = {item["id"]: item for item in _parse_listing(raw)}
    backup = load_backup()
    for item_id, entry in backup["items"].items():
        existing = by_id.get(item_id)
        if existing is not None:
            # The value is still in the registry: the backup entry is stale, the
            # item really is enabled and must not be reported as disabled.
            existing["backup_stale"] = True
            continue
        by_id[item_id] = _item(
            entry["location"], entry["name"], entry["command"], enabled=False
        )

    ordered = sorted(
        by_id.values(), key=lambda item: (item["location"], item["name"].lower())
    )
    return {"items": ordered, "count": len(ordered), "scannedAt": _now_iso()}


async def _probe_present(reg_path: str, name: str, *, runner: Runner) -> bool | None:
    """True/False when the registry value exists, None when it cannot be verified."""
    try:
        raw = await runner(_query_script(reg_path, name), timeout=_REG_TIMEOUT)
        code = _exit_code(raw)
    except Exception:
        log.warning("startup registry probe failed for %r", name, exc_info=True)
        return None
    return code == 0


async def set_enabled(
    item_id: str,
    enabled: bool,
    confirm: str,
    *,
    runner: Runner = run_powershell,
) -> dict[str, Any]:
    """Enable or disable one startup item, with a mandatory confirm phrase."""
    started = time.perf_counter()
    target = str(item_id or "").strip()

    if str(confirm or "").strip() != CONFIRM_PHRASE:
        _record(target, ok=False, started=started, error=CONFIRM_REQUIRED)
        raise StartupError(CONFIRM_REQUIRED)

    if not isinstance(enabled, bool):
        _record(target, ok=False, started=started, error=INVALID_REQUEST)
        raise StartupError(INVALID_REQUEST)

    listing = await list_startup(runner=runner)
    item = next((entry for entry in listing["items"] if entry["id"] == target), None)
    if item is None:
        _record(target, ok=False, started=started, error=NOT_FOUND)
        raise StartupError(NOT_FOUND, status_code=404)

    if not item["writable"]:
        _record(target, ok=False, started=started, error=UNSUPPORTED_LOCATION)
        raise StartupError(UNSUPPORTED_LOCATION)

    name = str(item["name"])
    if name.startswith("/") or _CONTROL_CHARS_RE.search(name):
        _record(
            target,
            ok=False,
            started=started,
            detail={
                "name": name,
                "location": item["location"],
                "command": item["command"],
            },
            error=INVALID_NAME,
        )
        raise StartupError(INVALID_NAME)

    if item["enabled"] is enabled:
        _record(
            target,
            ok=True,
            started=started,
            detail={
                "enabled": enabled,
                "noop": True,
                "location": item["location"],
                "name": name,
                "command": item["command"],
            },
        )
        return {"ok": True, "item": dict(item), "changed": False}

    if enabled:
        return await _enable(item, runner=runner, started=started)
    return await _disable(item, runner=runner, started=started)


async def _disable(
    item: dict[str, Any], *, runner: Runner, started: float
) -> dict[str, Any]:
    item_id = str(item["id"])
    location = str(item["location"])
    name = str(item["name"])
    reg_path = _REGISTRY_PATHS[location]
    provider_path = _PROVIDER_PATHS[location]

    try:
        raw = await runner(_query_script(reg_path, name), timeout=_REG_TIMEOUT)
        value = _require_query_value(raw)
    except Exception as exc:
        _record(
            item_id,
            ok=False,
            started=started,
            detail={
                "enabled": False,
                "location": location,
                "name": name,
                "command": item["command"],
            },
            error=WRITE_FAILED,
        )
        raise StartupError(
            WRITE_FAILED,
            status_code=502,
            text=f"อ่านค่าจริงจาก registry ไม่สำเร็จ: {exc}",
        ) from exc

    command = value or str(item["command"])
    detail = {
        "enabled": False,
        "location": location,
        "name": name,
        "command": command,
    }
    entry = {
        "location": location,
        "name": name,
        "command": command,
        "disabled_at": _now_iso(),
    }
    try:
        previous = await _backup_upsert(item_id, entry)
    except OSError as exc:
        _record(item_id, ok=False, started=started, detail=detail, error=WRITE_FAILED)
        raise StartupError(
            WRITE_FAILED,
            status_code=502,
            text=f"เขียนไฟล์สำรองก่อนลบไม่สำเร็จ: {exc}",
        ) from exc

    try:
        raw = await runner(_remove_script(provider_path, name), timeout=_REG_TIMEOUT)
        _checked_ok(raw, "Remove-ItemProperty")
    except Exception as exc:
        present = await _probe_present(reg_path, name, runner=runner)
        if present is False:
            # The value really is gone (the helper / process failed after the
            # removal): keep the backup so Enable can still restore it.
            log.warning(
                "startup removal reported an error but the value is gone; "
                "keeping the backup entry for %r: %s",
                name,
                exc,
            )
            _record(
                item_id,
                ok=True,
                started=started,
                detail={**detail, "verifiedAfterError": True},
            )
            return {
                "ok": True,
                "item": _item(location, name, command, enabled=False),
                "changed": True,
                "verified": True,
            }
        if present is True:
            try:
                await _backup_restore(previous)
            except OSError:
                log.warning("startup backup rollback failed", exc_info=True)
            _record(
                item_id, ok=False, started=started, detail=detail, error=WRITE_FAILED
            )
            raise StartupError(
                WRITE_FAILED,
                status_code=502,
                text=f"ปิดรายการ startup ไม่สำเร็จ (rollback backup แล้ว): {exc}",
            ) from exc
        log.warning(
            "startup removal state could not be verified; keeping the backup "
            "entry for %r: %s",
            name,
            exc,
        )
        _record(
            item_id,
            ok=False,
            started=started,
            detail={**detail, "stateUnknown": True},
            error=WRITE_FAILED,
        )
        raise StartupError(
            WRITE_FAILED,
            status_code=502,
            text=(
                "ปิดรายการ startup ไม่สำเร็จและตรวจสอบสถานะ registry ไม่ได้"
                f" (เก็บ backup ไว้แล้ว): {exc}"
            ),
        ) from exc

    _record(item_id, ok=True, started=started, detail=detail)
    return {
        "ok": True,
        "item": _item(location, name, command, enabled=False),
        "changed": True,
    }


async def _enable(
    item: dict[str, Any], *, runner: Runner, started: float
) -> dict[str, Any]:
    item_id = str(item["id"])
    backup = load_backup()
    entry = backup["items"].get(item_id)
    if entry is None:
        _record(item_id, ok=False, started=started, error=NOT_FOUND)
        raise StartupError(NOT_FOUND, status_code=404)

    location = str(entry["location"])
    name = str(entry["name"])
    command = str(entry["command"] or item["command"])
    reg_path = _REGISTRY_PATHS.get(location)
    provider_path = _PROVIDER_PATHS.get(location)
    if reg_path is None or provider_path is None:
        _record(item_id, ok=False, started=started, error=UNSUPPORTED_LOCATION)
        raise StartupError(UNSUPPORTED_LOCATION)

    detail = {
        "enabled": True,
        "location": location,
        "name": name,
        "command": command,
    }

    present = await _probe_present(reg_path, name, runner=runner)
    if present is True:
        _record(item_id, ok=False, started=started, detail=detail, error=ALREADY_ENABLED)
        raise StartupError(ALREADY_ENABLED, status_code=409)
    if present is None:
        _record(item_id, ok=False, started=started, detail=detail, error=WRITE_FAILED)
        raise StartupError(
            WRITE_FAILED,
            status_code=502,
            text="ตรวจสอบสถานะ registry ก่อนเปิดรายการ startup ไม่สำเร็จ",
        )

    try:
        raw = await runner(_set_script(provider_path, name, command), timeout=_REG_TIMEOUT)
        _checked_ok(raw, "Set-ItemProperty")
    except Exception as exc:
        _record(item_id, ok=False, started=started, detail=detail, error=WRITE_FAILED)
        raise StartupError(
            WRITE_FAILED,
            status_code=502,
            text=f"เปิดรายการ startup ไม่สำเร็จ: {exc}",
        ) from exc

    try:
        await _backup_remove(item_id)
    except OSError as exc:
        try:
            await runner(_remove_script(provider_path, name), timeout=_REG_TIMEOUT)
        except Exception:
            log.warning("startup enable rollback failed", exc_info=True)
        _record(item_id, ok=False, started=started, detail=detail, error=WRITE_FAILED)
        raise StartupError(
            WRITE_FAILED,
            status_code=502,
            text=f"อัปเดตไฟล์สำรองไม่สำเร็จ จึงย้อนกลับเป็นปิดใช้งาน: {exc}",
        ) from exc

    _record(item_id, ok=True, started=started, detail=detail)
    return {
        "ok": True,
        "item": _item(location, name, command, enabled=True),
        "changed": True,
    }
