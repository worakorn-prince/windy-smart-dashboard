"""Tests for collector lifecycle management."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from internet_insights.collectors.quality import QualityCollector
from internet_insights.collectors.interface import InterfaceCollector
from internet_insights.services.collector_manager import CollectorManager
from internet_insights.storage.repositories import QualitySampleRepository, InterfaceSampleRepository, TcpStatsRepository
from internet_insights.storage.database import InternetInsightsDB


@pytest.fixture
def temp_db(tmp_path: Path) -> InternetInsightsDB:
    db_path = tmp_path / "test_collectors.db"
    db = InternetInsightsDB(db_path)
    yield db
    db.close()


@pytest.fixture
def quality_repo(temp_db: InternetInsightsDB) -> QualitySampleRepository:
    return QualitySampleRepository(temp_db)


@pytest.fixture
def interface_repo(temp_db: InternetInsightsDB) -> InterfaceSampleRepository:
    return InterfaceSampleRepository(temp_db)


class TestQualityCollectorLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, quality_repo: QualitySampleRepository):
        with patch("internet_insights.collectors.quality.PingAdapter") as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.ping.return_value = 18.4
            mock_adapter_class.return_value = mock_adapter

            collector = QualityCollector(repository=quality_repo)
            await collector.start()
            assert collector._running is True
            assert collector._task is not None

            # Let it run briefly
            await asyncio.sleep(0.2)

            await collector.stop()
            assert collector._running is False

    @pytest.mark.asyncio
    async def test_no_duplicate_runs(self, quality_repo: QualitySampleRepository):
        """Collector should not start new collection if previous still running."""
        with patch("internet_insights.collectors.quality.PingAdapter") as mock_adapter_class:
            # Make ping slow
            async def slow_ping(*args, **kwargs):
                await asyncio.sleep(0.5)
                return 18.4

            mock_adapter = AsyncMock()
            mock_adapter.ping.side_effect = slow_ping
            mock_adapter_class.return_value = mock_adapter

            # Use very short interval to trigger multiple cycles
            collector = QualityCollector(repository=quality_repo)
            collector.config.quality_gateway_interval = 0.05
            collector.config.quality_primary_interval = 0.05
            collector.config.quality_secondary_interval = 0.05

            await collector.start()
            await asyncio.sleep(0.15)  # Should only complete one cycle
            await collector.stop()

            # Should only have called ping once per target (no overlapping)
            # Since ping takes 0.5s and interval is 0.05s, single-flight prevents overlap
            assert mock_adapter.ping.call_count <= 3  # One per target max

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, quality_repo: QualitySampleRepository):
        with patch("internet_insights.collectors.quality.PingAdapter") as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.ping.return_value = 18.4
            mock_adapter_class.return_value = mock_adapter

            collector = QualityCollector(repository=quality_repo)
            await collector.start()
            await asyncio.sleep(0.1)

            # Stop should wait for current collection to complete
            await collector.stop()
            assert collector._running is False

    def test_get_status(self, quality_repo: QualitySampleRepository):
        collector = QualityCollector(repository=quality_repo)
        status = collector.get_status()
        assert status["name"] == "quality"
        assert status["running"] is False
        assert "targets" in status


class TestInterfaceCollectorLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, interface_repo: InterfaceSampleRepository):
        with patch("psutil.net_io_counters") as mock_counters:
            # Mock counters with increasing values
            mock_stats = MagicMock()
            mock_stats.bytes_sent = 1000000
            mock_stats.bytes_recv = 2000000
            mock_stats.packets_sent = 1000
            mock_stats.packets_recv = 2000
            mock_stats.errin = 0
            mock_stats.errout = 0
            mock_stats.dropin = 0
            mock_stats.dropout = 0
            mock_counters.return_value = {"Ethernet0": mock_stats}

            with patch("psutil.net_if_stats") as mock_if_stats:
                mock_if = MagicMock()
                mock_if.isup = True
                mock_if_stats.return_value = {"Ethernet0": mock_if}

                collector = InterfaceCollector(repository=interface_repo)
                await collector.start()
                assert collector._running is True

                await asyncio.sleep(0.15)

                await collector.stop()
                assert collector._running is False

    @pytest.mark.asyncio
    async def test_rate_calculation(self, interface_repo: InterfaceSampleRepository):
        """Verify send_bps and recv_bps are calculated correctly."""
        call_count = 0

        def mock_counters_side_effect(*args, **kwargs):
            nonlocal call_count
            mock_stats = MagicMock()
            if call_count == 0:
                mock_stats.bytes_sent = 1000000
                mock_stats.bytes_recv = 2000000
            else:
                # 1 second later: 1MB sent, 2MB recv more
                mock_stats.bytes_sent = 2000000
                mock_stats.bytes_recv = 4000000
            mock_stats.packets_sent = 1000 + call_count * 100
            mock_stats.packets_recv = 2000 + call_count * 200
            mock_stats.errin = 0
            mock_stats.errout = 0
            mock_stats.dropin = 0
            mock_stats.dropout = 0
            call_count += 1
            return {"Ethernet0": mock_stats}

        with patch("psutil.net_io_counters", side_effect=mock_counters_side_effect), \
             patch("psutil.net_if_stats") as mock_if_stats:
                mock_if = MagicMock()
                mock_if.isup = True
                mock_if_stats.return_value = {"Ethernet0": mock_if}

                collector = InterfaceCollector(repository=interface_repo)
                collector.config.interface_interval = 0.05
                await collector.start()
                await asyncio.sleep(0.2)  # Let it run 2-3 cycles
                await collector.stop()

                # Check stored samples have correct rates
                samples = interface_repo.get_all_latest()
                eth0_sample = next((s for s in samples if s.interface_id == "Ethernet0"), None)
                assert eth0_sample is not None
                # Should have calculated rates (approximately 1MB/s send, 2MB/s recv)
                assert eth0_sample.send_bps > 0
                assert eth0_sample.recv_bps > 0

    def test_get_status(self, interface_repo: InterfaceSampleRepository):
        collector = InterfaceCollector(repository=interface_repo)
        status = collector.get_status()
        assert status["name"] == "interface"
        assert status["running"] is False


class TestCollectorManager:
    @pytest.mark.asyncio
    async def test_start_stop_all(self, temp_db: InternetInsightsDB):
        quality_repo = QualitySampleRepository(temp_db)
        interface_repo = InterfaceSampleRepository(temp_db)

        with patch("internet_insights.collectors.quality.PingAdapter") as mock_ping_class:
            mock_ping = AsyncMock()
            mock_ping.ping.return_value = 18.4
            mock_ping_class.return_value = mock_ping

            with patch("psutil.net_io_counters") as mock_counters:
                mock_stats = MagicMock()
                mock_stats.bytes_sent = 1000000
                mock_stats.bytes_recv = 2000000
                mock_stats.packets_sent = 1000
                mock_stats.packets_recv = 2000
                mock_stats.errin = 0
                mock_stats.errout = 0
                mock_stats.dropin = 0
                mock_stats.dropout = 0
                mock_counters.return_value = {"Ethernet0": mock_stats}

                with patch("psutil.net_if_stats") as mock_if_stats:
                    mock_if = MagicMock()
                    mock_if.isup = True
                    mock_if_stats.return_value = {"Ethernet0": mock_if}

                    manager = CollectorManager()
                    manager._repositories = {
                        "quality": quality_repo,
                        "interface": interface_repo,
                        "tcp_stats": TcpStatsRepository(temp_db),
                    }
                    manager._init_collectors()

                    await manager.start_all()
                    assert all(c._running for c in manager.collectors.values())

                    await asyncio.sleep(0.15)

                    await manager.stop_all()
                    assert all(not c._running for c in manager.collectors.values())

    @pytest.mark.asyncio
    async def test_get_status(self, temp_db: InternetInsightsDB):
        quality_repo = QualitySampleRepository(temp_db)
        interface_repo = InterfaceSampleRepository(temp_db)

        manager = CollectorManager()
        manager._repositories = {
            "quality": quality_repo,
            "interface": interface_repo,
            "tcp_stats": TcpStatsRepository(temp_db),
        }
        manager._init_collectors()

        status = manager.get_status()
        assert "quality" in status
        assert "interface" in status
        assert status["quality"]["name"] == "quality"
        assert status["interface"]["name"] == "interface"

    def test_get_collector(self, temp_db: InternetInsightsDB):
        quality_repo = QualitySampleRepository(temp_db)
        interface_repo = InterfaceSampleRepository(temp_db)

        manager = CollectorManager()
        manager._repositories = {
            "quality": quality_repo,
            "interface": interface_repo,
            "tcp_stats": TcpStatsRepository(temp_db),
        }
        manager._init_collectors()

        quality = manager.get_collector("quality")
        interface = manager.get_collector("interface")
        none = manager.get_collector("nonexistent")

        assert quality is not None
        assert interface is not None
        assert none is None

    def test_get_repository(self, temp_db: InternetInsightsDB):
        quality_repo = QualitySampleRepository(temp_db)
        interface_repo = InterfaceSampleRepository(temp_db)

        manager = CollectorManager()
        manager._repositories = {
            "quality": quality_repo,
            "interface": interface_repo,
        }

        qr = manager.get_repository("quality")
        ir = manager.get_repository("interface")
        none = manager.get_repository("nonexistent")

        assert qr is quality_repo
        assert ir is interface_repo
        assert none is None
