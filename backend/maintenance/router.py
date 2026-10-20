"""Maintenance API router.

Read endpoints (`GET /status`, `GET /scan`) plus guarded write endpoints
(`POST /action`, `/clean`, `/export`). `POST /relaunch` stays deliberately
disabled: killing the dashboard process and re-elevating through UAC from a web
request is too risky — use `run.ps1` instead.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from . import actions, cleaner, error_codes, export
from . import history as action_log
from .guards import require_allowed_host, require_csrf
from .scanner import scan
from .system import system_info

MODULE_NAME = "maintenance"
MODULE_VERSION = "0.3.1"
MODULE_STAGE = "write"

RELAUNCH_DISABLED = "RELAUNCH_DISABLED"
RELAUNCH_TEXT = "ยังไม่เปิดให้รีสตาร์ตแดชบอร์ดจาก API"
RELAUNCH_HINT = "รีสตาร์ตเองด้วย run.ps1 (ต้องยืนยัน UAC บนเครื่อง host)"


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
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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
async def action(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
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
async def clean(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
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
    payload: dict[str, Any] | None = Body(default=None),
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


@router.post("/relaunch", dependencies=_WRITE_GUARDS)
async def relaunch() -> None:
    raise HTTPException(
        status_code=501,
        detail={
            "code": RELAUNCH_DISABLED,
            "text": RELAUNCH_TEXT,
            "hint": RELAUNCH_HINT,
            "action": "relaunch",
        },
    )
