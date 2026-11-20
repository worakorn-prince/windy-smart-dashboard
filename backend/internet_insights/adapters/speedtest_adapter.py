"""Speedtest adapter - wraps speedtest_worker.run_speedtest_async()."""

from __future__ import annotations

import logging
from typing import Any

import speedtest_worker

logger = logging.getLogger("dashboard.internet_insights.adapters.speedtest")


class SpeedtestAdapter:
    """Wrap speedtest_worker.run_speedtest_async() — identical behavior."""

    async def run(self) -> dict[str, Any]:
        """Run the full speed test: latency, then download, then upload."""
        try:
            return await speedtest_worker.run_speedtest_async()
        except Exception as e:
            logger.exception("Speedtest failed")
            return {"ok": False, "error": str(e), "timestamp": __import__("time").time()}
