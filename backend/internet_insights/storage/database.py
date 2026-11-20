"""SQLite database connection for Internet Insights (WAL mode, separate from history.py)."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..config import get_config

logger = logging.getLogger("dashboard.internet_insights.storage")


class InternetInsightsDB:
    """Thread-local SQLite connection with WAL mode for Internet Insights tables."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_config().db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database file and run migrations."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Test connection and run migrations
        conn = self._get_conn()
        from .migrations import apply_migrations
        apply_migrations(conn)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection with WAL pragmas."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=5.0,
                isolation_level=None,  # autocommit mode; explicit transactions
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single statement with write lock."""
        with self._lock:
            return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params_seq: list[tuple]) -> sqlite3.Cursor:
        """Execute many statements with write lock."""
        with self._lock:
            return self._get_conn().executemany(sql, params_seq)

    def executescript(self, sql: str) -> sqlite3.Cursor:
        """Execute a script with write lock."""
        with self._lock:
            return self._get_conn().executescript(sql)

    def commit(self) -> None:
        """Commit the current transaction."""
        with self._lock:
            self._get_conn().commit()

    def close(self) -> None:
        """Close thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def fetchone(self, sql: str, params: tuple = ()) -> Any | None:
        """Execute and fetch one row."""
        with self._lock:
            return self._get_conn().execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[Any]:
        """Execute and fetch all rows."""
        with self._lock:
            return self._get_conn().execute(sql, params).fetchall()


# Global database instance
_db: InternetInsightsDB | None = None


def get_db() -> InternetInsightsDB:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        _db = InternetInsightsDB()
    return _db
