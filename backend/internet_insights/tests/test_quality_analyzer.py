"""Tests for Quality Analyzer."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from internet_insights.storage.database import InternetInsightsDB
from internet_insights.storage.migrations import apply_migrations
from internet_insights.storage.repositories import QualitySample, QualitySampleRepository
from internet_insights.analyzers.quality import QualityAnalyzer, LatencyStats, JitterStats, LossBreakdown


@pytest.fixture
def temp_db(tmp_path: Path) -> InternetInsightsDB:
    db_path = tmp_path / "test_analyzer.db"
    db = InternetInsightsDB(db_path)
    conn = db._get_conn()
    apply_migrations(conn)
    yield db
    db.close()


@pytest.fixture
def quality_repo(temp_db: InternetInsightsDB) -> QualitySampleRepository:
    return QualitySampleRepository(temp_db)


@pytest.fixture
def analyzer(quality_repo: QualitySampleRepository) -> QualityAnalyzer:
    return QualityAnalyzer(quality_repo)


class TestQualityAnalyzerLatency:
    def test_compute_latency_stats_empty(self, analyzer: QualityAnalyzer):
        stats = analyzer._compute_latency_stats([], 0)
        assert stats.min_ms is None
        assert stats.median_ms is None
        assert stats.p95_ms is None
        assert stats.max_ms is None
        assert stats.count == 0
        assert stats.timeouts == 0

    def test_compute_latency_stats_single(self, analyzer: QualityAnalyzer):
        stats = analyzer._compute_latency_stats([18.4], 0)
        assert stats.min_ms == 18.4
        assert stats.median_ms == 18.4
        assert stats.p95_ms == 18.4
        assert stats.max_ms == 18.4
        assert stats.count == 1
        assert stats.timeouts == 0

    def test_compute_latency_stats_multiple(self, analyzer: QualityAnalyzer):
        rtts = [10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0]
        stats = analyzer._compute_latency_stats(rtts, 2)
        assert stats.min_ms == 10.0
        assert stats.median_ms == 18.0  # 4th element (0-indexed: 3)
        assert stats.p95_ms == 30.0  # int(7 * 0.95) = 6
        assert stats.max_ms == 30.0
        assert stats.count == 7
        assert stats.timeouts == 2

    def test_compute_latency_stats_with_timeouts(self, analyzer: QualityAnalyzer):
        stats = analyzer._compute_latency_stats([15.0, 20.0], 3)
        assert stats.timeouts == 3
        assert stats.count == 2


class TestQualityAnalyzerJitter:
    def test_compute_jitter_empty(self, analyzer: QualityAnalyzer):
        jitter = analyzer._compute_jitter([])
        assert jitter.mean_abs_diff_ms is None
        assert jitter.samples_used == 0

    def test_compute_jitter_single(self, analyzer: QualityAnalyzer):
        jitter = analyzer._compute_jitter([18.4])
        assert jitter.mean_abs_diff_ms is None
        assert jitter.samples_used == 1

    def test_compute_jitter_multiple(self, analyzer: QualityAnalyzer):
        # RTTs: 10, 12, 15, 18 -> diffs: 2, 3, 3 -> mean = 2.67
        rtts = [10.0, 12.0, 15.0, 18.0]
        jitter = analyzer._compute_jitter(rtts)
        assert jitter.mean_abs_diff_ms == 2.7  # (2+3+3)/3 = 2.666... rounded to 1 decimal
        assert jitter.samples_used == 3


class TestQualityAnalyzerLoss:
    def test_compute_loss_breakdown_empty(self, analyzer: QualityAnalyzer):
        loss = analyzer._compute_loss_breakdown([])
        assert loss.total_samples == 0
        assert loss.loss_pct == 0.0
        assert loss.by_error_code == {}

    def test_compute_loss_breakdown_all_success(self, analyzer: QualityAnalyzer):
        samples = [
            QualitySample(ts=time.time(), target_id="primary", probe_type="tcp", rtt_ms=10.0, status="success", error_code=None, timeout_ms=2000, interface_id=None),
            QualitySample(ts=time.time(), target_id="primary", probe_type="tcp", rtt_ms=12.0, status="success", error_code=None, timeout_ms=2000, interface_id=None),
        ]
        loss = analyzer._compute_loss_breakdown(samples)
        assert loss.total_samples == 2
        assert loss.loss_pct == 0.0
        assert loss.by_error_code == {}

    def test_compute_loss_breakdown_with_failures(self, analyzer: QualityAnalyzer):
        samples = [
            QualitySample(ts=time.time(), target_id="primary", probe_type="tcp", rtt_ms=10.0, status="success", error_code=None, timeout_ms=2000, interface_id=None),
            QualitySample(ts=time.time(), target_id="primary", probe_type="tcp", rtt_ms=None, status="timeout", error_code="TIMEOUT", timeout_ms=2000, interface_id=None),
            QualitySample(ts=time.time(), target_id="primary", probe_type="tcp", rtt_ms=None, status="timeout", error_code="TIMEOUT", timeout_ms=2000, interface_id=None),
            QualitySample(ts=time.time(), target_id="primary", probe_type="tcp", rtt_ms=None, status="unreachable", error_code="CONNECTION_REFUSED", timeout_ms=2000, interface_id=None),
        ]
        loss = analyzer._compute_loss_breakdown(samples)
        assert loss.total_samples == 4
        assert loss.loss_pct == 75.0
        assert loss.by_error_code["TIMEOUT"] == 2
        assert loss.by_error_code["CONNECTION_REFUSED"] == 1


class TestQualityAnalyzerDegradation:
    def test_detect_degradation_no_current_samples(self, analyzer: QualityAnalyzer, quality_repo: QualitySampleRepository):
        result = analyzer._detect_degradation("primary", [], 0.0, time.time() - 86400, time.time())
        assert result.degraded is False
        assert result.reason == "No current samples"
        assert result.confidence == 0.0

    def test_detect_degradation_insufficient_baseline(self, analyzer: QualityAnalyzer, quality_repo: QualitySampleRepository):
        # Insert only a few baseline samples
        now = time.time()
        baseline_samples = [
            QualitySample(ts=now - 86400 + i * 3600, target_id="primary", probe_type="tcp", rtt_ms=10.0 + i, status="success", error_code=None, timeout_ms=2000, interface_id=None)
            for i in range(5)  # Less than min_baseline_samples (100)
        ]
        quality_repo.insert_batch(baseline_samples)

        current_rtts = [50.0, 55.0, 60.0]  # High latency
        result = analyzer._detect_degradation("primary", current_rtts, 0.0, now - 86400, now - 3600)
        assert result.degraded is False
        assert "Insufficient baseline samples" in (result.reason or "")

    def test_detect_degradation_latency_increase(self, analyzer: QualityAnalyzer, quality_repo: QualitySampleRepository):
        now = time.time()
        # Baseline: median ~10ms
        baseline_samples = [
            QualitySample(ts=now - 86400 + i * 600, target_id="primary", probe_type="tcp", rtt_ms=10.0, status="success", error_code=None, timeout_ms=2000, interface_id=None)
            for i in range(150)  # More than min_baseline_samples
        ]
        quality_repo.insert_batch(baseline_samples)

        current_rtts = [35.0, 40.0, 38.0]  # ~3.5x baseline (250% increase)
        result = analyzer._detect_degradation("primary", current_rtts, 0.0, now - 86400, now - 3600)
        assert result.degraded is True
        assert result.confidence > 0.5
        assert "Latency increased" in (result.reason or "")

    def test_detect_degradation_high_loss(self, analyzer: QualityAnalyzer, quality_repo: QualitySampleRepository):
        now = time.time()
        baseline_samples = [
            QualitySample(ts=now - 86400 + i * 600, target_id="primary", probe_type="tcp", rtt_ms=10.0, status="success", error_code=None, timeout_ms=2000, interface_id=None)
            for i in range(150)
        ]
        quality_repo.insert_batch(baseline_samples)

        current_rtts = [12.0, 11.0]  # Normal latency
        result = analyzer._detect_degradation("primary", current_rtts, 10.0, now - 86400, now - 3600)  # 10% loss
        assert result.degraded is True
        assert "packet loss" in (result.reason or "").lower()


class TestQualityAnalyzerFullAnalysis:
    def test_analyze_empty_window(self, analyzer: QualityAnalyzer):
        since = time.time() - 3600
        until = time.time()
        result = analyzer.analyze("primary", since, until)
        assert result.target_id == "primary"
        assert result.sample_count == 0
        assert result.latency.count == 0

    def test_analyze_with_samples(self, analyzer: QualityAnalyzer, quality_repo: QualitySampleRepository):
        now = time.time()
        samples = [
            QualitySample(ts=now - 300 + i * 10, target_id="primary", probe_type="tcp", rtt_ms=10.0 + i * 0.5, status="success", error_code=None, timeout_ms=2000, interface_id=None)
            for i in range(20)
        ]
        # Add some failures
        samples.extend([
            QualitySample(ts=now - 100, target_id="primary", probe_type="tcp", rtt_ms=None, status="timeout", error_code="TIMEOUT", timeout_ms=2000, interface_id=None),
            QualitySample(ts=now - 50, target_id="primary", probe_type="tcp", rtt_ms=None, status="timeout", error_code="TIMEOUT", timeout_ms=2000, interface_id=None),
        ])
        quality_repo.insert_batch(samples)

        result = analyzer.analyze("primary", now - 3600, now)
        assert result.target_id == "primary"
        assert result.sample_count == 22
        assert result.latency.count == 20
        assert result.latency.timeouts == 2
        assert result.loss.total_samples == 22
        assert result.loss.loss_pct == pytest.approx(9.1, rel=0.1)  # 2/22
        assert result.jitter.mean_abs_diff_ms is not None
        assert result.last_probe_at is not None

    def test_analyze_all_targets(self, analyzer: QualityAnalyzer, quality_repo: QualitySampleRepository):
        now = time.time()
        for target_id in ["gateway", "primary", "secondary"]:
            # Insert samples well within the 5m window (now - 250 to now - 100)
            samples = [
                QualitySample(ts=now - 250 + i * 10, target_id=target_id, probe_type="tcp", rtt_ms=10.0 + i * 0.5, status="success", error_code=None, timeout_ms=2000, interface_id=None)
                for i in range(10)
            ]
            quality_repo.insert_batch(samples)

        results = analyzer.analyze_all_targets(["gateway", "primary", "secondary"], "5m")
        assert len(results) == 3
        for target_id in ["gateway", "primary", "secondary"]:
            assert target_id in results
            assert results[target_id].sample_count == 10

    def test_get_overall_status_good(self, analyzer: QualityAnalyzer):
        from internet_insights.analyzers.quality import QualityAnalysis, LatencyStats, JitterStats, LossBreakdown, DegradationEvidence
        analyses = {
            "primary": QualityAnalysis(
                target_id="primary",
                latency=LatencyStats(10.0, 10.0, 12.0, 15.0, 10, 0),
                jitter=JitterStats(1.5, 9),
                loss=LossBreakdown(10, 0.0, {}),
                degradation=DegradationEvidence(False, None, 0.0, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
            "secondary": QualityAnalysis(
                target_id="secondary",
                latency=LatencyStats(12.0, 12.0, 14.0, 18.0, 10, 0),
                jitter=JitterStats(2.0, 9),
                loss=LossBreakdown(10, 0.0, {}),
                degradation=DegradationEvidence(False, None, 0.0, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
            "gateway": QualityAnalysis(
                target_id="gateway",
                latency=LatencyStats(2.0, 2.0, 3.0, 5.0, 10, 0),
                jitter=JitterStats(0.5, 9),
                loss=LossBreakdown(10, 0.0, {}),
                degradation=DegradationEvidence(False, None, 0.0, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
        }
        status = analyzer.get_overall_status(analyses)
        assert status["status"] == "good"
        assert status["badge"] == "Good"
        assert len(status["evidence"]) == 3
        assert status["degraded_targets"] == []

    def test_get_overall_status_degraded(self, analyzer: QualityAnalyzer):
        from internet_insights.analyzers.quality import QualityAnalysis, LatencyStats, JitterStats, LossBreakdown, DegradationEvidence
        analyses = {
            "primary": QualityAnalysis(
                target_id="primary",
                latency=LatencyStats(50.0, 50.0, 60.0, 80.0, 10, 0),
                jitter=JitterStats(10.0, 9),
                loss=LossBreakdown(10, 5.0, {"TIMEOUT": 1}),
                degradation=DegradationEvidence(True, "Latency increased", 0.8, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
            "secondary": QualityAnalysis(
                target_id="secondary",
                latency=LatencyStats(12.0, 12.0, 14.0, 18.0, 10, 0),
                jitter=JitterStats(2.0, 9),
                loss=LossBreakdown(10, 0.0, {}),
                degradation=DegradationEvidence(False, None, 0.0, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
            "gateway": QualityAnalysis(
                target_id="gateway",
                latency=LatencyStats(2.0, 2.0, 3.0, 5.0, 10, 0),
                jitter=JitterStats(0.5, 9),
                loss=LossBreakdown(10, 0.0, {}),
                degradation=DegradationEvidence(False, None, 0.0, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
        }
        status = analyzer.get_overall_status(analyses)
        assert status["status"] == "degraded"
        assert status["badge"] == "Degraded"
        assert "primary" in status["degraded_targets"]

    def test_get_overall_status_poor(self, analyzer: QualityAnalyzer):
        from internet_insights.analyzers.quality import QualityAnalysis, LatencyStats, JitterStats, LossBreakdown, DegradationEvidence
        analyses = {
            "primary": QualityAnalysis(
                target_id="primary",
                latency=LatencyStats(50.0, 50.0, 60.0, 80.0, 10, 0),
                jitter=JitterStats(10.0, 9),
                loss=LossBreakdown(10, 5.0, {"TIMEOUT": 1}),
                degradation=DegradationEvidence(True, "Latency increased", 0.8, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
            "secondary": QualityAnalysis(
                target_id="secondary",
                latency=LatencyStats(60.0, 60.0, 70.0, 90.0, 10, 0),
                jitter=JitterStats(15.0, 9),
                loss=LossBreakdown(10, 10.0, {"TIMEOUT": 2}),
                degradation=DegradationEvidence(True, "High latency", 0.9, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
            "gateway": QualityAnalysis(
                target_id="gateway",
                latency=LatencyStats(30.0, 30.0, 40.0, 50.0, 10, 0),
                jitter=JitterStats(5.0, 9),
                loss=LossBreakdown(10, 8.0, {"TIMEOUT": 1}),
                degradation=DegradationEvidence(True, "Gateway issues", 0.7, {}),
                last_probe_at=time.time(),
                sample_count=10,
                window_start=time.time() - 3600,
                window_end=time.time(),
            ),
        }
        status = analyzer.get_overall_status(analyses)
        assert status["status"] == "poor"
        assert status["badge"] == "Poor"
        assert len(status["degraded_targets"]) == 3