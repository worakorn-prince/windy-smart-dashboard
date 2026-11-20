"""NetCache adapter - reads main._net_connection_rows() (5s TTL cache, read-only)."""

from __future__ import annotations

import logging
import socket
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import main

logger = logging.getLogger("dashboard.internet_insights.adapters.net_cache")


def _get_main_module() -> main:
    """Lazy import to avoid circular dependency."""
    import main as main_module
    return main_module


class NetCacheAdapter:
    """Read main._net_connection_rows() — 5s TTL cache, read-only."""

    def get_connections(self) -> list[dict[str, Any]]:
        """Get cached inet socket rows."""
        try:
            return _get_main_module()._net_connection_rows()
        except Exception as e:
            logger.warning("Failed to get net connections: %s", e)
            return []

    def get_process_connections(self, pid: int) -> tuple[list[dict[str, Any]], int]:
        """Get ports and connection count for a process."""
        try:
            return _get_main_module()._process_net_info(pid)
        except Exception as e:
            logger.warning("Failed to get process net info for pid %d: %s", pid, e)
            return [], 0

    def get_active_connections(self, protocol: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
        """Get active connections with optional filters."""
        connections = self.get_connections()
        if protocol:
            connections = [
                c for c in connections
                if c.get("type") == (socket.SOCK_STREAM if protocol == "tcp" else socket.SOCK_DGRAM)
            ]
        if state:
            connections = [c for c in connections if c.get("status") == state]
        return connections
