"""Per-process CPU/RAM sample history (SQLite, WAL).

Stores the top-N processes (by memory) each history tick so the process
drilldown panel can render a small CPU/RAM sparkline. This module deliberately
uses the same SQLite file as `history` (``config.HISTORY_DB``) but its own
connection/lock; it must never import ``main`` or ``history``.
"""
from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
from datetime import datetime, UTC
from typing import Any

import config

logger = logging.getLogger("dashboard.process_history")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS process_samples(
    ts TEXT,
    pid INTEGER,
    name TEXT,
    cpu_pct REAL,
    mem_mb REAL
);
CREATE INDEX IF NOT EXISTS idx_process_samples_pid_ts
    ON process_samples(pid, ts);
"""

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _now_iso() -> str:
    """Fixed-width UTC ISO-8601 so TEXT ordering matches chronological order."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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


def record_samples(procs: list[dict[str, Any]]) -> int:
    """Persist one row per process sample; best-effort, never raises.

    Each item is expected to carry ``pid``, ``name``, ``cpu_pct`` and
    ``mem_mb``. An optional ``ts`` overrides the generated timestamp.
    Returns the number of rows written (0 on failure).
    """
    if not procs:
        return 0
    now = _now_iso()
    rows = [
        (
            p.get("ts") or now,
            int(p.get("pid") or 0),
            str(p.get("name") or ""),
            float(p.get("cpu_pct") or 0.0),
            float(p.get("mem_mb") or 0.0),
        )
        for p in procs
    ]
    try:
        with _lock:
            conn = _get_conn()
            conn.executemany(
                "INSERT INTO process_samples(ts, pid, name, cpu_pct, mem_mb) "
                "VALUES (?,?,?,?,?)",
                rows,
            )
            conn.commit()
    except Exception:
        logger.exception("process sample record failed")
        return 0
    return len(rows)


def get_history(pid: int, limit: int = 60) -> list[dict[str, Any]]:
    """Return the newest ``limit`` samples for ``pid``, oldest first (for graphs)."""
    limit = max(1, min(int(limit), 1000))
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT ts, cpu_pct, mem_mb FROM process_samples "
            "WHERE pid = ? ORDER BY ts DESC LIMIT ?",
            (int(pid), limit),
        ).fetchall()
    return [
        {"ts": r[0], "cpu_pct": r[1], "mem_mb": r[2]}
        for r in reversed(rows)
    ]


def prune(days: float = 7) -> int:
    """Delete samples older than ``days`` days; return rows removed."""
    days = max(float(days), 0.0)
    cutoff = _now_iso() if days == 0 else datetime.fromtimestamp(
        time.time() - days * 86400.0, tz=UTC
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with _lock:
        conn = _get_conn()
        deleted = conn.execute(
            "DELETE FROM process_samples WHERE ts < ?", (cutoff,)
        ).rowcount
        conn.commit()
        with contextlib.suppress(sqlite3.Error):
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return max(deleted, 0)
