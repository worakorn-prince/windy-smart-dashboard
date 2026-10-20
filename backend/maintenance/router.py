"""Maintenance API router.

Read endpoints (`GET /status`, `GET /scan`) plus guarded write endpoints
(`POST /action`, `/clean`, `/export`, `/relaunch`). Relaunch is opt-in: the
caller must send `{"confirm": "relaunch"}`, and the actual restart is handed to
a detached helper script that waits briefly before replacing the process.
"""
from __future__ import annotations

import inspect
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from . import actions, cleaner, export
from . import history as action_log
from .guards import require_allowed_host, require_csrf
from .scanner import scan
from .system import system_info

try:  # package import (`backend.maintenance.router`)
    from ..security import persistence as security_persistence
except ImportError:  # sys.path-style import (`maintenance.router`)
    from security import persistence as security_persistence

MODULE_NAME = "maintenance"
MODULE_VERSION = "0.3.1"
MODULE_STAGE = "write"

logger = logging.getLogger(__name__)

RELAUNCH_CONFIRM = "relaunch"
RELAUNCH_DELAY_SECONDS = 2.0
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENTRYPOINT = BACKEND_DIR / "main.py"


async def require_admin(request: Request) -> None:
    """Delegate to `main.require_admin` without a module-level circular import.

    `main` imports this router while it is still being initialised, so importing
    `main` at module level here would be circular. The import is therefore done
    lazily on the first request (by then `main` is fully loaded). The relative
    form covers package imports; the bare form covers `sys.path`-style imports
    used by uvicorn/pytest. `main.require_admin` is async, so await it when it
    returns an awaitable (kept defensive so a sync implementation also works).
    """
    try:
        from ..main import require_admin as _require_admin
    except ImportError:
        from main import require_admin as _require_admin
    result = _require_admin(request)
    if inspect.isawaitable(result):
        await result


router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])

_ALLOWED_HOST = Depends(require_allowed_host)
_CSRF = Depends(require_csrf)
_ADMIN = Depends(require_admin)

_WRITE_GUARDS = [_ALLOWED_HOST, _CSRF, _ADMIN]

_EXPORT_KINDS = frozenset({"devices", "history"})
_EXPORT_FORMATS = frozenset({"csv", "json"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_error(action: str, exc: Exception) -> HTTPException:
    message = str(exc).strip() or f"{action} query failed"
    return HTTPException(
        status_code=503,
        detail={
            "code": "READ_FAILED",
            "text": message,
            "hint": "ตรวจสอบว่า PowerShell ใช้งานได้ แล้วลองใหม่อีกครั้ง",
            "action": action,
        },
    )


def _invalid_export() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": "INVALID_EXPORT",
            "text": "kind/format ไม่ถูกต้อง",
            "hint": "kind: devices|history, format: csv|json",
            "action": "export",
        },
    )


def _write_error(action: str, exc: Exception) -> HTTPException:
    code = str(getattr(exc, "code", "") or "WRITE_FAILED")
    status = int(getattr(exc, "status_code", 400) or 400)
    return HTTPException(
        status_code=status,
        detail={
            "code": code,
            "text": str(getattr(exc, "text", "") or exc).strip(),
            "hint": str(getattr(exc, "hint", "") or ""),
            "action": action,
        },
    )


@router.get("/status", dependencies=[_ALLOWED_HOST])
async def status() -> dict[str, object]:
    try:
        info = await system_info()
    except Exception as exc:
        raise _read_error("status", exc) from exc
    body: dict[str, object] = dict(info)
    body.update(
        {
            "ok": True,
            "module": MODULE_NAME,
            "version": MODULE_VERSION,
            "stage": MODULE_STAGE,
            "cached": bool(info.get("cached")),
            "servedAt": _now_iso(),
        }
    )
    return body


@router.get("/scan", dependencies=[_ALLOWED_HOST])
async def scan_endpoint(refresh: int = 0) -> dict[str, object]:
    try:
        result = await scan(force=bool(refresh))
    except Exception as exc:
        raise _read_error("scan", exc) from exc
    body: dict[str, object] = dict(result)
    body.update(
        {
            "ok": True,
            "module": MODULE_NAME,
            "stage": MODULE_STAGE,
            "servedAt": _now_iso(),
        }
    )
    return body


@router.get("/history", dependencies=[_ALLOWED_HOST])
async def history_endpoint(limit: int = 100) -> dict[str, object]:
    rows = action_log.query(limit=max(1, min(int(limit or 100), 500)))
    return {"ok": True, "rows": rows, "count": len(rows), "servedAt": _now_iso()}


@router.post("/action", dependencies=_WRITE_GUARDS)
async def action(payload: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
    data = payload or {}
    try:
        return await actions.run_action(str(data.get("action") or ""))
    except actions.ActionError as exc:
        raise _write_error("action", exc) from exc


@router.get("/clean/summary", dependencies=[_ALLOWED_HOST])
async def clean_summary() -> dict[str, Any]:
    try:
        return await cleaner.summary()
    except cleaner.CleanError as exc:
        raise _write_error("clean-summary", exc) from exc
    except Exception as exc:
        raise _read_error("clean-summary", exc) from exc


@router.post("/clean", dependencies=_WRITE_GUARDS)
async def clean(payload: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
    data = payload or {}
    targets = data.get("targets")
    if targets is None:
        targets = []
    if not isinstance(targets, list):
        targets = []
    confirm = data.get("confirm") is True
    try:
        return await cleaner.clean(targets, confirm=confirm)
    except cleaner.CleanError as exc:
        raise _write_error("clean", exc) from exc


@router.post("/export", dependencies=_WRITE_GUARDS)
async def export_endpoint(
    payload: Annotated[dict[str, Any] | None, Body()] = None,
) -> Response:
    data = payload or {}
    kind = str(data.get("kind") or "devices").strip().lower()
    fmt = str(data.get("format") or "json").strip().lower()

    if kind not in _EXPORT_KINDS or fmt not in _EXPORT_FORMATS:
        raise _invalid_export()

    if kind == "devices":
        try:
            scanned = await scan()
        except Exception as exc:
            raise _read_error("export", exc) from exc
        body, media_type, filename = export.build_payload(
            "devices", devices=scanned.get("devices") or [], format=fmt
        )
    else:
        body, media_type, filename = export.build_payload(
            "history", history_rows=action_log.query(limit=200), format=fmt
        )

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _ps_literal(value: str) -> str:
    """Quote a value as a PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"


def _relaunch_script(pid: int) -> str:
    """PowerShell helper: wait, stop `pid` if alive, start a fresh backend."""
    return (
        "\n".join(
            [
                "# generated by the dashboard maintenance relaunch endpoint",
                "$ErrorActionPreference = 'SilentlyContinue'",
                f"Start-Sleep -Seconds {RELAUNCH_DELAY_SECONDS}",
                f"$target = Get-Process -Id {pid} -ErrorAction SilentlyContinue",
                "if ($target) { Stop-Process -Id $target.Id -Force -ErrorAction SilentlyContinue }",
                "Start-Sleep -Milliseconds 500",
                "Start-Process"
                f" -FilePath {_ps_literal(sys.executable)}"
                f" -ArgumentList {_ps_literal(ENTRYPOINT.name)}"
                f" -WorkingDirectory {_ps_literal(str(BACKEND_DIR))}"
                " -WindowStyle Hidden",
            ]
        )
        + "\n"
    )


def _schedule_relaunch(pid: int) -> Path:
    """Start a detached helper that restarts this process after a short delay.

    The helper lives in `%TEMP%` and is launched with `DETACHED_PROCESS` so it
    survives this process being killed. It mirrors `run.ps1`: the new backend
    runs `sys.executable main.py` with `cwd=backend`. Returns the script path.
    """
    script = Path(tempfile.gettempdir()) / f"dashboard-relaunch-{pid}-{time.time_ns()}.ps1"
    script.write_text(_relaunch_script(pid), encoding="utf-8-sig")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script),
        ],
        cwd=str(BACKEND_DIR),
        creationflags=creationflags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return script


def _audit_relaunch(
    request: Request | None,
    *,
    ok: bool,
    pid: int,
    duration_ms: int = 0,
    script: Path | None = None,
    error: str | None = None,
) -> None:
    """Best-effort audit to both the security log and maintenance history."""
    source_ip = request.client.host if request is not None and request.client else ""
    detail: dict[str, Any] = {"pid": pid, "action": "relaunch"}
    if script is not None:
        detail["script"] = str(script)
    if error:
        detail["error"] = error
    try:
        security_persistence.record_event(
            "relaunch_scheduled" if ok else "relaunch_failed", source_ip, detail
        )
    except Exception:
        logger.warning("relaunch security audit failed", exc_info=True)
    try:
        action_log.record(
            "relaunch", ok=ok, duration_ms=duration_ms, detail=detail, error=error
        )
    except Exception:
        logger.warning("relaunch history audit failed", exc_info=True)


@router.post("/relaunch", dependencies=_WRITE_GUARDS, status_code=202)
async def relaunch(
    request: Request, payload: Annotated[dict[str, Any] | None, Body()] = None
) -> dict[str, object]:
    """Schedule a detached backend restart after an explicit confirmation.

    The caller must send `{"confirm": "relaunch"}`. The response is flushed
    before the helper fires, so the client briefly loses the connection while
    the process is replaced.
    """
    data = payload or {}
    if str(data.get("confirm") or "").strip() != RELAUNCH_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONFIRMATION_REQUIRED",
                "text": "ต้องยืนยันการรีสตาร์ทบริการ",
                "hint": 'ส่ง {"confirm": "relaunch"} หรือพิมพ์คำว่า relaunch ในหน้าจอเพื่อยืนยัน',
                "action": "relaunch",
            },
        )

    pid = os.getpid()
    started = time.monotonic()
    try:
        script = _schedule_relaunch(pid)
    except Exception as exc:
        logger.exception("relaunch scheduling failed")
        _audit_relaunch(
            request, ok=False, pid=pid, error=str(exc) or exc.__class__.__name__
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "RELAUNCH_FAILED",
                "text": "กำหนดการรีสตาร์ทบริการไม่สำเร็จ",
                "hint": "ตรวจสอบสิทธิ์เขียนไฟล์ชั่วคราวและ PowerShell แล้วลองใหม่อีกครั้ง",
                "action": "relaunch",
            },
        ) from exc

    _audit_relaunch(
        request,
        ok=True,
        pid=pid,
        duration_ms=int((time.monotonic() - started) * 1000),
        script=script,
    )
    return {"status": "relaunch_scheduled", "pid": pid}
