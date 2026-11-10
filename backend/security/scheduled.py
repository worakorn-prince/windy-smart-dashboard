"""Scheduled security audit: hot-reloadable schedule + persisted results.

The audit is heavy (WMI/PowerShell), so it is disabled by default and only
runs when the operator turns it on from the Security page. Schedule state is
kept in a small JSON file under the cache dir; results are stored in the
shared security event log with kind="scheduled_audit".
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from datetime import datetime
from typing import Any

import config
from security import audit as audit_mod
from security import persistence

logger = logging.getLogger("dashboard.security.scheduled")

SCHEDULE_PATH = config.CACHE_DIR / "audit_schedule.json"

KIND = "scheduled_audit"
SOURCE_IP = "127.0.0.1"

DEFAULT_INTERVAL_HOURS = 24.0
MIN_INTERVAL_HOURS = 0.5
MAX_INTERVAL_HOURS = 168.0

STARTUP_DELAY = 60.0
POLL_INTERVAL = 30.0
RETRY_DELAY = 60.0

_schedule: dict[str, Any] | None = None
_next_due: float | None = None
_last_run: str | None = None
_last_run_ts: float | None = None
_state_loaded = False

_run_lock: asyncio.Lock | None = None
_run_lock_loop: asyncio.AbstractEventLoop | None = None


def _default_schedule() -> dict[str, Any]:
    return {"enabled": False, "intervalHours": DEFAULT_INTERVAL_HOURS}


def _coerce_interval(value: Any) -> float:
    """Return a validated interval in hours or raise ValueError."""
    if isinstance(value, bool):
        raise ValueError(  # noqa: TRY004 - API contract requires ValueError for odd values
            f"intervalHours must be a number between {MIN_INTERVAL_HOURS} and {MAX_INTERVAL_HOURS}",
        )
    try:
        hours = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError(
            f"intervalHours must be a number between {MIN_INTERVAL_HOURS} and {MAX_INTERVAL_HOURS}",
        ) from err
    if not math.isfinite(hours) or hours < MIN_INTERVAL_HOURS or hours > MAX_INTERVAL_HOURS:
        raise ValueError(
            f"intervalHours must be between {MIN_INTERVAL_HOURS} and {MAX_INTERVAL_HOURS}",
        )
    return hours


def _load_schedule() -> dict[str, Any]:
    """Read the schedule file, falling back to the disabled default."""
    try:
        raw = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _default_schedule()
    if not isinstance(raw, dict):
        return _default_schedule()

    out = _default_schedule()
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        out["enabled"] = enabled
    try:
        out["intervalHours"] = _coerce_interval(raw.get("intervalHours", DEFAULT_INTERVAL_HOURS))
    except ValueError:
        logger.warning("invalid intervalHours in %s; using default", SCHEDULE_PATH)
    return out


def _write_schedule(data: dict[str, Any]) -> None:
    """Persist atomically (temp file + replace); failures are non-fatal."""
    tmp = SCHEDULE_PATH.with_name(SCHEDULE_PATH.name + ".tmp")
    try:
        SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, SCHEDULE_PATH)
    except OSError:
        logger.warning("audit schedule not persisted", exc_info=True)


def _parse_ts(value: Any) -> float | None:
    """Parse an ISO timestamp from the event log into epoch seconds."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _recompute_next_due(now: float | None = None) -> None:
    """Derive ``_next_due`` from the last stored run + current interval.

    Never returns a timestamp in the past: an overdue schedule is reported as
    due *now* so the caller can decide, instead of exposing a stale epoch.
    """
    global _next_due
    schedule = get_schedule()
    if not schedule["enabled"] or _last_run_ts is None:
        _next_due = None
        return
    due = _last_run_ts + float(schedule["intervalHours"]) * 3600.0
    current = time.time() if now is None else now
    _next_due = max(due, current)


def _sync_from_history() -> None:
    """Seed last-run state from the newest persisted audit (restart-safe)."""
    global _last_run, _last_run_ts
    try:
        events = persistence.list_events(1, kind=KIND)
    except Exception:
        logger.debug("audit history unavailable", exc_info=True)
        return
    if not events:
        return
    stamp = events[0].get("ts")
    if not stamp:
        return
    _last_run = str(stamp)
    _last_run_ts = _parse_ts(stamp)


def _ensure_state_loaded() -> None:
    """Load the schedule + last run once per process (or after reset_state)."""
    global _state_loaded
    if _state_loaded:
        return
    _state_loaded = True
    _sync_from_history()
    _recompute_next_due()


def get_schedule() -> dict[str, Any]:
    """Return the effective schedule (memory cache, hot-reloaded on set)."""
    global _schedule
    if _schedule is None:
        _schedule = _load_schedule()
    return dict(_schedule)


def set_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and apply a schedule update; raises ValueError on bad input."""
    global _schedule
    if not isinstance(payload, dict):
        raise ValueError("schedule payload must be an object")  # noqa: TRY004 - endpoint maps it to 400

    current = get_schedule()
    enabled = current["enabled"]
    interval = current["intervalHours"]

    if "enabled" in payload:
        raw_enabled = payload["enabled"]
        if not isinstance(raw_enabled, bool):
            raise ValueError("enabled must be a boolean")
        enabled = raw_enabled
    if "intervalHours" in payload:
        interval = _coerce_interval(payload["intervalHours"])

    updated = {"enabled": enabled, "intervalHours": interval}
    _schedule = updated
    _write_schedule(updated)
    # Re-derive from the last stored run so a shorter/longer interval never
    # triggers an immediate run that is not actually due yet.
    _ensure_state_loaded()
    _recompute_next_due()
    return dict(updated)


def get_last_run() -> str | None:
    _ensure_state_loaded()
    return _last_run


def get_next_due() -> float | None:
    _ensure_state_loaded()
    return _next_due


def _get_run_lock() -> asyncio.Lock:
    """Return the module-level run lock for the current event loop.

    The lock is module-level (one audit at a time per process) but is bound to
    a single loop by asyncio, so it is recreated when the running loop changes
    (tests use a fresh loop per asyncio.run call).
    """
    global _run_lock, _run_lock_loop
    loop = asyncio.get_running_loop()
    if _run_lock is None or _run_lock_loop is not loop:
        _run_lock = asyncio.Lock()
        _run_lock_loop = loop
    return _run_lock


def _audit_in_thread(suspicious: list[str] | None) -> dict[str, Any]:
    """Run the async audit to completion on its own loop inside a worker thread.

    run_and_store() is always awaited from an event loop (uvicorn lifespan,
    audit_loop or the REST handler), so the WMI/PowerShell heavy audit must
    not run there — asyncio.to_thread() calls this helper and the audit gets a
    private loop, which keeps the server loop responsive.
    """
    return asyncio.run(audit_mod.run_audit(suspicious_override=suspicious))


def reset_state() -> None:
    """Clear in-memory state and re-seed it from persisted history (tests)."""
    global _schedule, _next_due, _last_run, _last_run_ts
    global _state_loaded, _run_lock, _run_lock_loop
    _schedule = None
    _next_due = None
    _last_run = None
    _last_run_ts = None
    _state_loaded = False
    _run_lock = None
    _run_lock_loop = None
    _ensure_state_loaded()


async def run_and_store(suspicious_override: list[str] | None = None) -> dict[str, Any]:
    """Run a full audit (off-loop), persist a compact summary and return it.

    Returns ``{"ok": True, "skipped": "in_flight"}`` immediately (without
    waiting) when another scheduled run already holds the module lock.
    """
    global _last_run, _last_run_ts
    lock = _get_run_lock()
    if lock.locked():
        return {"ok": True, "skipped": "in_flight"}

    async with lock:
        report = await asyncio.to_thread(_audit_in_thread, suspicious_override)
        findings = report.get("findings") or []
        ranked = sorted(
            (f for f in findings if isinstance(f, dict)),
            key=lambda f: f.get("weight", 0),
            reverse=True,
        )
        detail: dict[str, Any] = {
            "riskscore": report.get("riskscore", 0),
            "risk_label": report.get("risk_label", ""),
            "findings_count": len(findings),
            "critical_count": sum(
                1 for f in findings if isinstance(f, dict) and f.get("severity") == "critical"
            ),
            "duration_ms": report.get("duration_ms", 0),
            "top_findings": [f.get("title", "") for f in ranked[:3]],
        }
        stored = await asyncio.to_thread(persistence.record_event, KIND, SOURCE_IP, detail)
        _last_run = str(report.get("generated_at") or datetime.now().isoformat())
        _last_run_ts = _parse_ts(_last_run) or time.time()
        return {**detail, "generated_at": _last_run, "stored": bool(stored)}


async def maybe_run(now: float) -> dict[str, Any] | None:
    """Run the audit if enabled and due; return the summary or None.

    ``now`` is the caller's clock (audit_loop passes time.time()), which keeps
    the scheduling logic testable without sleeping. The next due time is
    computed from the successful run (``now`` + interval) and shortened to
    RETRY_DELAY after a failure so a broken run does not stall for hours.
    """
    global _next_due
    _ensure_state_loaded()
    schedule = get_schedule()
    if not schedule["enabled"]:
        return None
    if _next_due is not None and now < _next_due:
        return None

    try:
        summary = await run_and_store()
    except Exception:
        _next_due = now + RETRY_DELAY
        raise

    if summary.get("skipped"):
        _next_due = now + RETRY_DELAY
        return summary

    _next_due = now + float(schedule["intervalHours"]) * 3600.0
    return summary


async def audit_loop() -> None:
    """Poll every POLL_INTERVAL after a STARTUP_DELAY; never dies on errors."""
    await asyncio.sleep(STARTUP_DELAY)
    while True:
        try:
            await maybe_run(time.time())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduled audit run failed")
        await asyncio.sleep(POLL_INTERVAL)


try:
    _ensure_state_loaded()
except Exception:
    logger.warning("scheduled audit state init failed", exc_info=True)
