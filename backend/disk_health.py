"""Per-disk usage samples, days-to-full forecast and SMART health.

Samples live in the shared history SQLite file (``config.HISTORY_DB``) but this
module owns its own connection/lock and must never import ``main``, ``history``
or ``process_history``. ``smart_info`` is a single mockable function so tests
can avoid spawning PowerShell.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import psutil

import config

logger = logging.getLogger("dashboard.disk_health")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS disk_samples(
    ts TEXT,
    mount TEXT,
    used_gb REAL,
    total_gb REAL
);
CREATE INDEX IF NOT EXISTS idx_disk_samples_mount_ts
    ON disk_samples(mount, ts);
"""

SMART_COMMAND = (
    "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,"
    "OperationalStatus | ConvertTo-Json"
)
SMART_TIMEOUT_SEC = 5.0
_GB = 1024.0 ** 3

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _now_iso() -> str:
    """Fixed-width UTC ISO-8601 so TEXT ordering matches chronological order."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _cutoff_iso(days: float) -> str:
    days = max(float(days), 0.0)
    moment = datetime.now(UTC) - timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.HISTORY_DB, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


def close() -> None:
    """Close the shared connection (used by tests and shutdown)."""
    global _conn
    with _lock:
        if _conn is not None:
            with contextlib.suppress(sqlite3.Error):
                _conn.close()
            _conn = None


def record_samples(disks: list[dict[str, Any]]) -> int:
    """Persist one row per disk usage sample; best-effort, never raises.

    Each item is expected to carry ``mount``, ``used_gb`` and ``total_gb``.
    An optional ``ts`` overrides the generated timestamp. Returns the number
    of rows written (0 on failure).
    """
    if not disks:
        return 0
    now = _now_iso()
    rows = [
        (
            d.get("ts") or now,
            str(d.get("mount") or ""),
            float(d.get("used_gb") or 0.0),
            float(d.get("total_gb") or 0.0),
        )
        for d in disks
        if d.get("mount")
    ]
    if not rows:
        return 0
    try:
        with _lock:
            conn = _get_conn()
            conn.executemany(
                "INSERT INTO disk_samples(ts, mount, used_gb, total_gb) "
                "VALUES (?,?,?,?)",
                rows,
            )
            conn.commit()
    except Exception:
        logger.exception("disk sample record failed")
        return 0
    return len(rows)


def get_samples(mount: str, days: float = 7) -> list[dict[str, Any]]:
    """Return samples for ``mount`` inside the last ``days``, oldest first."""
    cutoff = _cutoff_iso(days)
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT ts, mount, used_gb, total_gb FROM disk_samples "
            "WHERE mount = ? AND ts >= ? ORDER BY ts ASC",
            (str(mount), cutoff),
        ).fetchall()
    return [
        {"ts": r[0], "mount": r[1], "used_gb": r[2], "total_gb": r[3]}
        for r in rows
    ]


def prune(days: float = 30) -> int:
    """Delete samples older than ``days`` days; return rows removed."""
    cutoff = _cutoff_iso(days)
    with _lock:
        conn = _get_conn()
        deleted = conn.execute(
            "DELETE FROM disk_samples WHERE ts < ?", (cutoff,)
        ).rowcount
        conn.commit()
        with contextlib.suppress(sqlite3.Error):
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return max(deleted, 0)


def _parse_ts(value: Any) -> float | None:
    """Parse an ISO-8601 stamp (or epoch number) into a POSIX timestamp."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def predict_days_to_full(samples: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Least-squares forecast of when a mount fills up.

    Returns ``{"days_to_full", "trend_gb_per_day", "samples"}``. The forecast
    is ``None`` when there are fewer than three valid points, the slope is not
    positive, or the total capacity is unknown.
    """
    points: list[tuple[float, float]] = []
    total_gb: float | None = None
    for sample in samples or []:
        if not isinstance(sample, dict):
            continue
        ts = _parse_ts(sample.get("ts"))
        used_gb = _as_float(sample.get("used_gb"))
        if ts is None or used_gb is None:
            continue
        points.append((ts, used_gb))
        candidate_total = _as_float(sample.get("total_gb"))
        if candidate_total is not None and candidate_total > 0:
            total_gb = candidate_total

    result: dict[str, Any] = {
        "days_to_full": None,
        "trend_gb_per_day": None,
        "samples": len(points),
    }
    if len(points) < 3:
        return result

    t0 = points[0][0]
    xs = [(ts - t0) / 86400.0 for ts, _ in points]
    ys = [used for _, used in points]
    count = len(points)
    x_mean = sum(xs) / count
    y_mean = sum(ys) / count
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= 0:
        return result

    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator
    result["trend_gb_per_day"] = round(slope, 6)
    if slope <= 0 or total_gb is None:
        return result

    remaining_gb = max(total_gb - ys[-1], 0.0)
    result["days_to_full"] = round(remaining_gb / slope, 2)
    return result


def smart_info() -> dict[str, Any]:
    """Query physical-disk health through PowerShell (best-effort).

    Returns ``{"available": True, "disks": [...]}`` on success, otherwise
    ``{"available": False, "error": "..."}``. Kept as one mockable function.
    """
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", SMART_COMMAND],
            capture_output=True,
            text=True,
            timeout=SMART_TIMEOUT_SEC,
            check=False,
            **kwargs,
        )
    except Exception as exc:
        logger.warning("SMART query failed: %s", exc)
        return {"available": False, "error": str(exc)}

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"powershell exit {proc.returncode}"
        return {"available": False, "error": detail[:400]}

    output = (proc.stdout or "").strip()
    if not output:
        return {"available": False, "error": "empty PowerShell output"}
    try:
        payload = json.loads(output)
    except (TypeError, ValueError) as exc:
        return {"available": False, "error": f"invalid JSON: {exc}"}

    if isinstance(payload, dict):
        rows = [payload]
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    else:
        rows = []
    if not rows:
        return {"available": False, "error": "unexpected SMART payload"}
    return {"available": True, "disks": rows}


def disk_usage() -> list[dict[str, Any]]:
    """Return usage for mounted fixed drives (CD/removable/network skipped)."""
    disks: list[dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        opts = (part.opts or "").lower()
        if any(flag in opts for flag in ("cdrom", "removable", "remote")):
            continue
        if not part.fstype or not part.mountpoint:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (OSError, psutil.Error):
            continue
        total_gb = round(usage.total / _GB, 2)
        used_gb = round(usage.used / _GB, 2)
        used_pct = usage.percent if isinstance(usage.percent, (int, float)) else None
        if used_pct is None:
            used_pct = (used_gb / total_gb * 100.0) if total_gb else 0.0
        disks.append({
            "mount": part.mountpoint,
            "total_gb": total_gb,
            "used_gb": used_gb,
            "used_pct": round(float(used_pct), 1),
        })
    return disks
