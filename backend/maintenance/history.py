"""Action history for the maintenance module.

Stored in the shared SQLite file at `config.HISTORY_DB` but in its **own table**
(`maintenance_actions`). The metrics tables (`samples`) managed by
`backend/history.py` are never touched here.

Every call opens a short-lived connection (no module-level singleton) so a
write from a request thread cannot leak state into the metrics history layer.
Logging failures must never break the action that is being logged.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import config

log = logging.getLogger(__name__)

TABLE = "maintenance_actions"
BUSY_TIMEOUT_MS = 5000

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS maintenance_actions("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts TEXT NOT NULL, "
    "action TEXT NOT NULL, "
    "target TEXT, "
    "ok INTEGER NOT NULL, "
    "duration_ms INTEGER, "
    "detail TEXT, "
    "error TEXT"
    ")"
)

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_maintenance_actions_ts "
    "ON maintenance_actions(ts)"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _db_path() -> Path:
    return Path(str(config.HISTORY_DB))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)
        conn.execute(_INDEX)
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def _as_detail(detail: Any) -> str | None:
    if detail is None:
        return None
    if isinstance(detail, str):
        return detail
    try:
        return json.dumps(detail, ensure_ascii=False, default=str)
    except Exception:
        return str(detail)


def record(
    action: str,
    *,
    target: str | None = None,
    ok: bool,
    duration_ms: int = 0,
    detail: Any = None,
    error: str | None = None,
) -> None:
    """Append one row. Never raises — a broken log must not fail the action."""
    conn: sqlite3.Connection | None = None
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO maintenance_actions "
            "(ts, action, target, ok, duration_ms, detail, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                _now_iso(),
                str(action),
                target,
                1 if ok is True else 0,
                int(duration_ms or 0),
                _as_detail(detail),
                None if error is None else str(error),
            ),
        )
        conn.commit()
    except Exception as exc:
        log.warning("maintenance history write failed (%s): %s", action, exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def query(limit: int = 100) -> list[dict[str, Any]]:
    """Newest-first rows, at most `limit` (1..1000)."""
    try:
        size = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        size = 100

    conn: sqlite3.Connection | None = None
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT id, ts, action, target, ok, duration_ms, detail, error "
            "FROM maintenance_actions ORDER BY id DESC LIMIT ?",
            (size,),
        ).fetchall()
    except Exception as exc:
        log.warning("maintenance history query failed: %s", exc)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return [
        {
            "id": int(row["id"]),
            "ts": row["ts"],
            "action": row["action"],
            "target": row["target"],
            "ok": bool(row["ok"]),
            "durationMs": int(row["duration_ms"] or 0),
            "detail": row["detail"],
            "error": row["error"],
        }
        for row in rows
    ]


def purge(days: int = 30) -> int:
    """Delete rows older than `days`; returns the number of removed rows."""
    try:
        window = int(days)
    except (TypeError, ValueError):
        window = 30
    if window <= 0:
        return 0

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=window)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")

    conn: sqlite3.Connection | None = None
    try:
        conn = _connect()
        cursor = conn.execute("DELETE FROM maintenance_actions WHERE ts < ?", (cutoff,))
        conn.commit()
        return int(cursor.rowcount or 0)
    except Exception as exc:
        log.warning("maintenance history purge failed: %s", exc)
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
