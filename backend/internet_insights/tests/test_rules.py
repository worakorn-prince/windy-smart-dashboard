"""Tests for Internet Insights deterministic rules (INET-M5).

Seeds synthetic samples into a temp DB and verifies trigger/skip conditions
of all five rules, correlation, and the RuleDefinition contract (spec §15).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from internet_insights.analyzers.rules import (
    ANALYZER_VERSION,
    IncidentAnalyzer,
    RuleDefinition,
    RuleEvaluation,
    all_rule_definitions,
)
from internet_insights.storage.database import InternetInsightsDB
from internet_insights.storage.repositories import (
    DnsProbeRepository,
    DnsProbeSample,
    QualitySample,
    QualitySampleRepository,
    TcpStatsRepository,
    TcpStatsSample,
)

NOW = 1_800_000_000.0

DETECTION = (NOW - 3600, NOW)
TRAINING = (NOW - 25 * 3600, NOW - 5400)


def _quality(
    ts: float,
    target_id: str,
    rtt_ms: float | None,
    status: str = "success",
) -> QualitySample:
    return QualitySample(
        ts=ts,
        target_id=target_id,
        probe_type="icmp",
        rtt_ms=rtt_ms,
        status=status,
        error_code=None if status == "success" else "timeout",
        timeout_ms=1000,
        interface_id=None,
    )


def _dns(ts: float, duration_ms: float | None, status: str = "success") -> DnsProbeSample:
    return DnsProbeSample(
        ts=ts,
        resolver="",
        hostname="example.com",
        record_type="A",
        duration_ms=duration_ms,
        status=status,
        answer_count=1 if status == "success" else 0,
        error_code=None if status == "success" else "timeout",
        probe_method="direct_udp",
    )


def _tcp(ts: float, sent: int, retrans: int, failed: int = 0) -> TcpStatsSample:
    return TcpStatsSample(
        ts=ts,
        active_opens=10,
        passive_opens=5,
        failed_attempts=failed,
        established_resets=0,
        current_established=1,
        segments_sent=sent,
        segments_received=sent * 2,
        segments_retransmitted=retrans,
        source="psutil_fallback",
    )


def _seed_tcp(analyzer: IncidentAnalyzer, samples: list[TcpStatsSample]) -> None:
    for sample in samples:
        analyzer.tcp_repo.insert(sample)


@pytest.fixture
def analyzer(tmp_path: Path) -> IncidentAnalyzer:
    db = InternetInsightsDB(tmp_path / "test_rules.db")
    yield IncidentAnalyzer(
        quality_repo=QualitySampleRepository(db),
        dns_repo=DnsProbeRepository(db),
        tcp_repo=TcpStatsRepository(db),
    )
    db.close()


def _seed_latency(
    analyzer: IncidentAnalyzer,
    target_id: str,
    det_rtt: float = 50.0,
    train_rtt: float = 10.0,
    det_count: int = 24,
    train_count: int = 120,
) -> None:
    det, train = DETECTION, TRAINING
    analyzer.quality_repo.insert_batch(
        [_quality(det[0] + i * 10.0, target_id, det_rtt) for i in range(det_count)]
    )
    analyzer.quality_repo.insert_batch(
        [_quality(train[0] + i * 60.0, target_id, train_rtt) for i in range(train_count)]
    )


class TestLatencyRule:
    def test_triggers_on_sustained_increase(self, analyzer):
        _seed_latency(analyzer, "primary")
        ev = analyzer.evaluate_rule("sustained_latency_increase", target_id="primary", now=NOW)
        assert ev.rule_id == "sustained_latency_increase"
        assert ev.triggered is True
        assert ev.skipped_reason is None
        assert ev.category == "latency"
        assert ev.affected_target == "primary"
        assert ev.baseline["latency_increase_pct"] >= 200.0
        assert ev.baseline["threshold_pct"] == 200.0

    def test_critical_when_increase_doubles_threshold(self, analyzer):
        _seed_latency(analyzer, "primary", det_rtt=50.0, train_rtt=10.0)
        ev = analyzer.evaluate_rule("sustained_latency_increase", target_id="primary", now=NOW)
        assert ev.triggered is True
        assert ev.severity == "critical"

    def test_warning_when_below_double_threshold(self, analyzer):
        _seed_latency(analyzer, "primary", det_rtt=35.0, train_rtt=10.0)
        ev = analyzer.evaluate_rule("sustained_latency_increase", target_id="primary", now=NOW)
        assert ev.triggered is True
        assert ev.severity == "warning"

    def test_skips_when_below_min_detection_samples(self, analyzer):
        det, train = DETECTION, TRAINING
        analyzer.quality_repo.insert_batch(
            [_quality(det[0] + i * 10.0, "primary", 50.0) for i in range(19)]
        )
        analyzer.quality_repo.insert_batch(
            [_quality(train[0] + i * 60.0, "primary", 10.0) for i in range(120)]
        )
        ev = analyzer.evaluate_rule("sustained_latency_increase", target_id="primary", now=NOW)
        assert ev.triggered is False
        assert "min_sample_count" in ev.skipped_reason
        assert "19 < 20" in ev.skipped_reason

    def test_skips_when_insufficient_baseline(self, analyzer):
        _seed_latency(analyzer, "primary", det_count=24, train_count=99)
        ev = analyzer.evaluate_rule("sustained_latency_increase", target_id="primary", now=NOW)
        assert ev.triggered is False
        assert "insufficient baseline" in ev.skipped_reason
        assert "99 < 100" in ev.skipped_reason

    def test_not_triggered_when_below_threshold(self, analyzer):
        _seed_latency(analyzer, "primary", det_rtt=12.0, train_rtt=10.0)
        ev = analyzer.evaluate_rule("sustained_latency_increase", target_id="primary", now=NOW)
        assert ev.triggered is False
        assert ev.skipped_reason is None
        assert ev.confidence == 0.0
        assert ev.severity == "warning"

    def test_windows_do_not_overlap(self, analyzer):
        det, train = analyzer._windows(NOW)
        assert train[1] < det[0]
        assert det == (NOW - 3600, NOW)
        assert train == (NOW - 25 * 3600, NOW - 5400)


class TestLossRule:
    def test_triggers_at_5pct_loss(self, analyzer):
        det, train = DETECTION, TRAINING
        det_samples = [_quality(det[0] + i * 10.0, "primary", 20.0) for i in range(24)]
        det_samples[0] = _quality(det[0], "primary", None, status="timeout")
        det_samples[1] = _quality(det[0] + 10.0, "primary", None, status="timeout")
        analyzer.quality_repo.insert_batch(det_samples)
        analyzer.quality_repo.insert_batch(
            [_quality(train[0] + i * 60.0, "primary", 20.0) for i in range(24)]
        )
        ev = analyzer.evaluate_rule("sustained_packet_loss", target_id="primary", now=NOW)
        assert ev.triggered is True
        assert ev.category == "loss"
        assert ev.severity == "warning"
        assert ev.baseline["detection_loss_pct"] == 8.3
        assert ev.baseline["by_error_code"] == {"timeout": 2}
        assert ev.baseline["threshold_pct"] == 5.0

    def test_critical_at_triple_threshold(self, analyzer):
        det, train = DETECTION, TRAINING
        det_samples = [_quality(det[0] + i * 10.0, "primary", 20.0) for i in range(24)]
        for i in range(5):
            det_samples[i] = _quality(det[0] + i * 10.0, "primary", None, status="timeout")
        analyzer.quality_repo.insert_batch(det_samples)
        analyzer.quality_repo.insert_batch(
            [_quality(train[0] + i * 60.0, "primary", 20.0) for i in range(24)]
        )
        ev = analyzer.evaluate_rule("sustained_packet_loss", target_id="primary", now=NOW)
        assert ev.triggered is True
        assert ev.severity == "critical"

    def test_skips_when_below_min_detection_samples(self, analyzer):
        det = DETECTION
        analyzer.quality_repo.insert_batch(
            [_quality(det[0] + i * 10.0, "primary", 20.0) for i in range(19)]
        )
        ev = analyzer.evaluate_rule("sustained_packet_loss", target_id="primary", now=NOW)
        assert ev.triggered is False
        assert "min_sample_count" in ev.skipped_reason
        assert "19 < 20" in ev.skipped_reason

    def test_not_triggered_when_below_threshold(self, analyzer):
        det, train = DETECTION, TRAINING
        det_samples = [_quality(det[0] + i * 10.0, "primary", 20.0) for i in range(24)]
        det_samples[0] = _quality(det[0], "primary", None, status="timeout")
        analyzer.quality_repo.insert_batch(det_samples)
        analyzer.quality_repo.insert_batch(
            [_quality(train[0] + i * 60.0, "primary", 20.0) for i in range(24)]
        )
        ev = analyzer.evaluate_rule("sustained_packet_loss", target_id="primary", now=NOW)
        assert ev.triggered is False
        assert ev.skipped_reason is None
        assert ev.baseline["detection_loss_pct"] == 4.2

    def test_error_code_fallback_to_status(self, analyzer):
        det, train = DETECTION, TRAINING
        det_samples = [_quality(det[0] + i * 10.0, "primary", 20.0) for i in range(24)]
        det_samples[0] = _quality(det[0], "primary", None, status="timeout")
        det_samples[1] = _quality(det[0] + 10.0, "primary", None, status="timeout")
        analyzer.quality_repo.insert_batch(det_samples)
        analyzer.quality_repo.insert_batch(
            [_quality(train[0] + i * 60.0, "primary", 20.0) for i in range(24)]
        )
        ev = analyzer.evaluate_rule("sustained_packet_loss", target_id="primary", now=NOW)
        assert ev.baseline["by_error_code"] == {"timeout": 2}


class TestDnsRule:
    def test_triggers_on_high_median_duration(self, analyzer):
        det, train = DETECTION, TRAINING
        analyzer.dns_repo.insert_batch([_dns(det[0] + i * 30.0, 800.0) for i in range(12)])
        analyzer.dns_repo.insert_batch([_dns(train[0] + i * 60.0, 20.0) for i in range(12)])
        ev = analyzer.evaluate_rule("dns_resolution_degradation", now=NOW)
        assert ev.triggered is True
        assert ev.category == "dns"
        assert ev.affected_target == "dns"
        assert ev.baseline["detection_median_ms"] == 800.0
        assert ev.severity == "warning"

    def test_triggers_on_failure_rate(self, analyzer):
        det = DETECTION
        samples = [_dns(det[0] + i * 30.0, 20.0) for i in range(10)]
        samples[0] = _dns(det[0], None, status="timeout")
        samples[1] = _dns(det[0] + 30.0, None, status="timeout")
        samples[2] = _dns(det[0] + 60.0, None, status="timeout")
        samples[3] = _dns(det[0] + 90.0, None, status="timeout")
        analyzer.dns_repo.insert_batch(samples)
        ev = analyzer.evaluate_rule("dns_resolution_degradation", now=NOW)
        assert ev.triggered is True
        assert ev.baseline["detection_failure_pct"] == 40.0

    def test_skips_when_below_min_sample_count(self, analyzer):
        det = DETECTION
        analyzer.dns_repo.insert_batch([_dns(det[0] + i * 30.0, 20.0) for i in range(9)])
        ev = analyzer.evaluate_rule("dns_resolution_degradation", now=NOW)
        assert ev.triggered is False
        assert "min_sample_count" in ev.skipped_reason
        assert "9 < 10" in ev.skipped_reason

    def test_ignores_non_matching_resolvers(self, analyzer):
        det = DETECTION
        other = DnsProbeSample(
            ts=det[0], resolver="1.1.1.1", hostname="example.com", record_type="A",
            duration_ms=2000.0, status="success", answer_count=1, error_code=None,
            probe_method="direct_udp",
        )
        analyzer.dns_repo.insert_batch([other] * 12)
        ev = analyzer.evaluate_rule("dns_resolution_degradation", now=NOW)
        assert ev.triggered is False
        assert "min_sample_count" in ev.skipped_reason

    def test_success_path_not_triggered(self, analyzer):
        det, train = DETECTION, TRAINING
        analyzer.dns_repo.insert_batch([_dns(det[0] + i * 30.0, 30.0) for i in range(12)])
        analyzer.dns_repo.insert_batch([_dns(train[0] + i * 60.0, 30.0) for i in range(12)])
        ev = analyzer.evaluate_rule("dns_resolution_degradation", now=NOW)
        assert ev.triggered is False
        assert ev.skipped_reason is None
        assert ev.baseline["detection_median_ms"] == 30.0


class TestGatewayRule:
    def test_triggers_when_all_probes_fail(self, analyzer):
        det, train = DETECTION, TRAINING
        analyzer.quality_repo.insert_batch(
            [_quality(det[0] + i * 10.0, "gateway", None, status="timeout") for i in range(12)]
        )
        analyzer.quality_repo.insert_batch(
            [_quality(train[0] + i * 60.0, "gateway", 5.0) for i in range(12)]
        )
        ev = analyzer.evaluate_rule("gateway_reachability_loss", now=NOW)
        assert ev.triggered is True
        assert ev.category == "gateway"
        assert ev.severity == "critical"
        assert ev.baseline["latest_status"] == "timeout"
        assert ev.baseline["detection_loss_pct"] == 100.0

    def test_not_triggered_when_latest_success(self, analyzer):
        det = DETECTION
        det_samples = [_quality(det[0] + i * 10.0, "gateway", None, status="timeout") for i in range(12)]
        # Newest sample (det[0] + 11*10) succeeds -> rule must not trigger (recovery_condition).
        det_samples[-1] = _quality(det[0] + 11 * 10.0, "gateway", 5.0)
        analyzer.quality_repo.insert_batch(det_samples)
        ev = analyzer.evaluate_rule("gateway_reachability_loss", now=NOW)
        assert ev.triggered is False
        assert ev.baseline["latest_status"] == "success"

    def test_skips_when_below_min_sample_count(self, analyzer):
        det = DETECTION
        analyzer.quality_repo.insert_batch(
            [_quality(det[0] + i * 30.0, "gateway", None, status="timeout") for i in range(9)]
        )
        ev = analyzer.evaluate_rule("gateway_reachability_loss", now=NOW)
        assert ev.triggered is False
        assert "min_sample_count" in ev.skipped_reason
        assert "9 < 10" in ev.skipped_reason


class TestTcpRule:
    def test_triggers_on_retransmission_spike(self, analyzer):
        det, train = DETECTION, TRAINING
        _seed_tcp(analyzer, [_tcp(det[0] + i * 60.0, sent=500, retrans=10) for i in range(6)])
        _seed_tcp(analyzer, [_tcp(train[0] + i * 60.0, sent=500, retrans=0) for i in range(6)])
        ev = analyzer.evaluate_rule("tcp_retransmission_increase", now=NOW)
        assert ev.triggered is True
        assert ev.category == "tcp"
        assert ev.baseline["detection_rate_pct"] == 2.0
        assert ev.baseline["baseline_rate_pct"] == 0.0
        assert ev.baseline["detection_failed_attempts"] == 0
        assert ev.severity == "warning"

    def test_not_triggered_when_rate_below_threshold(self, analyzer):
        det = DETECTION
        _seed_tcp(analyzer, [_tcp(det[0] + i * 60.0, sent=500, retrans=4) for i in range(6)])
        ev = analyzer.evaluate_rule("tcp_retransmission_increase", now=NOW)
        assert ev.triggered is False
        assert ev.baseline["detection_rate_pct"] == 0.8

    def test_not_triggered_when_not_150pct_of_baseline(self, analyzer):
        det, train = DETECTION, TRAINING
        _seed_tcp(analyzer, [_tcp(det[0] + i * 60.0, sent=500, retrans=6) for i in range(6)])
        _seed_tcp(analyzer, [_tcp(train[0] + i * 60.0, sent=500, retrans=5) for i in range(6)])
        ev = analyzer.evaluate_rule("tcp_retransmission_increase", now=NOW)
        assert ev.baseline["detection_rate_pct"] == 1.2
        assert ev.baseline["baseline_rate_pct"] == 1.0
        assert ev.triggered is False

    def test_skips_when_below_min_sample_count(self, analyzer):
        det = DETECTION
        _seed_tcp(analyzer, [_tcp(det[0] + i * 60.0, sent=500, retrans=10) for i in range(5)])
        ev = analyzer.evaluate_rule("tcp_retransmission_increase", now=NOW)
        assert ev.triggered is False
        assert "min_sample_count" in ev.skipped_reason
        assert "5 < 6" in ev.skipped_reason


class TestCorrelation:
    def _seed_all_rules(self, analyzer: IncidentAnalyzer, secondary_det_rtt: float = 50.0) -> None:
        for target, det_rtt in (("primary", 50.0), ("secondary", secondary_det_rtt)):
            _seed_latency(analyzer, target, det_rtt=det_rtt)
        det, train = DETECTION, TRAINING
        analyzer.dns_repo.insert_batch([_dns(det[0] + i * 30.0, 30.0) for i in range(12)])
        analyzer.dns_repo.insert_batch([_dns(train[0] + i * 60.0, 30.0) for i in range(12)])
        analyzer.quality_repo.insert_batch(
            [_quality(det[0] + i * 10.0, "gateway", 2.0) for i in range(12)]
        )
        analyzer.quality_repo.insert_batch(
            [_quality(train[0] + i * 60.0, "gateway", 2.0) for i in range(12)]
        )
        _seed_tcp(analyzer, [_tcp(det[0] + i * 60.0, sent=500, retrans=10) for i in range(6)])
        _seed_tcp(analyzer, [_tcp(train[0] + i * 60.0, sent=500, retrans=0) for i in range(6)])

    def test_correlation_fires_when_all_conditions_met(self, analyzer):
        self._seed_all_rules(analyzer)
        evals = analyzer.evaluate_all(now=NOW)
        corr = analyzer.correlate(evals, now=NOW)
        assert corr is not None
        assert corr.rule_id == "upstream_network_degradation_correlation"
        assert corr.triggered is True
        assert corr.category == "route"
        assert corr.affected_target == "upstream"
        assert corr.confidence == 0.65
        assert corr.title == "Possible upstream network degradation"
        assert corr.baseline["degraded_internet_targets"] == ["primary", "secondary"]
        assert corr.baseline["gateway_reachable"] is True
        assert corr.baseline["dns_normal"] is True
        assert corr.baseline["tcp_retransmission_rising"] is True

    def test_correlation_none_when_gateway_down(self, analyzer):
        self._seed_all_rules(analyzer)
        det = DETECTION
        analyzer.quality_repo.insert_batch(
            [_quality(det[0] + i * 10.0, "gateway", None, status="timeout") for i in range(12)]
        )
        evals = analyzer.evaluate_all(now=NOW)
        corr = analyzer.correlate(evals, now=NOW)
        assert corr is None

    def test_correlation_none_when_only_one_target_degraded(self, analyzer):
        self._seed_all_rules(analyzer, secondary_det_rtt=12.0)
        evals = analyzer.evaluate_all(now=NOW)
        corr = analyzer.correlate(evals, now=NOW)
        assert corr is None

    def test_correlation_none_when_dns_degraded(self, analyzer):
        self._seed_all_rules(analyzer)
        det = DETECTION
        analyzer.dns_repo.insert_batch([_dns(det[0] + 400.0 + i * 30.0, 900.0) for i in range(24)])
        evals = analyzer.evaluate_all(now=NOW)
        corr = analyzer.correlate(evals, now=NOW)
        assert corr is None

    def test_correlation_none_when_tcp_not_rising(self, analyzer):
        self._seed_all_rules(analyzer)
        det = DETECTION
        _seed_tcp(
            analyzer, [_tcp(det[0] + 400.0 + i * 60.0, sent=950, retrans=0) for i in range(6)]
        )
        evals = analyzer.evaluate_all(now=NOW)
        corr = analyzer.correlate(evals, now=NOW)
        assert corr is None

    def test_correlation_none_on_empty_evaluations(self, analyzer):
        corr = analyzer.correlate([], now=NOW)
        assert corr is None


class TestRuleDefinitionContract:
    def test_all_rule_definitions_returns_5_rules_with_full_fields(self):
        defs = all_rule_definitions()
        assert set(defs) == {
            "sustained_latency_increase",
            "sustained_packet_loss",
            "dns_resolution_degradation",
            "gateway_reachability_loss",
            "tcp_retransmission_increase",
        }
        for rule_id, defn in defs.items():
            assert isinstance(defn, RuleDefinition)
            assert defn.rule_id == rule_id
            assert isinstance(defn.input_metrics, list) and defn.input_metrics
            assert defn.min_sample_count > 0
            assert defn.threshold > 0
            assert defn.duration_sec > 0
            assert defn.cooldown_sec > 0
            assert defn.recovery_condition
            assert 0 < defn.confidence <= 1.0
            assert defn.analyzer_version == ANALYZER_VERSION == "1.0.0"

    def test_evaluate_all_returns_9_evaluations(self, analyzer):
        evals = analyzer.evaluate_all(now=NOW)
        assert len(evals) == 9
        assert all(isinstance(e, RuleEvaluation) for e in evals)

    def test_evaluate_rule_unknown_id_raises(self, analyzer):
        with pytest.raises(ValueError, match="Unknown rule_id"):
            analyzer.evaluate_rule("not_a_rule", now=NOW)



