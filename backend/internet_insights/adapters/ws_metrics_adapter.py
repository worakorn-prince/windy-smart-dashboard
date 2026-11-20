"""WS Metrics adapter - subscribes to /ws/metrics broadcasts."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    pass

logger = logging.getLogger("dashboard.internet_insights.adapters.ws_metrics")


class WSMetricsAdapter:
    """Subscribe to /ws/metrics broadcasts for live ping/throughput."""

    def __init__(self):
        self._callbacks: list[Callable[[dict], None]] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for metrics updates."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[dict], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start(self) -> None:
        """Start listening to metrics channel."""
        if self._running:
            return
        self._running = True
        # Note: The existing ConnectionManager broadcasts to all connected WebSocket clients.
        # For Internet Insights, we hook into the broadcast by wrapping the manager's broadcast.
        # This is a simplified approach - in production, we'd add a proper subscriber pattern.
        logger.info("WSMetricsAdapter started (passive - receives via existing WS clients)")

    async def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._task:
            self._task.cancel()
            with asyncio.suppress(asyncio.CancelledError):
                await self._task

    def _notify(self, data: dict) -> None:
        """Notify all callbacks."""
        for callback in self._callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.warning("WSMetricsAdapter callback error: %s", e)

    def get_latest_ping(self) -> dict[str, Any] | None:
        """Get latest ping from metrics cache (if available)."""
        # This would need integration with the metrics loop's ping state
        # For now, return None - the QualityCollector handles active probing
        return None

    def get_latest_throughput(self) -> dict[str, Any] | None:
        """Get latest throughput from metrics cache."""
        return None
