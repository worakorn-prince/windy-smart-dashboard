"""Persistent metrics history (SQLite, WAL).

Samples cheap scalar metrics every HISTORY_SAMPLE_INTERVAL seconds and serves
bucketed aggregates for GET /api/history. Rate counters live in this module —
never call metrics.disk_snapshot()/network_snapshot() here, that would corrupt
their rate timestamps.
"""
from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
from typing import Any, Literal

import psutil

import config
import metrics

HistoryRange = Literal["1h", "6h", "24h"]

logger = logging.getLogger("dashboard.history")

_SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples(
    ts REAL PRIMARY KEY,
    cpu_pct REAL, ram_pct REAL, swap_pct REAL,
    cpu_temp REAL, gpu_temp REAL, disk_temp_max REAL,
    cpu_power_w REAL, gpu_power_w REAL,
    net_sent_bps REAL, net_recv_bps REAL,
    disk_read_bps REAL, disk_write_bps REAL
);
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
"""

_COLS = ("cpu_pct", "ram_pct", "swap_pct", "cpu_temp", "gpu_temp", "disk_temp_max",
         "cpu_power_w", "gpu_power_w",
         "net_sent_bps", "net_recv_bps",
         "disk_read_bps", "disk_write_bps")

_RANGES: dict[str, int] = {"1h": 3600, "6h": 21600, "24h": 86400}

_lock = threading.Lock()
_prev_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

_prev_net = psutil.net_io_counters()
_prev_disk = psutil.disk_io_counters()
_prev_ts = time.monotonic()
_last_cleanup = 0.0
_last_sample_ts = 0.0


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.HISTORY_DB, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.executescript(_SCHEMA)
        _conn.commit()
        _migrate(_conn)
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    version = row[0] if row and row[0] else 0
    if version == 0:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(samples)")}
        version = 2 if {"cpu_power_w", "gpu_power_w"} <= existing else 1
    if version < 2:
        existing = {r[1] for r in conn.execute("PRAGMA table_info(samples)")}
        for col in ("cpu_power_w", "gpu_power_w"):
            if col not in existing:
                conn.execute(f"ALTER TABLE samples ADD COLUMN {col} REAL")
        version = 2
    conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (version,))
    conn.commit()


def record_sample() -> dict[str, Any]:
    """Collect one sample and persist it, returning the stored row."""
    global _prev_net, _prev_disk, _prev_ts, _last_cleanup, _last_sample_ts

    now_mono = time.monotonic()
    cur_net = psutil.net_io_counters()
    cur_disk = psutil.disk_io_counters()
    with _prev_lock:
        dt = max(now_mono - _prev_ts, 0.001)
        net_sent_bps = max((cur_net.bytes_sent - _prev_net.bytes_sent) / dt, 0)
        net_recv_bps = max((cur_net.bytes_recv - _prev_net.bytes_recv) / dt, 0)
        disk_read_bps = max((cur_disk.read_bytes - _prev_disk.read_bytes) / dt, 0)
        disk_write_bps = max((cur_disk.write_bytes - _prev_disk.write_bytes) / dt, 0)
        _prev_net, _prev_disk, _prev_ts = cur_net, cur_disk, now_mono

    s = metrics.light_snapshot()
    ts = time.time()
    if ts <= _last_sample_ts:
        ts = _last_sample_ts + 0.001
    _last_sample_ts = ts
    s.update({
        "ts": ts,
        "net_sent_bps": round(net_sent_bps),
        "net_recv_bps": round(net_recv_bps),
        "disk_read_bps": round(disk_read_bps),
        "disk_write_bps": round(disk_write_bps),
    })

    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s["ts"], s["cpu_pct"], s["ram_pct"], s["swap_pct"],
             s["cpu_temp"], s["gpu_temp"], s["disk_temp_max"],
             s["cpu_power_w"], s["gpu_power_w"],
             s["net_sent_bps"], s["net_recv_bps"],
             s["disk_read_bps"], s["disk_write_bps"]),
        )
        conn.commit()

    if time.time() - _last_cleanup > 3600:
        _last_cleanup = time.time()
        cutoff = time.time() - config.HISTORY_RETENTION_HOURS * 3600
        with _lock:
            _get_conn().execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
            _get_conn().commit()
            with contextlib.suppress(sqlite3.Error):
                _get_conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")

    return s


def query_range(range_str: HistoryRange = "1h") -> dict[str, Any]:
    """Return bucketed averages for a range, serving the history endpoint."""
    range_sec = _RANGES.get(range_str, 3600)
    bucket = max(range_sec // config.HISTORY_MAX_POINTS, 1)
    since = time.time() - range_sec

    sel = ", ".join(f"AVG({c}) AS {c}" for c in _COLS)
    sql = (f"SELECT CAST(ts/{bucket} AS INTEGER)*{bucket} AS b, MAX(ts) AS last_ts, {sel} "
           f"FROM samples WHERE ts >= ? GROUP BY b ORDER BY b")

    with _lock:
        rows = _get_conn().execute(sql, (since,)).fetchall()

    points: list[dict[str, Any]] = []
    for r in rows:
        p: dict[str, Any] = {"ts": r[0]}
        for i, col in enumerate(_COLS, start=2):
            v = r[i]
            p[col] = round(v, 2) if v is not None else None
        points.append(p)

    return {"range": range_str, "bucket_sec": bucket,
            "count": len(points), "points": points}
