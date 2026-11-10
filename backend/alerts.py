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
import copy
import ipaddress
import json
import logging
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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

# Notification delivery (best-effort, stdlib only).
HTTP_TIMEOUT = 5.0
LINE_NOTIFY_URL = "https://notify-api.line.me/api/notify"
WEBHOOK_URL_MAX = 2048
LINE_FIELD_MAX = 200

# Cloud metadata endpoints: never a legitimate webhook target (SSRF guard).
BLOCKED_WEBHOOK_HOSTS = frozenset({
    "169.254.169.254",
    "100.100.100.200",
    "metadata",
    "metadata.google.internal",
})
BLOCKED_WEBHOOK_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
)


def _validate_webhook_url(url: str) -> str:
    """Reject non-http(s) and link-local/metadata webhook targets.

    Loopback and LAN addresses stay allowed on purpose: this dashboard runs on
    the user's own machine and a webhook to ``http://192.168.1.10/hook`` (home
    automation, local Home Assistant, ...) is a supported use case.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("channels.webhook.url must be an absolute http(s) URL")
    host = parts.hostname.lower()
    if host in BLOCKED_WEBHOOK_HOSTS:
        raise ValueError("channels.webhook.url host is not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if any(address in network for network in BLOCKED_WEBHOOK_NETWORKS):
        raise ValueError("channels.webhook.url host is not allowed")
    return url


def _default_channels() -> dict[str, Any]:
    """Full channel schema; webhook/LINE stay off unless configured."""
    return {
        "toast": True,
        "sound": False,
        "webhook": {"enabled": False, "url": ""},
        "line": {"enabled": False, "token": "", "target": ""},
    }


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
        "channels": _default_channels(),
    }


def _validate_rules_payload(payload: Any, existing_line_token: str = "") -> dict[str, Any]:
    """Validate a rules+channels payload; returns the normalized copy.

    ``existing_line_token`` is reused when the payload omits ``line.token`` so
    the UI can save rules without ever receiving the stored secret.

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
    defaults = _default_channels()
    channels: dict[str, Any] = {}
    for key in ("toast", "sound"):
        v = raw_channels.get(key, defaults[key])
        if not isinstance(v, bool):
            raise ValueError(f"channels.{key} must be a boolean")  # noqa: TRY004 -- ValueError -> HTTP 400
        channels[key] = v

    raw_webhook = raw_channels.get("webhook", defaults["webhook"])
    if not isinstance(raw_webhook, dict):
        raise ValueError("channels.webhook must be an object")  # noqa: TRY004 -- ValueError -> HTTP 400
    webhook_enabled = raw_webhook.get("enabled", False)
    if not isinstance(webhook_enabled, bool):
        raise ValueError("channels.webhook.enabled must be a boolean")  # noqa: TRY004 -- ValueError -> HTTP 400
    webhook_url = raw_webhook.get("url", "")
    if not isinstance(webhook_url, str):
        raise ValueError("channels.webhook.url must be a string")  # noqa: TRY004 -- ValueError -> HTTP 400
    webhook_url = webhook_url.strip()
    if len(webhook_url) > WEBHOOK_URL_MAX:
        raise ValueError(f"channels.webhook.url must be at most {WEBHOOK_URL_MAX} chars")
    if webhook_enabled:
        _validate_webhook_url(webhook_url)
    channels["webhook"] = {"enabled": webhook_enabled, "url": webhook_url}

    raw_line = raw_channels.get("line", defaults["line"])
    if not isinstance(raw_line, dict):
        raise ValueError("channels.line must be an object")  # noqa: TRY004 -- ValueError -> HTTP 400
    line_enabled = raw_line.get("enabled", False)
    if not isinstance(line_enabled, bool):
        raise ValueError("channels.line.enabled must be a boolean")  # noqa: TRY004 -- ValueError -> HTTP 400
    # Omitting the token key keeps the stored secret; an explicit "" clears it.
    if "token" in raw_line:
        raw_token = raw_line.get("token")
        if not isinstance(raw_token, str):
            raise ValueError("channels.line.token must be a string")
        line_token = raw_token.strip()
        if len(line_token) > LINE_FIELD_MAX:
            raise ValueError(f"channels.line.token must be at most {LINE_FIELD_MAX} chars")
    else:
        line_token = existing_line_token
    raw_target = raw_line.get("target", "")
    if not isinstance(raw_target, str):
        raise ValueError("channels.line.target must be a string")  # noqa: TRY004 -- ValueError -> HTTP 400
    line_target = raw_target.strip()
    if len(line_target) > LINE_FIELD_MAX:
        raise ValueError(f"channels.line.target must be at most {LINE_FIELD_MAX} chars")
    channels["line"] = {"enabled": line_enabled, "token": line_token, "target": line_target}

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


def get_channels() -> dict[str, Any]:
    """Notification channels (toast/sound/webhook/line) from the effective rules."""
    raw = get_rules().get("channels") or {}
    merged = _default_channels()
    merged["toast"] = bool(raw.get("toast", merged["toast"]))
    merged["sound"] = bool(raw.get("sound", merged["sound"]))
    for name in ("webhook", "line"):
        extra = raw.get(name)
        if isinstance(extra, dict):
            merged[name] = {**merged[name], **extra}
    return merged


def public_rules() -> dict[str, Any]:
    """Effective rules with the LINE token redacted (never leaves the machine)."""
    rules = copy.deepcopy(get_rules())
    channels = get_channels()
    line = channels.get("line") or {}
    rules["channels"] = {
        "toast": channels["toast"],
        "sound": channels["sound"],
        "webhook": dict(channels.get("webhook") or {}),
        "line": {
            "enabled": bool(line.get("enabled")),
            "token": "",
            "token_set": bool(line.get("token")),
            "target": str(line.get("target") or ""),
        },
    }
    return rules


def set_rules(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate, hot-reload in memory and persist rules to disk."""
    global _rules
    existing_line_token = str((get_channels().get("line") or {}).get("token") or "")
    validated = _validate_rules_payload(payload, existing_line_token=existing_line_token)
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so a webhook cannot be bounced to another target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _log_target(url: str) -> str:
    """Host-only label for logs (query strings may carry secrets)."""
    try:
        parts = urllib.parse.urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"
    except Exception:
        return "webhook"


def _post(url: str, body: bytes, headers: dict[str, str]) -> bool:
    """Blocking POST helper; returns True on a 2xx response, never raises."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _OPENER.open(req, timeout=HTTP_TIMEOUT) as resp:
            status = getattr(resp, "status", 200)
            if 300 <= status < 400:
                logger.warning("notification POST to %s rejected: HTTP %s (no redirects)",
                               _log_target(url), status)
                return False
            resp.read()
        return True
    except urllib.error.HTTPError as exc:
        logger.warning("notification POST to %s failed: HTTP %s",
                       _log_target(url), exc.code)
        return False
    except Exception as exc:
        logger.warning("notification POST to %s failed: %s", _log_target(url), exc)
        return False


async def send_webhook(url: str, payload: dict[str, Any]) -> bool:
    """POST one JSON payload to a generic webhook; never raises."""
    if not isinstance(url, str):
        return False
    try:
        _validate_webhook_url(url)
    except ValueError as exc:
        logger.warning("webhook blocked: %s", exc)
        return False
    body = json.dumps(payload, default=str).encode("utf-8")
    try:
        return await asyncio.to_thread(
            _post, url, body, {"Content-Type": "application/json"})
    except Exception as exc:
        logger.warning("webhook dispatch failed: %s", exc)
        return False


async def send_line(token: str, message: str) -> bool:
    """Send one LINE Notify message; never raises."""
    if not isinstance(token, str) or not token.strip():
        return False
    body = urllib.parse.urlencode({"message": message}).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Bearer {token.strip()}",
    }
    try:
        return await asyncio.to_thread(_post, LINE_NOTIFY_URL, body, headers)
    except Exception as exc:
        logger.warning("line notify dispatch failed: %s", exc)
        return False


def _webhook_payload(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": alert.get("id", ""),
        "title": alert.get("title", ""),
        "message": alert.get("message", ""),
        "value": alert.get("value"),
        "threshold": alert.get("threshold"),
        "ts": alert.get("ts", time.time()),
        "severity": alert.get("severity"),
        "regressions": alert.get("regressions") or [],
        "source": str(alert.get("source") or "dashboard"),
    }


async def dispatch(alert: dict[str, Any]) -> dict[str, bool]:
    """Fan one alert out to every enabled channel; never raises.

    The returned mapping only contains channels that were attempted, mapped to
    whether delivery succeeded.
    """
    results: dict[str, bool] = {}
    try:
        channels = get_channels()
    except Exception as exc:
        logger.warning("channel lookup failed: %s", exc)
        return results

    title = str(alert.get("title", ""))
    message = str(alert.get("message", ""))

    if channels.get("toast", True):
        try:
            await send_toast(title, message)
            results["toast"] = True
        except Exception as exc:
            logger.warning("toast dispatch failed: %s", exc)
            results["toast"] = False

    webhook = channels.get("webhook") or {}
    if webhook.get("enabled"):
        try:
            results["webhook"] = await send_webhook(
                str(webhook.get("url", "")), _webhook_payload(alert))
        except Exception as exc:
            logger.warning("webhook dispatch failed: %s", exc)
            results["webhook"] = False

    line = channels.get("line") or {}
    if line.get("enabled"):
        text = f"{title}: {message}" if title and not message.startswith(title) else message
        try:
            results["line"] = await send_line(str(line.get("token", "")), text)
        except Exception as exc:
            logger.warning("line dispatch failed: %s", exc)
            results["line"] = False

    if results and not all(results.values()):
        logger.warning("alert delivery failed on: %s",
                       [name for name, ok in results.items() if not ok])
    return results


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
