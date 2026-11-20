"""Tests for TCP Statistics Collector."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from internet_insights.collectors.tcp_stats import TcpStatsCollector, TcpStats
from internet_insights.storage.database import InternetInsightsDB
from internet_insights.storage.migrations import apply_migrations
from internet_insights.storage.repositories import TcpStatsRepository, TcpStatsSample


@pytest.fixture
def temp_db(tmp_path: Path) -> InternetInsightsDB:
    db_path = tmp_path / "test_tcp_stats.db"
    db = InternetInsightsDB(db_path)
    conn = db._get_conn()
    apply_migrations(conn)
    yield db
    db.close()


@pytest.fixture
def tcp_repo(temp_db: InternetInsightsDB) -> TcpStatsRepository:
    return TcpStatsRepository(temp_db)


class TestTcpStatsCollectorLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, tcp_repo: TcpStatsRepository):
        with patch("internet_insights.collectors.tcp_stats.TcpStatsCollector._get_tcp_stats", new_callable=AsyncMock) as mock_get_stats:
            mock_get_stats.return_value = TcpStats(
                active_opens=100,
                passive_opens=50,
                failed_attempts=2,
                established_resets=1,
                current_established=10,
                segments_sent=10000,
                segments_received=9500,
                segments_retransmitted=100,
                source="psutil_fallback",
            )

            collector = TcpStatsCollector(repository=tcp_repo)
            collector.config.tcp_stats_interval = 0.05

            await collector.start()
            assert collector._running is True
            assert collector._task is not None

            await asyncio.sleep(0.15)

            await collector.stop()
            assert collector._running is False

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, tcp_repo: TcpStatsRepository):
        with patch("internet_insights.collectors.tcp_stats.TcpStatsCollector._get_tcp_stats", new_callable=AsyncMock) as mock_get_stats:
            mock_get_stats.return_value = TcpStats(
                active_opens=100,
                passive_opens=50,
                failed_attempts=2,
                established_resets=1,
                current_established=10,
                segments_sent=10000,
                segments_received=9500,
                segments_retransmitted=100,
                source="psutil_fallback",
            )

            collector = TcpStatsCollector(repository=tcp_repo)
            collector.config.tcp_stats_interval = 0.05

            await collector.start()
            await asyncio.sleep(0.1)

            await collector.stop()
            assert collector._running is False

    def test_get_status(self, tcp_repo: TcpStatsRepository):
        collector = TcpStatsCollector(repository=tcp_repo)
        status = collector.get_status()
        assert status["name"] == "tcp_stats"
        assert status["running"] is False
        assert "interval_sec" in status


class TestTcpStatsCollectorWindowsAPI:
    def test_get_windows_tcp_stats_structure(self, tcp_repo: TcpStatsRepository):
        collector = TcpStatsCollector(repository=tcp_repo)
        # Just verify the structure is correct; actual Windows API call is mocked
        stats = collector._get_windows_tcp_stats()
        # On non-Windows or without IPHLPAPI, this returns None
        # The test is mainly for structure validation
        if stats is not None:
            assert isinstance(stats.active_opens, int)
            assert isinstance(stats.passive_opens, int)
            assert isinstance(stats.failed_attempts, int)
            assert isinstance(stats.established_resets, int)
            assert isinstance(stats.current_established, int)
            assert isinstance(stats.segments_sent, int)
            assert isinstance(stats.segments_received, int)
            assert isinstance(stats.segments_retransmitted, int)
            assert stats.source == "GetTcpStatisticsEx"

    def test_get_psutil_tcp_stats_structure(self, tcp_repo: TcpStatsRepository):
        collector = TcpStatsCollector(repository=tcp_repo)
        with patch("psutil.net_io_counters") as mock_io, \
             patch("psutil.net_connections") as mock_conns:
            mock_io.return_value = MagicMock(packets_sent=10000, packets_recv=9500)
            mock_conns.return_value = [MagicMock(status="ESTABLISHED") for _ in range(10)]

            stats = collector._get_psutil_tcp_stats()
            assert stats.source == "psutil_fallback"
            assert stats.current_established == 10
            assert stats.segments_sent == 10000
            assert stats.segments_received == 9500


class TestTcpStatsRepository:
    def test_insert_and_get_latest(self, tcp_repo: TcpStatsRepository):
        sample = TcpStatsSample(
            ts=time.time(),
            active_opens=1250,
            passive_opens=890,
            failed_attempts=12,
            established_resets=5,
            current_established=42,
            segments_sent=1500000,
            segments_received=1450000,
            segments_retransmitted=3400,
            source="GetTcpStatisticsEx",
        )
        tcp_repo.insert(sample)
        latest = tcp_repo.get_latest()
        assert latest is not None
        assert latest.source == "GetTcpStatisticsEx"
        assert latest.current_established == 42
        assert latest.segments_retransmitted == 3400

    def test_query_range(self, tcp_repo: TcpStatsRepository):
        import time
        now = time.time()
        samples = [
            TcpStatsSample(
                ts=now - 100 + i * 10,
                active_opens=100 + i,
                passive_opens=50 + i,
                failed_attempts=i,
                established_resets=0,
                current_established=10 + i,
                segments_sent=1000 + i * 100,
                segments_received=950 + i * 100,
                segments_retransmitted=5 + i,
                source="psutil_fallback",
            )
            for i in range(5)
        ]
        for s in samples:
            tcp_repo.insert(s)

        results = tcp_repo.query_range(now - 200, now, limit=10)
        assert len(results) == 5

    def test_prune(self, tcp_repo: TcpStatsRepository):
        import time
        now = time.time()
        samples = [
            TcpStatsSample(
                ts=now - 86400 * 20,
                active_opens=100,
                passive_opens=50,
                failed_attempts=0,
                established_resets=0,
                current_established=10,
                segments_sent=1000,
                segments_received=950,
                segments_retransmitted=5,
                source="psutil_fallback",
            ),
            TcpStatsSample(
                ts=now - 86400 * 5,
                active_opens=100,
                passive_opens=50,
                failed_attempts=0,
                established_resets=0,
                current_established=10,
                segments_sent=1000,
                segments_received=950,
                segments_retransmitted=5,
                source="psutil_fallback",
            ),
        ]
        for s in samples:
            tcp_repo.insert(s)

        cutoff = now - 86400 * 14
        deleted = tcp_repo.prune(cutoff)
        assert deleted == 1

        remaining = tcp_repo.query_range(0, now, limit=10)
        assert len(remaining) == 1
        assert remaining[0].ts > cutoff
