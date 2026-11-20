"""Interface collector for per-interface traffic counters and errors."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import psutil

from ..config import get_config
from ..storage.repositories import InterfaceSample, InterfaceSampleRepository

logger = logging.getLogger("dashboard.internet_insights.collectors.interface")


class InterfaceCollector:
    """Background collector for per-interface traffic samples."""

    def __init__(self, repository: InterfaceSampleRepository | None = None):
        self.config = get_config()
        self.repository = repository or InterfaceSampleRepository()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_start: float | None = None
        self._last_run_duration: float | None = None
        self._consecutive_failures = 0
        self._run_lock = asyncio.Lock()

        # Previous counters for rate calculation
        self._prev_counters: dict[str, psutil._common.snicstats] = {}
        self._prev_ts: float = time.monotonic()

    @property
    def name(self) -> str:
        return "interface"

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run_loop(self) -> None:
        while self._running:
            if self._run_lock.locked():
                await asyncio.sleep(0.5)
                continue

            start = time.monotonic()
            self._last_run_start = start

            try:
                await self._collect_interfaces()
                self._consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning("InterfaceCollector failed (%d): %s", self._consecutive_failures, e)
            finally:
                self._last_run_duration = time.monotonic() - start

            sleep_time = max(0.1, self.config.interface_interval - self._last_run_duration)
            await asyncio.sleep(sleep_time)

    async def _collect_interfaces(self) -> None:
        """Collect interface counters and store samples."""
        now_mono = time.monotonic()
        dt = max(now_mono - self._prev_ts, 0.001)

        # Get current counters in thread to avoid blocking
        counters = await asyncio.to_thread(psutil.net_io_counters, pernic=True)

        samples = []
        for interface_id, cur in counters.items():
            prev = self._prev_counters.get(interface_id)
            if prev is None:
                # First sample for this interface - no rate calculation yet
                send_bps = 0.0
                recv_bps = 0.0
            else:
                send_bps = max((cur.bytes_sent - prev.bytes_sent) / dt, 0.0)
                recv_bps = max((cur.bytes_recv - prev.bytes_recv) / dt, 0.0)

            # Get link status
            link_status = None
            try:
                stats = await asyncio.to_thread(psutil.net_if_stats)
                if interface_id in stats:
                    link_status = "up" if stats[interface_id].isup else "down"
            except Exception:
                link_status = "unknown"

            sample = InterfaceSample(
                ts=time.time(),
                interface_id=interface_id,
                bytes_sent=cur.bytes_sent,
                bytes_recv=cur.bytes_recv,
                send_bps=send_bps,
                recv_bps=recv_bps,
                packets_sent=cur.packets_sent,
                packets_recv=cur.packets_recv,
                errors_in=cur.errin,
                errors_out=cur.errout,
                discards_in=cur.dropin,
                discards_out=cur.dropout,
                link_status=link_status,
            )
            samples.append(sample)

        # Update previous counters
        self._prev_counters = counters
        self._prev_ts = now_mono

        # Store samples in background
        if samples:
            await asyncio.to_thread(self.repository.insert_batch, samples)

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "interval_sec": self.config.interface_interval,
            "last_run_duration_sec": self._last_run_duration,
            "consecutive_failures": self._consecutive_failures,
            "tracked_interfaces": list(self._prev_counters.keys()),
        }


import contextlib
