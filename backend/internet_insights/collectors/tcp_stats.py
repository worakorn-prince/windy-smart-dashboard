"""TCP statistics collector using Windows GetTcpStatisticsEx API with psutil fallback."""

from __future__ import annotations

import asyncio
import ctypes
import logging
import platform
import time
from dataclasses import dataclass
from typing import Any

from ..config import get_config
from ..storage.repositories import TcpStatsSample, TcpStatsRepository

logger = logging.getLogger("dashboard.internet_insights.collectors.tcp_stats")


@dataclass
class TcpStats:
    active_opens: int
    passive_opens: int
    failed_attempts: int
    established_resets: int
    current_established: int
    segments_sent: int
    segments_received: int
    segments_retransmitted: int
    source: str


class TcpStatsCollector:
    """Background collector for TCP statistics (Windows GetTcpStatisticsEx + psutil fallback)."""

    def __init__(self, repository: TcpStatsRepository | None = None):
        self.config = get_config()
        self.repository = repository or TcpStatsRepository()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_start: float | None = None
        self._last_run_duration: float | None = None
        self._consecutive_failures = 0
        self._run_lock = asyncio.Lock()
        self._is_windows = platform.system() == "Windows"
        self._iphlpapi = None
        self._init_windows_api()

    @property
    def name(self) -> str:
        return "tcp_stats"

    def _init_windows_api(self) -> None:
        """Initialize Windows IPHLPAPI for GetTcpStatisticsEx."""
        if not self._is_windows:
            return
        try:
            self._iphlpapi = ctypes.windll.LoadLibrary("iphlpapi.dll")
            # Define GetTcpStatisticsEx function signature
            # DWORD GetTcpStatisticsEx(PMIB_TCPSTATS pStats, DWORD dwFamily)
            self._iphlpapi.GetTcpStatisticsEx.argtypes = [ctypes.POINTER(ctypes.c_byte), ctypes.c_ulong]
            self._iphlpapi.GetTcpStatisticsEx.restype = ctypes.c_ulong
            logger.debug("Windows IPHLPAPI loaded successfully")
        except Exception as e:
            logger.warning("Failed to load Windows IPHLPAPI: %s, will use psutil fallback", e)
            self._iphlpapi = None

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
                await self._collect_tcp_stats()
                self._consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning("TcpStatsCollector failed (%d): %s", self._consecutive_failures, e)
            finally:
                self._last_run_duration = time.monotonic() - start

            sleep_time = max(0.1, self.config.tcp_stats_interval - self._last_run_duration)
            await asyncio.sleep(sleep_time)

    async def _collect_tcp_stats(self) -> None:
        """Collect TCP statistics and store sample."""
        stats = await self._get_tcp_stats()
        ts = time.time()

        sample = TcpStatsSample(
            ts=ts,
            active_opens=stats.active_opens,
            passive_opens=stats.passive_opens,
            failed_attempts=stats.failed_attempts,
            established_resets=stats.established_resets,
            current_established=stats.current_established,
            segments_sent=stats.segments_sent,
            segments_received=stats.segments_received,
            segments_retransmitted=stats.segments_retransmitted,
            source=stats.source,
        )

        await asyncio.to_thread(self.repository.insert, sample)

    async def _get_tcp_stats(self) -> TcpStats:
        """Get TCP statistics from Windows API or psutil fallback."""
        if self._is_windows and self._iphlpapi:
            stats = await asyncio.to_thread(self._get_windows_tcp_stats)
            if stats:
                return stats

        # Fallback to psutil
        return await asyncio.to_thread(self._get_psutil_tcp_stats)

    def _get_windows_tcp_stats(self) -> TcpStats | None:
        """Get TCP statistics using Windows GetTcpStatisticsEx API."""
        try:
            # MIB_TCPSTATS structure for GetTcpStatisticsEx
            # Fields: RtoAlgorithm, RtoMin, RtoMax, MaxConn, ActiveOpens, PassiveOpens,
            # AttemptFails, EstabResets, CurrEstab, InSegs, OutSegs, RetransSegs, ...
            class MIB_TCPSTATS(ctypes.Structure):
                _fields_ = [
                    ("RtoAlgorithm", ctypes.c_ulong),
                    ("RtoMin", ctypes.c_ulong),
                    ("RtoMax", ctypes.c_ulong),
                    ("MaxConn", ctypes.c_ulong),
                    ("ActiveOpens", ctypes.c_ulong),
                    ("PassiveOpens", ctypes.c_ulong),
                    ("AttemptFails", ctypes.c_ulong),
                    ("EstabResets", ctypes.c_ulong),
                    ("CurrEstab", ctypes.c_ulong),
                    ("InSegs", ctypes.c_ulong),
                    ("OutSegs", ctypes.c_ulong),
                    ("RetransSegs", ctypes.c_ulong),
                    ("InErrs", ctypes.c_ulong),
                    ("OutRsts", ctypes.c_ulong),
                    ("NumConns", ctypes.c_ulong),
                ]

            tcp_stats = MIB_TCPSTATS()
            # AF_INET = 2 for IPv4, AF_INET6 = 23 for IPv6
            # Use AF_INET (2) for IPv4 stats
            result = self._iphlpapi.GetTcpStatisticsEx(ctypes.byref(tcp_stats), 2)

            if result == 0:  # NO_ERROR
                return TcpStats(
                    active_opens=tcp_stats.ActiveOpens,
                    passive_opens=tcp_stats.PassiveOpens,
                    failed_attempts=tcp_stats.AttemptFails,
                    established_resets=tcp_stats.EstabResets,
                    current_established=tcp_stats.CurrEstab,
                    segments_sent=tcp_stats.OutSegs,
                    segments_received=tcp_stats.InSegs,
                    segments_retransmitted=tcp_stats.RetransSegs,
                    source="GetTcpStatisticsEx",
                )
            else:
                logger.warning("GetTcpStatisticsEx returned error code: %d", result)
        except Exception as e:
            logger.warning("Failed to get TCP stats via Windows API: %s", e)
        return None

    def _get_psutil_tcp_stats(self) -> TcpStats:
        """Get TCP statistics using psutil fallback."""
        import psutil

        try:
            net_io = psutil.net_io_counters()
            # psutil provides limited TCP stats, estimate where needed
            connections = psutil.net_connections(kind="tcp")
            established = sum(1 for c in connections if c.status == "ESTABLISHED")

            return TcpStats(
                active_opens=0,  # Not available in psutil
                passive_opens=0,  # Not available in psutil
                failed_attempts=0,  # Not available in psutil
                established_resets=0,  # Not available in psutil
                current_established=established,
                segments_sent=net_io.packets_sent,
                segments_received=net_io.packets_recv,
                segments_retransmitted=0,  # Not available in psutil
                source="psutil_fallback",
            )
        except Exception as e:
            logger.warning("Failed to get TCP stats via psutil: %s", e)
            return TcpStats(
                active_opens=0,
                passive_opens=0,
                failed_attempts=0,
                established_resets=0,
                current_established=0,
                segments_sent=0,
                segments_received=0,
                segments_retransmitted=0,
                source="estimated",
            )

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "interval_sec": self.config.tcp_stats_interval,
            "last_run_duration_sec": self._last_run_duration,
            "consecutive_failures": self._consecutive_failures,
            "platform": platform.system(),
            "windows_api_available": self._iphlpapi is not None,
        }


import contextlib