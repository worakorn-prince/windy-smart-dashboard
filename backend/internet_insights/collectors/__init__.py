"""Collector base classes and interfaces."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .quality import QualityCollector as QualityCollector
from .interface import InterfaceCollector as InterfaceCollector
from .tcp_stats import TcpStatsCollector as TcpStatsCollector
from .dns import DnsCollector as DnsCollector
from .route import RouteCollector as RouteCollector

__all__ = ["Collector", "CollectorConfig", "InterfaceCollector", "QualityCollector", "TcpStatsCollector", "DnsCollector", "RouteCollector"]

logger = logging.getLogger("dashboard.internet_insights.collectors")


@dataclass
class CollectorConfig:
    interval_sec: float
    timeout_sec: float = 30.0
    enabled: bool = True
    max_concurrent_runs: int = 1


class Collector(ABC):
    """Base collector class with lifecycle management."""

    def __init__(self, config: CollectorConfig, repository: Any):
        self.config = config
        self.repository = repository
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_start: float | None = None
        self._last_run_duration: float | None = None
        self._consecutive_failures = 0
        self._run_lock = asyncio.Lock()

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique collector name."""
        ...

    @abstractmethod
    async def collect(self) -> Any:
        """Perform one collection cycle."""
        ...

    async def start(self) -> None:
        """Start the collector loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the collector loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run_loop(self) -> None:
        while self._running:
            if not self.config.enabled:
                await asyncio.sleep(self.config.interval_sec)
                continue

            # Single-flight: don't start new run if previous still executing
            if self._run_lock.locked():
                logger.debug("Collector %s: previous run still executing, skipping", self.name)
                await asyncio.sleep(self.config.interval_sec)
                continue

            start = time.monotonic()
            self._last_run_start = start
            try:
                await asyncio.wait_for(self.collect(), timeout=self.config.timeout_sec)
                self._consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning("Collector %s failed (%d): %s", self.name, self._consecutive_failures, e)
            finally:
                self._last_run_duration = time.monotonic() - start

            # Sleep for remaining interval
            sleep_time = max(0.1, self.config.interval_sec - self._last_run_duration)
            await asyncio.sleep(sleep_time)

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "interval_sec": self.config.interval_sec,
            "last_run_duration_sec": self._last_run_duration,
            "consecutive_failures": self._consecutive_failures,
        }
