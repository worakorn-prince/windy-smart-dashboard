"""Aggregated overview payload for the /insights page (read-only).

One synchronous producer per ``24h|7d|30d`` range; main.py wraps it in a
per-range ``_SingleFlightCache`` (TTL 60 s) so it always runs via
``asyncio.to_thread`` and never blocks the event loop. Aggregation happens
in SQL as much as possible, and baseline + anomalies are reused from
``insights.compute_anomalies`` (ANOM-01) — never re-implemented here.

Data reality (measured 2026-11-20): ``samples`` retention is only ~10 h,
while process/disk/maintenance/security tables hold ~1 month of TEXT-ISO
rows. The response therefore reports ``effective_window`` (min/max ts of
the ``samples`` actually used) instead of pretending the requested range
was covered, and every TEXT table is always filtered by ``ts >= since``
with a cutoff string matching that table's exact ISO format:

- process_samples / disk_samples: ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (UTC)
- maintenance_actions:            ``YYYY-MM-DDTHH:MM:SSZ`` (UTC)
- security_events:                local naive ``datetime.now().isoformat()``

Each section is best-effort: a missing table or DB error degrades that
section to an empty result instead of failing the whole payload.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import config
import disk_health
import history
import insights
import process_history
from security import persistence as sec_persistence

logger = logging.getLogger("dashboard.insights_overview")

RANGES: dict[str, int] = insights.RANGES

TREND_METRICS: tuple[str, ...] = (
    "cpu_pct", "ram_pct", "swap_pct", "cpu_temp", "gpu_temp", "disk_temp_max",
    "cpu_power_w", "gpu_power_w",
    "net_sent_bps", "net_recv_bps",
    "disk_read_bps", "disk_write_bps",
)

TOP_PROCESSES_LIMIT = 10
TOP_SOURCES_LIMIT = 10
BY_KIND_LIMIT = 20

# Fixed-width UTC stamps, mirroring each owner module's _now_iso().
_MICRO_Z = "%Y-%m-%dT%H:%M:%S.%fZ"
_SEC_Z = "%Y-%m-%dT%H:%M:%SZ"

_MAINT_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS maintenance_actions("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts TEXT NOT NULL, "
    "action TEXT NOT NULL, "
    "target TEXT, "
    "ok INTEGER NOT NULL, "
    "duration_ms INTEGER, "
    "detail TEXT, "
    "error TEXT)"
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _trends(range_str: str, range_sec: int, since: float) -> dict[str, Any]:
    """Bucketed averages over ``samples`` + the effective window actually covered."""
    bucket = max(range_sec // config.HISTORY_MAX_POINTS, 1)
    with history._lock:
        conn = history._get_conn()
        existing = {r[1] for r in conn.execute("PRAGMA table_info(samples)")}
        cols = [c for c in TREND_METRICS if c in existing]
        min_ts, max_ts, n_rows = conn.execute(
            "SELECT MIN(ts), MAX(ts), COUNT(*) FROM samples WHERE ts >= ?", (since,)
        ).fetchone()
        sel = ", ".join(f"AVG({c}) AS {c}" for c in cols)
        rows = conn.execute(
            f"SELECT CAST(ts/{bucket} AS INTEGER)*{bucket} AS b, {sel} "
            f"FROM samples WHERE ts >= ? GROUP BY b ORDER BY b",
            (since,),
        ).fetchall()

    window: dict[str, Any] | None = None
    if n_rows:
        window = {"start": float(min_ts), "end": float(max_ts), "n": int(n_rows)}

    points: list[dict[str, Any]] = []
    for row in rows:
        p: dict[str, Any] = {"ts": row[0]}
        for i, col in enumerate(cols, start=1):
            v = row[i]
            p[col] = round(v, 2) if v is not None else None
        for col in TREND_METRICS:
            if col not in p:
                p[col] = None
        points.append(p)

    return {
        "range": range_str,
        "bucket_sec": bucket,
        "count": len(points),
        "points": points,
    }, window


def _disk_usage(since_iso: str) -> list[dict[str, Any]]:
    """Per-mount used_gb stats from disk_samples (first/last/avg/peak/delta)."""
    with disk_health._lock:
        conn = disk_health._get_conn()
        if not _table_exists(conn, "disk_samples"):
            return []
        agg = conn.execute(
            "SELECT mount, AVG(used_gb), MAX(used_gb), MIN(used_gb), COUNT(*), MIN(ts), MAX(ts) "
            "FROM disk_samples WHERE ts >= ? GROUP BY mount ORDER BY mount",
            (since_iso,),
        ).fetchall()
        first_rows = conn.execute(
            "SELECT mount, used_gb FROM ("
            "  SELECT mount, used_gb, ROW_NUMBER() OVER (PARTITION BY mount ORDER BY ts ASC) AS rn"
            "  FROM disk_samples WHERE ts >= ?) WHERE rn = 1",
            (since_iso,),
        ).fetchall()
        last_rows = conn.execute(
            "SELECT mount, used_gb, total_gb FROM ("
            "  SELECT mount, used_gb, total_gb,"
            "  ROW_NUMBER() OVER (PARTITION BY mount ORDER BY ts DESC) AS rn"
            "  FROM disk_samples WHERE ts >= ?) WHERE rn = 1",
            (since_iso,),
        ).fetchall()

    first_used = dict(first_rows)
    last_info = {r[0]: (r[1], r[2]) for r in last_rows}

    disks: list[dict[str, Any]] = []
    for mount, avg, peak, _low, n, first_ts, last_ts in agg:
        last_used, total_gb = last_info.get(mount, (None, None))
        start_used = first_used.get(mount)
        delta = None
        if last_used is not None and start_used is not None:
            delta = round(last_used - start_used, 2)
        disks.append({
            "mount": mount,
            "used_gb": round(last_used, 2) if last_used is not None else None,
            "total_gb": round(total_gb, 2) if total_gb is not None else None,
            "first_used_gb": round(start_used, 2) if start_used is not None else None,
            "avg_used_gb": round(avg, 2) if avg is not None else None,
            "peak_used_gb": round(peak, 2) if peak is not None else None,
            "delta_gb": delta,
            "n": int(n),
            "first_ts": first_ts,
            "last_ts": last_ts,
        })
    return disks


def _top_processes(since_iso: str) -> list[dict[str, Any]]:
    """Top-N processes by average CPU, with peak memory, from process_samples."""
    with process_history._lock:
        conn = process_history._get_conn()
        if not _table_exists(conn, "process_samples"):
            return []
        rows = conn.execute(
            "SELECT name, AVG(cpu_pct), MAX(mem_mb), COUNT(*) "
            "FROM process_samples WHERE ts >= ? "
            "GROUP BY name ORDER BY AVG(cpu_pct) DESC LIMIT ?",
            (since_iso, TOP_PROCESSES_LIMIT),
        ).fetchall()
    return [
        {
            "name": name,
            "avg_cpu_pct": round(avg, 2) if avg is not None else None,
            "peak_mem_mb": round(peak, 2) if peak is not None else None,
            "n": int(n),
        }
        for name, avg, peak, n in rows
    ]


def _open_read_only() -> sqlite3.Connection:
    path = Path(str(config.HISTORY_DB)).resolve()
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5.0)


def _maintenance(since_iso: str) -> dict[str, Any]:
    """Action counts + success rate from maintenance_actions (read-only)."""
    empty = {"total": 0, "ok": 0, "failed": 0, "success_rate": None, "by_action": []}
    if not Path(str(config.HISTORY_DB)).exists():
        return empty
    try:
        conn = _open_read_only()
        try:
            if not _table_exists(conn, "maintenance_actions"):
                return empty
            total, ok = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(ok), 0) "
                "FROM maintenance_actions WHERE ts >= ?",
                (since_iso,),
            ).fetchone()
            by_action = conn.execute(
                "SELECT action, COUNT(*), COALESCE(SUM(ok), 0) "
                "FROM maintenance_actions WHERE ts >= ? "
                "GROUP BY action ORDER BY COUNT(*) DESC",
                (since_iso,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        logger.warning("maintenance overview query failed", exc_info=True)
        return empty

    total, ok = int(total), int(ok)
    actions: list[dict[str, Any]] = []
    for action, count, ok_count in by_action:
        count, ok_count = int(count), int(ok_count)
        actions.append({
            "action": action,
            "count": count,
            "ok": ok_count,
            "failed": count - ok_count,
            "success_rate": round(ok_count / count, 4) if count else None,
        })
    return {
        "total": total,
        "ok": ok,
        "failed": total - ok,
        "success_rate": round(ok / total, 4) if total else None,
        "by_action": actions,
    }


def _security(since_iso: str) -> dict[str, Any]:
    """Event counts by kind + top source IPs from security_events."""
    with sec_persistence._lock:
        conn = sec_persistence._get_conn()
        if not _table_exists(conn, "security_events"):
            return {"total": 0, "by_kind": [], "top_sources": []}
        total = conn.execute(
            "SELECT COUNT(*) FROM security_events WHERE ts >= ?", (since_iso,)
        ).fetchone()[0]
        by_kind = conn.execute(
            "SELECT kind, COUNT(*) AS c FROM security_events WHERE ts >= ? "
            "GROUP BY kind ORDER BY c DESC LIMIT ?",
            (since_iso, BY_KIND_LIMIT),
        ).fetchall()
        top_sources = conn.execute(
            "SELECT source_ip, COUNT(*) AS c FROM security_events "
            "WHERE ts >= ? AND source_ip IS NOT NULL AND source_ip != '' "
            "GROUP BY source_ip ORDER BY c DESC LIMIT ?",
            (since_iso, TOP_SOURCES_LIMIT),
        ).fetchall()
    return {
        "total": int(total),
        "by_kind": [{"kind": kind, "count": int(c)} for kind, c in by_kind],
        "top_sources": [{"source_ip": ip, "count": int(c)} for ip, c in top_sources],
    }


def compute_insights(range_str: str = "24h") -> dict[str, Any]:
    """Aggregated /insights overview for ``24h|7d|30d`` (read-only)."""
    if range_str not in RANGES:
        raise ValueError(f"range must be one of {sorted(RANGES)}")
    range_sec = RANGES[range_str]
    since = time.time() - range_sec

    report = insights.compute_anomalies(range_str)
    try:
        series, window = _trends(range_str, range_sec, since)
    except Exception:
        logger.exception("insights trends aggregation failed")
        series, window = {
            "range": range_str, "bucket_sec": max(range_sec // config.HISTORY_MAX_POINTS, 1),
            "count": 0, "points": [],
        }, None

    cutoff_dt = datetime.now(UTC) - timedelta(seconds=range_sec)
    disk_cutoff = cutoff_dt.strftime(_MICRO_Z)
    maint_cutoff = cutoff_dt.strftime(_SEC_Z)
    sec_cutoff = (datetime.now() - timedelta(seconds=range_sec)).isoformat()

    try:
        disks = _disk_usage(disk_cutoff)
    except Exception:
        logger.exception("insights disk aggregation failed")
        disks = []
    try:
        procs = _top_processes(disk_cutoff)
    except Exception:
        logger.exception("insights top-processes aggregation failed")
        procs = []
    maintenance = _maintenance(maint_cutoff)
    try:
        security = _security(sec_cutoff)
    except Exception:
        logger.exception("insights security aggregation failed")
        security = {"total": 0, "by_kind": [], "top_sources": []}

    return {
        "range": range_str,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "effective_window": window,
        "trends": series,
        "disk": disks,
        "top_processes": procs,
        "maintenance": maintenance,
        "security": security,
        "baseline": report["baseline"],
        "anomalies": report["anomalies"],
    }


__all__ = ["BY_KIND_LIMIT", "RANGES", "TOP_PROCESSES_LIMIT", "TOP_SOURCES_LIMIT", "compute_insights"]
