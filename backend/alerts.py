"""Threshold-based alerting with sustained-breach confirmation + cooldown.

Fires dashboard WS events ("alert") and native Windows Toast notifications.
Evaluation is pure/synchronous so it is easy to unit-test; the toast sender is
the only async piece.

Rules live in ``backend/.cache/alert_rules.json`` (editable via
``PUT /api/alerts/rules``). When the file is missing or invalid the built-in
defaults are used, derived from the historical hardcoded thresholds in
``config`` — so with no user configuration the behavior is unchanged.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import sys
import time
from collections.abc import Callable
from typing import Any

import psutil

import config

logger = logging.getLogger("dashboard.alerts")

_state: dict[str, dict[str, Any]] = {}

# ---- Rules store ---- #

RULES_PATH = config.CACHE_DIR / "alert_rules.json"

KNOWN_METRICS = ("cpu_temp", "gpu_temp", "ram_pct", "disk_pct")
KNOWN_OPS = (">=", ">")

_METRIC_EXTRACTORS: dict[str, Callable[[dict[str, Any]], float | None]] = {
    "cpu_temp": lambda sample: sample.get("cpu_temp"),
    "gpu_temp": lambda sample: sample.get("gpu_temp"),
    "ram_pct": lambda sample: sample.get("ram_pct"),
    "disk_pct": lambda sample: _max_disk_used_pct(),
}
_METRIC_TITLES = {
    "cpu_temp": "CPU temperature high",
    "gpu_temp": "GPU temperature high",
    "ram_pct": "RAM usage critical",
    "disk_pct": "Disk almost full",
}
_METRIC_UNITS = {"cpu_temp": "°C", "gpu_temp": "°C", "ram_pct": "%", "disk_pct": "%"}

# None => use defaults derived from config thresholds (legacy behavior).
_rules: dict[str, Any] | None = None


def _default_rules() -> dict[str, Any]:
    """Seed rules from the historical hardcoded thresholds in config."""
    return {
        "rules": [
            {"id": "cpu_temp", "metric": "cpu_temp", "op": ">=",
             "threshold": config.ALERT_CPU_TEMP, "enabled": True},
            {"id": "gpu_temp", "metric": "gpu_temp", "op": ">=",
             "threshold": config.ALERT_GPU_TEMP, "enabled": True},
            {"id": "ram_pct", "metric": "ram_pct", "op": ">=",
             "threshold": config.ALERT_RAM_PCT, "enabled": True},
            {"id": "disk_full", "metric": "disk_pct", "op": ">=",
             "threshold": config.ALERT_DISK_PCT, "enabled": True},
        ],
        "channels": {"toast": True, "sound": False},
    }


def _validate_rules_payload(payload: Any) -> dict[str, Any]:
    """Validate a rules+channels payload; returns the normalized copy.

    Type mismatches raise ValueError (not TypeError) on purpose: the API layer
    maps ValueError to HTTP 400 for malformed client payloads.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")  # noqa: TRY004 -- ValueError -> HTTP 400
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be a list")  # noqa: TRY004 -- ValueError -> HTTP 400
    seen: set[str] = set()
    rules: list[dict[str, Any]] = []
    for r in raw_rules:
        if not isinstance(r, dict):
            raise ValueError("each rule must be an object")  # noqa: TRY004 -- ValueError -> HTTP 400
        rid = r.get("id")
        metric = r.get("metric")
        op = r.get("op")
        threshold = r.get("threshold")
        enabled = r.get("enabled", True)
        if not isinstance(rid, str) or not rid.strip() or len(rid) > 64:
            raise ValueError("rule.id must be a non-empty string (max 64 chars)")
        rid = rid.strip()
        if rid in seen:
            raise ValueError(f"duplicate rule id: {rid}")
        seen.add(rid)
        if metric not in KNOWN_METRICS:
            raise ValueError(f"unknown metric: {metric!r}")
        if op not in KNOWN_OPS:
            raise ValueError(f"unknown op: {op!r}")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) \
                or not math.isfinite(threshold):
            raise ValueError("rule.threshold must be a finite number")
        if not isinstance(enabled, bool):
            raise ValueError("rule.enabled must be a boolean")  # noqa: TRY004 -- ValueError -> HTTP 400
        rules.append({"id": rid, "metric": metric, "op": op,
                      "threshold": float(threshold), "enabled": enabled})
    raw_channels = payload.get("channels", {})
    if not isinstance(raw_channels, dict):
        raise ValueError("channels must be an object")  # noqa: TRY004 -- ValueError -> HTTP 400
    defaults = _default_rules()["channels"]
    channels: dict[str, bool] = {}
    for key in ("toast", "sound"):
        v = raw_channels.get(key, defaults[key])
        if not isinstance(v, bool):
            raise ValueError(f"channels.{key} must be a boolean")  # noqa: TRY004 -- ValueError -> HTTP 400
        channels[key] = v
    return {"rules": rules, "channels": channels}


def load_rules() -> dict[str, Any]:
    """Load rules from disk; fall back to defaults when missing/invalid."""
    global _rules
    try:
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        _rules = _validate_rules_payload(raw)
    except FileNotFoundError:
        _rules = None
    except (OSError, ValueError) as exc:
        logger.debug("alert rules fallback to defaults: %s", exc)
        _rules = None
    return get_rules()


def get_rules() -> dict[str, Any]:
    """Effective rules (user-configured or defaults)."""
    return _rules if _rules is not None else _default_rules()


def get_channels() -> dict[str, bool]:
    """Notification channels (toast/sound) from the effective rules."""
    return dict(get_rules()["channels"])


def set_rules(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate, hot-reload in memory and persist rules to disk."""
    global _rules
    validated = _validate_rules_payload(payload)
    _rules = validated
    RULES_PATH.write_text(json.dumps(_rules, indent=2), encoding="utf-8")
    logger.info("alert rules updated (%d rules)", len(_rules["rules"]))
    return get_rules()


load_rules()

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
           threshold: float, unit: str = "", op: str = ">=") -> dict[str, Any] | None:
    st = _state.setdefault(rule_id, {"breaches": 0, "last_fired": 0.0,
                                     "gaps": 0, "recoveries": 0})
    if value is None:
        st["breaches"] = 0
        st["gaps"] += 1
        logger.debug("alert %s gap (sensor None) gaps=%d", rule_id, st["gaps"])
        return None
    breached = value >= threshold if op == ">=" else value > threshold
    if not breached:
        if st["breaches"] > 0:
            st["recoveries"] += 1
            logger.debug("alert %s recovered recoveries=%d", rule_id, st["recoveries"])
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
    """Run all enabled rules against one sample; returns newly-fired alerts."""
    if not config.ALERTS_ENABLED:
        return []

    fired: list[dict[str, Any]] = []
    for rule in get_rules()["rules"]:
        if not rule.get("enabled", True):
            continue
        metric = rule["metric"]
        extract = _METRIC_EXTRACTORS.get(metric)
        if extract is None:
            continue
        value = extract(sample)
        a = _check(rule["id"], _METRIC_TITLES[metric], value,
                   rule["threshold"], _METRIC_UNITS[metric], rule.get("op", ">="))
        if a:
            fired.append(a)
    if fired:
        logger.warning("alerts fired: %s", [a["id"] for a in fired])
    return fired


def reset_state() -> None:
    _state.clear()
