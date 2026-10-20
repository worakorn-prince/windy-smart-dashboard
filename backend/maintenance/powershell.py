"""Async read-only PowerShell runner ported from updater/lib/powershell.js."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("dashboard.maintenance.powershell")

PS_EXE = "powershell.exe"
BASE_ARGS = (
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
)
DEFAULT_TIMEOUT = 30.0


class PowerShellError(RuntimeError):
    """Readable PowerShell failure."""


class PowerShellTimeout(PowerShellError, TimeoutError):
    """Raised after the child process was killed on timeout."""


def _decode(data: bytes | None) -> str:
    return (data or b"").decode("utf-8", errors="replace")


def _kill(proc: Any) -> None:
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


async def run_powershell(script: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    if not isinstance(script, str) or not script.strip():
        raise PowerShellError("PowerShell script must be a non-empty string")
    timeout = float(timeout)
    try:
        proc = await asyncio.create_subprocess_exec(
            PS_EXE,
            *BASE_ARGS,
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise PowerShellError("powershell.exe not found on this system") from None
    except OSError as exc:
        raise PowerShellError(f"failed to start powershell.exe: {exc}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        _kill(proc)
        try:
            await proc.wait()
        except (ProcessLookupError, OSError):
            pass
        raise PowerShellTimeout(
            f"PowerShell query timed out after {timeout:g}s and was terminated"
        ) from None

    out = _decode(stdout).strip()
    err = _decode(stderr).strip()
    code = proc.returncode
    if err:
        logger.debug("PowerShell stderr (exit %s): %s", code, err[:500])
    if code not in (0, None) and not out:
        raise PowerShellError(
            f"PowerShell exited with code {code}: {err[:500] or 'no stderr output'}"
        )
    return out


def _as_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _try_load(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return _MISSING


_MISSING = object()


def parse_json_list(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip().lstrip("\ufeff").strip()
    if not text:
        return []

    data = _try_load(text)
    if data is not _MISSING:
        return _as_list(data)

    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped[0] not in "[{":
            continue
        chunk = "\n".join(lines[index:]).strip()
        data = _try_load(chunk)
        if data is not _MISSING:
            return _as_list(data)

    for start_char, end_char in (("[", "]"), ("{", "}")):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end > start:
            data = _try_load(text[start : end + 1])
            if data is not _MISSING:
                return _as_list(data)

    items: list[dict[str, Any]] = []
    for line in lines:
        candidate = line.strip().rstrip(",")
        if candidate[:1] in ("{", "["):
            data = _try_load(candidate)
            if isinstance(data, dict):
                items.append(data)
    if items:
        return items

    raise PowerShellError("unparseable PowerShell JSON output")
