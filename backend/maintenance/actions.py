"""Allowlisted maintenance actions (scan-only).

`open-devmgmt` from the Node updater is deliberately **not** ported: launching a
GUI on the host machine from a service process is not appropriate here.
"""
from __future__ import annotations

import json
import time
from typing import Any

from . import history
from .powershell import run_powershell

ALLOWED_ACTIONS: tuple[str, ...] = ("wu-scan", "pnputil-scan")

UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
ACTION_FAILED = "ACTION_FAILED"

WU_TIMEOUT = 120.0
PNPUTIL_TIMEOUT = 60.0

# Read-only: only searches for updates, never installs anything.
WU_SCAN_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "$session=New-Object -ComObject Microsoft.Update.Session;"
    "$searcher=$session.CreateUpdateSearcher();"
    "$r=$searcher.Search(\"IsInstalled=0 and Type='Software'\");"
    "$titles=@();foreach($u in $r.Updates){if($titles.Count -ge 10){break};"
    "$titles+=$u.Title};"
    "@{count=[int]$r.Updates.Count;titles=$titles} | ConvertTo-Json -Compress -Depth 3"
)

PNPUTIL_SCAN_SCRIPT = (
    "$ErrorActionPreference='Continue';"
    "$out=(& pnputil.exe /scan-devices 2>&1 | Out-String);"
    "$code=$LASTEXITCODE;"
    "@{exitCode=[int]$code;output=$out} | ConvertTo-Json -Compress"
)

_TEXT = {
    UNSUPPORTED_ACTION: "action นี้ไม่รองรับ",
    ACTION_FAILED: "รัน action ไม่สำเร็จ",
    "INVALID_ACTION": "ไม่ได้ระบุ action",
}
_HINT = {
    UNSUPPORTED_ACTION: (
        "รองรับเฉพาะ " + ", ".join(ALLOWED_ACTIONS)
        + " (open-devmgmt ถูกปิดโดยเจตนา)"
    ),
    ACTION_FAILED: "ตรวจสอบว่า PowerShell และสิทธิ์ผู้ดูแลระบบใช้งานได้ แล้วลองใหม่",
    "INVALID_ACTION": "ส่ง action เป็น " + " หรือ ".join(ALLOWED_ACTIONS),
}


class ActionError(Exception):
    """Action failure carrying a stable machine-readable code."""

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


def _first_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
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
    if isinstance(value, list):
        value = value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _parse_wu(raw: str) -> dict[str, Any]:
    payload = _first_json(raw)
    try:
        count = int(payload.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    titles = payload.get("titles")
    if isinstance(titles, str):
        titles = [titles]
    if not isinstance(titles, list):
        titles = []
    return {"updateCount": count, "titles": [str(t) for t in titles][:10]}


def _parse_pnputil(raw: str) -> dict[str, Any]:
    payload = _first_json(raw)
    try:
        exit_code = int(payload.get("exitCode") or 0)
    except (TypeError, ValueError):
        exit_code = 0
    output = str(payload.get("output") or "").strip()
    return {"exitCode": exit_code, "output": output[:4000]}


async def run_action(action: str) -> dict[str, Any]:
    """Run an allowlisted scan action and record it in the action history."""
    started = time.perf_counter()
    name = str(action or "").strip()

    if not name:
        history.record(
            "action",
            ok=False,
            duration_ms=_duration_ms(started),
            error="INVALID_ACTION",
        )
        raise ActionError("INVALID_ACTION")

    if name not in ALLOWED_ACTIONS:
        history.record(
            name,
            ok=False,
            duration_ms=_duration_ms(started),
            error=UNSUPPORTED_ACTION,
        )
        raise ActionError(UNSUPPORTED_ACTION)

    try:
        if name == "wu-scan":
            raw = await run_powershell(WU_SCAN_SCRIPT, timeout=WU_TIMEOUT)
            result: dict[str, Any] = _parse_wu(raw)
        else:
            raw = await run_powershell(PNPUTIL_SCAN_SCRIPT, timeout=PNPUTIL_TIMEOUT)
            result = _parse_pnputil(raw)
    except Exception as exc:
        duration = _duration_ms(started)
        history.record(
            name,
            ok=False,
            duration_ms=duration,
            error=str(exc) or ACTION_FAILED,
        )
        raise ActionError(
            ACTION_FAILED,
            status_code=502,
            text=f"{name} ล้มเหลว: {exc}",
        ) from exc

    duration = _duration_ms(started)
    history.record(name, ok=True, duration_ms=duration, detail=result)
    return {
        "ok": True,
        "action": name,
        "result": result,
        "durationMs": duration,
    }
