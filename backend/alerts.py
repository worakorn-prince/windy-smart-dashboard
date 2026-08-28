"""Threshold-based alerting with sustained-breach confirmation + cooldown.

Fires dashboard WS events ("alert") and native Windows Toast notifications.
Evaluation is pure/synchronous so it is easy to unit-test; the toast sender is
the only async piece.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import time
from typing import Any

import psutil

import config

logger = logging.getLogger("dashboard.alerts")

_state: dict[str, dict[str, Any]] = {}

# Using the well-known PowerShell AUMID so toasts render without registering
# a custom Start-menu app identity.
_TOAST_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xmlText = @'
<toast><visual><binding template="ToastGeneric"><text>__TITLE__</text><text>__MSG__</text></binding></visual></toast>
'@
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($xmlText)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('__AUMID__').Show($toast)
"""


def _esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("'", "''"))


async def send_toast(title: str, message: str) -> None:
    """Best-effort native Windows toast; never raises."""
    if not sys.platform.startswith("win"):
        return
    script = (_TOAST_PS.replace("__TITLE__", _esc(title))
                       .replace("__MSG__", _esc(message))
                       .replace("__AUMID__", _esc(_TOAST_AUMID)))
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=8)
    except Exception as exc:
        logger.debug("toast failed: %s", exc)


def _check(rule_id: str, title: str, value: float | None,
           threshold: float, unit: str = "") -> dict[str, Any] | None:
    st = _state.setdefault(rule_id, {"breaches": 0, "last_fired": 0.0})
    if value is None or value < threshold:
        st["breaches"] = 0
        return None
    st["breaches"] += 1
    if st["breaches"] < config.ALERT_SUSTAINED_SAMPLES:
        return None
    now = time.time()
    if now - st["last_fired"] < config.ALERT_COOLDOWN_SEC:
        return None
    st["last_fired"] = now
    st["breaches"] = 0
    return {
        "id": rule_id,
        "title": title,
        "message": f"{title}: {value:g}{unit} (limit {threshold:g}{unit})",
        "value": value,
        "threshold": threshold,
        "ts": now,
    }


def _max_disk_used_pct() -> float | None:
    vals: list[float] = []
    for p in psutil.disk_partitions(all=False):
        if "cdrom" in p.opts.lower():
            continue
        try:
            vals.append(psutil.disk_usage(p.mountpoint).percent)
        except (PermissionError, OSError):
            continue
    return max(vals) if vals else None


def evaluate(sample: dict[str, Any]) -> list[dict[str, Any]]:
    """Run all rules against one sample; returns newly-fired alerts."""
    if not config.ALERTS_ENABLED:
        return []

    fired: list[dict[str, Any]] = []
    checks = [
        ("cpu_temp", "CPU temperature high", sample.get("cpu_temp"),
         config.ALERT_CPU_TEMP, "°C"),
        ("gpu_temp", "GPU temperature high", sample.get("gpu_temp"),
         config.ALERT_GPU_TEMP, "°C"),
        ("ram_pct", "RAM usage critical", sample.get("ram_pct"),
         config.ALERT_RAM_PCT, "%"),
        ("disk_full", "Disk almost full", _max_disk_used_pct(),
         config.ALERT_DISK_PCT, "%"),
    ]
    for rule_id, title, value, threshold, unit in checks:
        a = _check(rule_id, title, value, threshold, unit)
        if a:
            fired.append(a)
    if fired:
        logger.warning("alerts fired: %s", [a["id"] for a in fired])
    return fired


def reset_state() -> None:
    _state.clear()
