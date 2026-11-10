"""Windows Update status for the maintenance page.

Read-only and fully best-effort:

* `pendingReboot` comes from one PowerShell read of the four classic registry
  locations (CBS, Windows Update, `PendingFileRenameOperations`);
* `installed` lists the last five hotfixes;
* `lastScan` is read from the maintenance action history (`wu-scan` rows) so the
  page shows the result of the most recent scan without re-running it.

Every PowerShell call goes through the injectable `runner` parameter, so tests
never touch the real machine. A failing section is surfaced under `errors` and
never fails the whole payload.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from . import actions, history
from .powershell import parse_json_list, run_powershell

Runner = Callable[..., Awaitable[str]]

PENDING_TIMEOUT = 30.0
HOTFIX_TIMEOUT = 45.0

REASON_CBS = "CBS"
REASON_WU = "WU"
REASON_RENAME = "PendingFileRename"

PENDING_REASONS: tuple[str, ...] = (REASON_CBS, REASON_WU, REASON_RENAME)

HOTFIX_LIMIT = 5
LAST_SCAN_WINDOW = 200

# Read-only registry probes. `Test-Path` returns $false when the key is absent or
# unreadable; `PendingFileRenameOperations` only counts when it actually holds
# entries (an empty value is a leftover, not a pending reboot).
PENDING_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$cbs=Test-Path -LiteralPath "
    "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Component Based Servicing\\RebootPending';"
    "$wu=Test-Path -LiteralPath "
    "'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\WindowsUpdate\\Auto Update\\RebootRequired';"
    "$renames=0;"
    "$pending=(Get-ItemProperty -LiteralPath "
    "'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager'"
    " -Name 'PendingFileRenameOperations' -ErrorAction SilentlyContinue).PendingFileRenameOperations;"
    "if($pending){$renames=@($pending | Where-Object { $_ -and [string]$_ -ne '' }).Count};"
    "@{cbs=[bool]$cbs;wu=[bool]$wu;renames=[int]$renames} | ConvertTo-Json -Compress"
)

HOTFIX_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$items=@(Get-HotFix -ErrorAction SilentlyContinue | Sort-Object InstalledOn -Descending "
    "| Select-Object -First 5 HotFixID,Description,InstalledOn);"
    "$out=@();"
    "foreach($h in $items){"
    "$on='';"
    "if($h.InstalledOn){try{$on=([datetime]$h.InstalledOn).ToString('yyyy-MM-dd')}"
    "catch{$on=[string]$h.InstalledOn}};"
    "$out+=[pscustomobject]@{id=[string]$h.HotFixID;"
    "description=[string]$h.Description;installedOn=$on}};"
    "ConvertTo-Json -InputObject @($out) -Compress -Depth 3"
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _message(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__


def _load(raw: str) -> list[dict[str, Any]] | None:
    """Tolerant JSON list parse: `None` means "output was missing or unusable"."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return parse_json_list(text)
    except Exception:
        return None


def _first_payload(raw: str) -> dict[str, Any] | None:
    items = _load(raw)
    return items[0] if items else None


def _field(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in payload:
            return payload[name]
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return False


def _count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, tuple, set)):
        return len([item for item in value if str(item).strip()])
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _pending_from(payload: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if _truthy(_field(payload, "cbs", "CBS", "componentBasedServicing")):
        reasons.append(REASON_CBS)
    if _truthy(_field(payload, "wu", "WU", "windowsUpdate")):
        reasons.append(REASON_WU)
    if _count(_field(payload, "renames", "pendingFileRename")) > 0:
        reasons.append(REASON_RENAME)
    return {"pending": bool(reasons), "reasons": reasons}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _installed_from(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    for item in items:
        hotfix_id = _text(_field(item, "id", "HotFixID"))
        if not hotfix_id:
            continue
        collected.append(
            {
                "id": hotfix_id,
                "description": _text(_field(item, "description", "Description")),
                "installedOn": _text(_field(item, "installedOn", "InstalledOn")),
            }
        )
        if len(collected) >= HOTFIX_LIMIT:
            break
    return collected


def _detail(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _last_scan() -> dict[str, Any] | None:
    rows = history.query(limit=LAST_SCAN_WINDOW)
    for row in rows:
        if str(row.get("action") or "") != "wu-scan":
            continue
        detail = _detail(row.get("detail"))
        titles = _field(detail, "titles", "Titles")
        title_list = [str(title) for title in titles] if isinstance(titles, list) else []
        return {
            "ts": _text(row.get("ts")),
            "ok": bool(row.get("ok")),
            "count": _count(_field(detail, "updateCount", "count")),
            "titles": title_list[:10],
            "durationMs": _count(row.get("durationMs")),
        }
    return None


async def status(*, runner: Runner | None = None) -> dict[str, Any]:
    """Pending reboot, recent hotfixes and the last `wu-scan` result."""
    runner = runner or run_powershell
    errors: dict[str, str] = {}
    pending_reboot: dict[str, Any] = {"pending": False, "reasons": []}
    installed: list[dict[str, str]] = []

    try:
        pending_raw = await runner(PENDING_SCRIPT, timeout=PENDING_TIMEOUT)
    except Exception as exc:
        errors["pendingReboot"] = _message(exc)
    else:
        payload = _first_payload(pending_raw)
        if payload is None:
            errors["pendingReboot"] = "ผลลัพธ์ pending reboot จาก PowerShell ไม่ใช่ JSON"
        else:
            pending_reboot = _pending_from(payload)

    try:
        hotfix_raw = await runner(HOTFIX_SCRIPT, timeout=HOTFIX_TIMEOUT)
    except Exception as exc:
        errors["installed"] = _message(exc)
    else:
        hotfixes = _load(hotfix_raw)
        if hotfixes is None:
            errors["installed"] = "ผลลัพธ์รายการ hotfix จาก PowerShell ไม่ใช่ JSON"
        else:
            installed = _installed_from(hotfixes)

    try:
        last_scan = _last_scan()
    except Exception as exc:
        errors["lastScan"] = _message(exc)
        last_scan = None

    return {
        "pendingReboot": pending_reboot,
        "installed": installed,
        "lastScan": last_scan,
        "scannedAt": _now_iso(),
        "errors": errors,
    }


async def scan(*, runner: Runner | None = None) -> dict[str, Any]:
    """Run the allowlisted `wu-scan` action, then re-read the status."""
    runner = runner or run_powershell
    result = await actions.run_action("wu-scan")
    fresh = await status(runner=runner)
    return {
        "ok": True,
        "action": str(result.get("action") or "wu-scan"),
        "result": result.get("result") or {},
        "durationMs": _count(result.get("durationMs")),
        "status": fresh,
    }
