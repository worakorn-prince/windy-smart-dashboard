"""Quality collector for latency, jitter, and packet loss probes."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from ..config import get_config
from ..storage.repositories import QualitySample, QualitySampleRepository
from ..adapters.ping_adapter import PingAdapter

logger = logging.getLogger("dashboard.internet_insights.collectors.quality")


@dataclass
class ProbeTarget:
    target_id: str
    address: str
    probe_type: str
    interval_sec: float


class QualityCollector:
    """Background collector for internet quality probes (gateway, primary, secondary)."""

    def __init__(self, repository: QualitySampleRepository | None = None, ping_adapter: PingAdapter | None = None):
        self.config = get_config()
        self.repository = repository or QualitySampleRepository()
        self.ping_adapter = ping_adapter or PingAdapter()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_start: float | None = None
        self._last_run_duration: float | None = None
        self._consecutive_failures = 0
        self._run_lock = asyncio.Lock()

        # Define probe targets
        self.targets = [
            ProbeTarget(
                target_id="gateway",
                address=self._get_gateway(),
                probe_type="tcp",
                interval_sec=self.config.quality_gateway_interval,
            ),
            ProbeTarget(
                target_id="primary",
                address=self.config.primary_target,
                probe_type="tcp",
                interval_sec=self.config.quality_primary_interval,
            ),
            ProbeTarget(
                target_id="secondary",
                address=self.config.secondary_target,
                probe_type="tcp",
                interval_sec=self.config.quality_secondary_interval,
            ),
        ]
        self._next_probe_time: dict[str, float] = {t.target_id: 0.0 for t in self.targets}

    @property
    def name(self) -> str:
        return "quality"

    def _get_gateway(self) -> str:
        """Get default gateway from metrics adapter."""
        try:
            from ..adapters.metrics_adapter import MetricsAdapter
            adapter = MetricsAdapter()
            snapshot = adapter.get_network_snapshot()
            for gw in snapshot.get("gateways", []):
                return gw
            # Fallback to common gateway
            return "192.168.1.1"
        except Exception:
            return "192.168.1.1"

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

            now = time.monotonic()
            start = now
            self._last_run_start = start

            try:
                # Check each target if it's time to probe
                probe_tasks = []
                for target in self.targets:
                    if now >= self._next_probe_time[target.target_id]:
                        self._next_probe_time[target.target_id] = now + target.interval_sec
                        probe_tasks.append(self._probe_target(target))

                if probe_tasks:
                    await asyncio.gather(*probe_tasks, return_exceptions=True)

                self._consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning("QualityCollector failed (%d): %s", self._consecutive_failures, e)
            finally:
                self._last_run_duration = time.monotonic() - start

            # Sleep a short interval and check again
            await asyncio.sleep(1.0)

    async def _probe_target(self, target: ProbeTarget) -> None:
        """Probe a single target and store the result."""
        timeout_sec = self.config.probe_timeout_ms / 1000.0
        try:
            rtt_ms = await self.ping_adapter.ping(target.address, timeout=timeout_sec)
            if rtt_ms is not None:
                status = "success"
                error_code = None
            else:
                status = "timeout"
                error_code = "TIMEOUT"
                rtt_ms = None
        except TimeoutError:
            status = "timeout"
            error_code = "TIMEOUT"
            rtt_ms = None
        except Exception as e:
            status = "error"
            error_code = type(e).__name__
            rtt_ms = None

        sample = QualitySample(
            ts=time.time(),
            target_id=target.target_id,
            probe_type=target.probe_type,
            rtt_ms=rtt_ms,
            status=status,
            error_code=error_code,
            timeout_ms=self.config.probe_timeout_ms,
            interface_id=None,
        )

        # Store in background to not block the loop
        await asyncio.to_thread(self.repository.insert, sample)

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "targets": [{"target_id": t.target_id, "address": t.address, "interval_sec": t.interval_sec} for t in self.targets],
            "last_run_duration_sec": self._last_run_duration,
            "consecutive_failures": self._consecutive_failures,
        }


# Import contextlib at top level for _run_loop
import contextlib
