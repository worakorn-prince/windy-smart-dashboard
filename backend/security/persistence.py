"""Persistent security event log (SQLite, WAL).

Stores every security event emitted on the /ws/security channel into the same
SQLite database used by metrics history (config.HISTORY_DB) so the Security
page can show past events, not just the live stream.

Everything here is best-effort: a missing/corrupt database must never take
down the WS path — record_event() returns False and list_events() returns []
instead of raising.
"""
from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Any

import config

logger = logging.getLogger("dashboard.security.persistence")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events(
    id INTEGER PRIMARY KEY,
    ts TEXT,
    kind TEXT,
    source_ip TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_security_events_ts ON security_events(ts);
"""

_MAX_LIST_LIMIT = 1000

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """Open (once) the shared history database; mirrors history.py's setup."""
    global _conn
    if _conn is None:
        conn = sqlite3.connect(config.HISTORY_DB, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.commit()
        except sqlite3.Error:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
            raise
        _conn = conn
    return _conn


def _reset_conn() -> None:
    """Drop the cached connection so the next call retries a fresh one."""
    global _conn
    with _lock:
        if _conn is not None:
            with contextlib.suppress(sqlite3.Error):
                _conn.close()
            _conn = None


def close() -> None:
    """Close the cached connection (tests and shutdown)."""
    _reset_conn()


def record_event(kind: str, source_ip: str, detail: dict[str, Any] | None = None,
                 ts: str | None = None) -> bool:
    """Persist one security event; return True on success, False on any DB error."""
    try:
        payload = json.dumps(detail if isinstance(detail, dict) else {},
                             ensure_ascii=False, default=str)
        stamp = ts or datetime.now().isoformat()
        with _lock:
            conn = _get_conn()
            conn.execute(
                "INSERT INTO security_events(ts, kind, source_ip, detail) VALUES (?,?,?,?)",
                (stamp, str(kind), str(source_ip or ""), payload),
            )
            conn.commit()
        return True
    except Exception:
        _reset_conn()
        logger.warning("security event not persisted", exc_info=True)
        return False


def list_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return up to `limit` events, newest first, with detail parsed back to dict."""
    try:
        n = max(0, min(int(limit), _MAX_LIST_LIMIT))
    except (TypeError, ValueError):
        n = 50
    try:
        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT id, ts, kind, source_ip, detail FROM security_events "
                "ORDER BY ts DESC, id DESC LIMIT ?",
                (n,),
            ).fetchall()
    except Exception:
        _reset_conn()
        logger.warning("security events not listed", exc_info=True)
        return []
    events: list[dict[str, Any]] = []
    for row_id, ts, kind, ip, raw in rows:
        try:
            detail = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            detail = {"raw": raw}
        if not isinstance(detail, dict):
            detail = {"value": detail}
        events.append({"id": row_id, "ts": ts, "kind": kind,
                       "source_ip": ip, "detail": detail})
    return events
