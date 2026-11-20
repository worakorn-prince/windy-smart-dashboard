"""History adapter - reads history.query_range() (read-only access to legacy samples)."""

from __future__ import annotations

import logging
from typing import Any, Literal

import history

logger = logging.getLogger("dashboard.internet_insights.adapters.history")

HistoryRange = Literal["5m", "1h", "6h", "24h"]


class HistoryAdapter:
    """Read history.query_range() — read-only access to legacy samples."""

    def query(self, range_str: HistoryRange = "1h") -> dict[str, Any]:
        """Query historical metrics samples."""
        try:
            return history.query_range(range_str)
        except Exception as e:
            logger.warning("Failed to query history range %s: %s", range_str, e)
            return {"range": range_str, "bucket_sec": 0, "count": 0, "points": []}

    def query_quality_history(self, range_str: HistoryRange = "1h") -> dict[str, Any]:
        """Query historical quality/latency data from legacy samples."""
        # Legacy history only has net_sent_bps, net_recv_bps, not quality probes
        # This is for backwards compatibility - returns network throughput history
        data = self.query(range_str)
        points = data.get("points", [])
        # Extract network throughput as quality proxy
        quality_points = []
        for p in points:
            quality_points.append({
                "ts": p.get("ts"),
                "net_sent_bps": p.get("net_sent_bps"),
                "net_recv_bps": p.get("net_recv_bps"),
            })
        return {
            "range": range_str,
            "bucket_sec": data.get("bucket_sec", 0),
            "count": len(quality_points),
            "points": quality_points,
        }

    def query_interface_history(self, range_str: HistoryRange = "1h") -> dict[str, Any]:
        """Query historical interface data from legacy samples."""
        # Legacy history doesn't have per-interface data
        # Returns aggregate network data as fallback
        data = self.query(range_str)
        points = data.get("points", [])
        interface_points = []
        for p in points:
            interface_points.append({
                "ts": p.get("ts"),
                "send_bps": p.get("net_sent_bps"),
                "recv_bps": p.get("net_recv_bps"),
            })
        return {
            "range": range_str,
            "bucket_sec": data.get("bucket_sec", 0),
            "count": len(interface_points),
            "points": interface_points,
        }
