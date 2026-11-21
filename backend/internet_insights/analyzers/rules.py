"""Deterministic incident rules for Internet Insights Intelligence Engine.

Rules are pure functions over repository-backed windows: no LLM, no randomness.
Each rule declares its full RuleDefinition (spec §15.2) and evaluates
(training window baseline vs detection window) per target.
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

from ..storage.repositories import (
    DnsProbeRepository,
    QualitySampleRepository,
    TcpStatsRepository,
)

logger = logging.getLogger("dashboard.internet_insights.analyzers.rules")

ANALYZER_VERSION = "1.0.0"


@dataclass
class RuleDefinition:
    """Full declaration of a deterministic rule (spec §15.2 — all 8 fields required)."""

    rule_id: str
    input_metrics: list[str]
    min_sample_count: int
    threshold: float
    duration_sec: float
    cooldown_sec: float
    recovery_condition: str
    confidence: float
    analyzer_version: str = ANALYZER_VERSION


@dataclass
class RuleEvaluation:
    """Result of evaluating one rule against current windows."""

    rule_id: str
    triggered: bool
    skipped_reason: str | None = None
    confidence: float = 0.0
    observations: dict[str, Any] = field(default_factory=dict)
    baseline: dict[str, Any] = field(default_factory=dict)
    detection_window: tuple[float, float] = (0.0, 0.0)
    baseline_window: tuple[float, float] = (0.0, 0.0)
    affected_target: str = ""
    interface_id: str | None = None
    title: str = ""
    category: str = ""
    severity: str = "warning"
    summary: str = ""
    uncertainty: str = ""


def _robust_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"median_ms": None, "p95_ms": None, "count": 0}
    ordered = sorted(values)
    n = len(ordered)
    return {
        "median_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(ordered[int(n * 0.95)] if n > 1 else ordered[0], 1),
        "count": n,
    }


def _success_rtts(samples: list) -> list[float]:
    return [s.rtt_ms for s in samples if s.status == "success" and s.rtt_ms is not None]


class IncidentAnalyzer:
    """Evaluates deterministic rules over repository-backed windows."""

    def __init__(
        self,
        quality_repo: QualitySampleRepository | None = None,
        dns_repo: DnsProbeRepository | None = None,
        tcp_repo: TcpStatsRepository | None = None,
        config=None,
    ):
        if config is None:
            from ..config import get_config

            config = get_config()
        self.config = config
        self.quality_repo = quality_repo or QualitySampleRepository()
        self.dns_repo = dns_repo or DnsProbeRepository()
        self.tcp_repo = tcp_repo or TcpStatsRepository()

    # ---- windows (spec §15.1: training vs detection separate, min-sample gate) ----

    def _windows(self, now: float) -> tuple[tuple[float, float], tuple[float, float]]:
        detection = (now - self.config.detection_window_hours * 3600, now)
        training = (now - (self.config.detection_window_hours + self.config.baseline_window_hours) * 3600,
                    now - self.config.detection_window_hours * 1.5 * 3600)
        # Keep training strictly before detection to avoid overlap that would dilute the baseline.
        if training[1] >= detection[0]:
            training = (detection[0] - self.config.baseline_window_hours * 3600, detection[0])
        return detection, training

    def _rule_def(self, rule_id: str, **overrides: Any) -> RuleDefinition:
        cfg = self.config
        base: dict[str, RuleDefinition] = {
            "sustained_latency_increase": RuleDefinition(
                rule_id="sustained_latency_increase",
                input_metrics=["rtt_ms"],
                min_sample_count=cfg.min_detection_samples,
                threshold=cfg.latency_increase_threshold_pct,
                duration_sec=300.0,
                cooldown_sec=900.0,
                recovery_condition="detection median within +50% of baseline median",
                confidence=0.75,
            ),
            "sustained_packet_loss": RuleDefinition(
                rule_id="sustained_packet_loss",
                input_metrics=["status", "error_code"],
                min_sample_count=cfg.min_detection_samples,
                threshold=cfg.loss_sustained_threshold_pct,
                duration_sec=300.0,
                cooldown_sec=900.0,
                recovery_condition="detection loss_pct <= threshold",
                confidence=0.8,
            ),
            "dns_resolution_degradation": RuleDefinition(
                rule_id="dns_resolution_degradation",
                input_metrics=["duration_ms", "status"],
                min_sample_count=10,
                threshold=cfg.dns_degradation_threshold_ms,
                duration_sec=300.0,
                cooldown_sec=1800.0,
                recovery_condition="detection median duration <= threshold",
                confidence=0.7,
            ),
            "gateway_reachability_loss": RuleDefinition(
                rule_id="gateway_reachability_loss",
                input_metrics=["status"],
                min_sample_count=10,
                threshold=cfg.gateway_loss_threshold_pct,
                duration_sec=60.0,
                cooldown_sec=600.0,
                recovery_condition="latest gateway probe succeeds",
                confidence=0.85,
            ),
            "tcp_retransmission_increase": RuleDefinition(
                rule_id="tcp_retransmission_increase",
                input_metrics=["segments_retransmitted", "segments_sent", "failed_attempts"],
                min_sample_count=6,
                threshold=cfg.tcp_retransmit_rate_threshold_pct,
                duration_sec=300.0,
                cooldown_sec=1800.0,
                recovery_condition="detection retransmit rate <= threshold",
                confidence=0.6,
            ),
        }
        definition = base[rule_id]
        return definition

    # ---- individual rules ----

    def _rule_latency(self, target_id: str, now: float) -> RuleEvaluation:
        rule = self._rule_def("sustained_latency_increase")
        detection, training = self._windows(now)
        det_samples = self.quality_repo.query_range(target_id, detection[0], detection[1], limit=10000)
        rtts = _success_rtts(det_samples)
        if len(rtts) < rule.min_sample_count:
            return RuleEvaluation(rule_id=rule.rule_id, triggered=False,
                                  skipped_reason=f"min_sample_count ({len(rtts)} < {rule.min_sample_count})",
                                  detection_window=detection, baseline_window=training,
                                  affected_target=target_id)
        train_samples = self.quality_repo.query_range(target_id, training[0], training[1], limit=10000)
        train_rtts = _success_rtts(train_samples)
        if len(train_rtts) < self.config.min_baseline_samples:
            return RuleEvaluation(rule_id=rule.rule_id, triggered=False,
                                  skipped_reason=f"insufficient baseline ({len(train_rtts)} < {self.config.min_baseline_samples})",
                                  detection_window=detection, baseline_window=training,
                                  affected_target=target_id)
        det_stats = _robust_stats(rtts)
        train_stats = _robust_stats(train_rtts)
        base_median = train_stats["median_ms"] or 0.0
        det_median = det_stats["median_ms"] or 0.0
        increase_pct = ((det_median - base_median) / base_median * 100) if base_median > 0 else 0.0
        triggered = increase_pct >= rule.threshold
        return RuleEvaluation(
            rule_id=rule.rule_id,
            triggered=triggered,
            confidence=rule.confidence if triggered else 0.0,
            observations={
                "triggering_observations": [
                    {"ts": s.ts, "rtt_ms": s.rtt_ms, "status": s.status, "interface_id": s.interface_id}
                    for s in det_samples[-20:]
                ],
                "timestamp_range": {"start": det_samples[-1].ts if det_samples else detection[0], "end": detection[1]},
            },
            baseline={
                "baseline_median_ms": train_stats["median_ms"],
                "baseline_p95_ms": train_stats["p95_ms"],
                "baseline_samples": train_stats["count"],
                "detection_median_ms": det_stats["median_ms"],
                "detection_p95_ms": det_stats["p95_ms"],
                "detection_samples": det_stats["count"],
                "latency_increase_pct": round(increase_pct, 1),
                "threshold_pct": rule.threshold,
            },
            detection_window=detection,
            baseline_window=training,
            affected_target=target_id,
            interface_id=det_samples[-1].interface_id if det_samples else None,
            title=f"Sustained latency increase on {target_id}",
            category="latency",
            severity="warning" if increase_pct < rule.threshold * 2 else "critical",
            summary=(
                f"Median latency on {target_id} is {det_median:.1f} ms vs baseline {base_median:.1f} ms "
                f"(+{increase_pct:.0f}%, threshold {rule.threshold:.0f}%) sustained over the detection window."
            ),
            uncertainty=(
                "Latency increase is measured against this host's own historical baseline; "
                "it may reflect local load, target-side slowness, or network path changes. "
                "Confidence is limited by sample size and window length."
            ),
        )

    def _rule_loss(self, target_id: str, now: float) -> RuleEvaluation:
        rule = self._rule_def("sustained_packet_loss")
        detection, training = self._windows(now)
        det_samples = self.quality_repo.query_range(target_id, detection[0], detection[1], limit=10000)
        if len(det_samples) < rule.min_sample_count:
            return RuleEvaluation(rule_id=rule.rule_id, triggered=False,
                                  skipped_reason=f"min_sample_count ({len(det_samples)} < {rule.min_sample_count})",
                                  detection_window=detection, baseline_window=training,
                                  affected_target=target_id)
        det_failed = [s for s in det_samples if s.status != "success"]
        det_loss_pct = len(det_failed) / len(det_samples) * 100
        train_samples = self.quality_repo.query_range(target_id, training[0], training[1], limit=10000)
        train_failed = len([s for s in train_samples if s.status != "success"])
        train_loss_pct = (train_failed / len(train_samples) * 100) if train_samples else 0.0
        triggered = det_loss_pct >= rule.threshold
        by_error: dict[str, int] = {}
        for s in det_failed:
            code = s.error_code or s.status
            by_error[code] = by_error.get(code, 0) + 1
        return RuleEvaluation(
            rule_id=rule.rule_id,
            triggered=triggered,
            confidence=rule.confidence if triggered else 0.0,
            observations={
                "triggering_observations": [
                    {"ts": s.ts, "status": s.status, "error_code": s.error_code, "interface_id": s.interface_id}
                    for s in det_failed[-20:]
                ],
                "timestamp_range": {"start": det_samples[-1].ts if det_samples else detection[0], "end": detection[1]},
            },
            baseline={
                "baseline_loss_pct": round(train_loss_pct, 1),
                "baseline_samples": len(train_samples),
                "detection_loss_pct": round(det_loss_pct, 1),
                "detection_samples": len(det_samples),
                "by_error_code": by_error,
                "threshold_pct": rule.threshold,
            },
            detection_window=detection,
            baseline_window=training,
            affected_target=target_id,
            interface_id=det_failed[-1].interface_id if det_failed else None,
            title=f"Sustained packet loss on {target_id}",
            category="loss",
            severity="critical" if det_loss_pct >= rule.threshold * 3 else "warning",
            summary=(
                f"Packet loss on {target_id} is {det_loss_pct:.1f}% in the detection window "
                f"(baseline {train_loss_pct:.1f}%, threshold {rule.threshold:.0f}%)."
            ),
            uncertainty=(
                "Loss is computed from probe outcomes which are also affected by target-side rate limiting; "
                "small windows may over- or under-estimate real path loss."
            ),
        )

    def _rule_dns(self, now: float) -> RuleEvaluation:
        rule = self._rule_def("dns_resolution_degradation")
        detection, training = self._windows(now)
        det_samples = self.dns_repo.query_range("", detection[0], detection[1], limit=10000)
        det_samples = [s for s in det_samples if s.status in ("success", "timeout", "error")]
        if len(det_samples) < rule.min_sample_count:
            return RuleEvaluation(rule_id=rule.rule_id, triggered=False,
                                  skipped_reason=f"min_sample_count ({len(det_samples)} < {rule.min_sample_count})",
                                  detection_window=detection, baseline_window=training,
                                  affected_target="dns")
        train_samples = self.dns_repo.query_range("", training[0], training[1], limit=10000)
        train_samples = [s for s in train_samples if s.status in ("success", "timeout", "error")]
        det_success = [s for s in det_samples if s.status == "success" and s.duration_ms is not None]
        det_median = statistics.median([s.duration_ms for s in det_success]) if det_success else None
        train_success = [s for s in train_samples if s.status == "success" and s.duration_ms is not None]
        train_median = statistics.median([s.duration_ms for s in train_success]) if train_success else None
        det_failure_pct = (len(det_samples) - len(det_success)) / len(det_samples) * 100
        train_failure_pct = ((len(train_samples) - len(train_success)) / len(train_samples) * 100) if train_samples else 0.0
        triggered = (
            det_median is not None and det_median >= rule.threshold
        ) or det_failure_pct >= 20.0
        return RuleEvaluation(
            rule_id=rule.rule_id,
            triggered=triggered,
            confidence=rule.confidence if triggered else 0.0,
            observations={
                "triggering_observations": [
                    {"ts": s.ts, "resolver": s.resolver, "hostname": s.hostname,
                     "duration_ms": s.duration_ms, "status": s.status}
                    for s in det_samples[-20:]
                ],
                "timestamp_range": {"start": det_samples[-1].ts if det_samples else detection[0], "end": detection[1]},
            },
            baseline={
                "baseline_median_ms": round(train_median, 1) if train_median is not None else None,
                "baseline_failure_pct": round(train_failure_pct, 1),
                "baseline_samples": len(train_samples),
                "detection_median_ms": round(det_median, 1) if det_median is not None else None,
                "detection_failure_pct": round(det_failure_pct, 1),
                "detection_samples": len(det_samples),
                "threshold_ms": rule.threshold,
            },
            detection_window=detection,
            baseline_window=training,
            affected_target="dns",
            title="DNS resolution degradation",
            category="dns",
            severity="warning",
            summary=(
                f"DNS resolution median {det_median:.1f} ms (threshold {rule.threshold:.0f} ms) "
                f"and failure rate {det_failure_pct:.1f}% in the detection window."
            ) if det_median is not None else f"DNS failure rate {det_failure_pct:.1f}% in the detection window.",
            uncertainty=(
                "Resolver latency may reflect upstream resolver choice or captive-network DNS interception; "
                "this does not identify the responsible party."
            ),
        )

    def _rule_gateway(self, now: float) -> RuleEvaluation:
        rule = self._rule_def("gateway_reachability_loss")
        detection, training = self._windows(now)
        det_samples = self.quality_repo.query_range("gateway", detection[0], detection[1], limit=10000)
        if len(det_samples) < rule.min_sample_count:
            return RuleEvaluation(rule_id=rule.rule_id, triggered=False,
                                  skipped_reason=f"min_sample_count ({len(det_samples)} < {rule.min_sample_count})",
                                  detection_window=detection, baseline_window=training,
                                  affected_target="gateway")
        failed = [s for s in det_samples if s.status != "success"]
        loss_pct = len(failed) / len(det_samples) * 100
        # query_range returns newest-first (ORDER BY ts DESC), so index 0 is the latest probe.
        latest = det_samples[0]
        triggered = loss_pct >= rule.threshold and latest.status != "success"
        return RuleEvaluation(
            rule_id=rule.rule_id,
            triggered=triggered,
            confidence=rule.confidence if triggered else 0.0,
            observations={
                "triggering_observations": [
                    {"ts": s.ts, "status": s.status, "error_code": s.error_code, "interface_id": s.interface_id}
                    for s in failed[-20:]
                ],
                "timestamp_range": {"start": det_samples[-1].ts, "end": detection[1]},
            },
            baseline={
                "baseline_samples": len(self.quality_repo.query_range("gateway", training[0], training[1], limit=100)),
                "detection_loss_pct": round(loss_pct, 1),
                "detection_samples": len(det_samples),
                "latest_status": latest.status,
                "threshold_pct": rule.threshold,
            },
            detection_window=detection,
            baseline_window=training,
            affected_target="gateway",
            interface_id=latest.interface_id,
            title="Gateway reachability loss",
            category="gateway",
            severity="critical",
            summary=(
                f"Gateway probes fail at {loss_pct:.1f}% in the detection window "
                f"(threshold {rule.threshold:.0f}%) and the latest probe failed."
            ),
            uncertainty=(
                "Gateway loss usually indicates local LAN/Wi-Fi/router trouble rather than an upstream fault; "
                "correlate with interface counters before drawing conclusions."
            ),
        )

    def _rule_tcp(self, now: float) -> RuleEvaluation:
        rule = self._rule_def("tcp_retransmission_increase")
        detection, training = self._windows(now)
        det_samples = self.tcp_repo.query_range(detection[0], detection[1], limit=10000)
        if len(det_samples) < rule.min_sample_count:
            return RuleEvaluation(rule_id=rule.rule_id, triggered=False,
                                  skipped_reason=f"min_sample_count ({len(det_samples)} < {rule.min_sample_count})",
                                  detection_window=detection, baseline_window=training,
                                  affected_target="tcp")
        det_retrans = sum(s.segments_retransmitted for s in det_samples)
        det_sent = sum(s.segments_sent for s in det_samples)
        det_failed = sum(s.failed_attempts for s in det_samples)
        det_rate = (det_retrans / det_sent * 100) if det_sent > 0 else 0.0
        train_samples = self.tcp_repo.query_range(training[0], training[1], limit=10000)
        train_retrans = sum(s.segments_retransmitted for s in train_samples)
        train_sent = sum(s.segments_sent for s in train_samples)
        train_rate = (train_retrans / train_sent * 100) if train_sent > 0 else 0.0
        triggered = det_rate >= rule.threshold and det_rate > train_rate * 1.5
        return RuleEvaluation(
            rule_id=rule.rule_id,
            triggered=triggered,
            confidence=rule.confidence if triggered else 0.0,
            observations={
                "triggering_observations": [
                    {"ts": s.ts, "retransmit_rate_pct": (
                        (s.segments_retransmitted / s.segments_sent * 100) if s.segments_sent > 0 else 0.0
                    ), "failed_attempts": s.failed_attempts}
                    for s in det_samples[-20:]
                ],
                "timestamp_range": {"start": det_samples[-1].ts, "end": detection[1]},
            },
            baseline={
                "baseline_rate_pct": round(train_rate, 2),
                "baseline_samples": len(train_samples),
                "detection_rate_pct": round(det_rate, 2),
                "detection_samples": len(det_samples),
                "detection_failed_attempts": det_failed,
                "threshold_pct": rule.threshold,
            },
            detection_window=detection,
            baseline_window=training,
            affected_target="tcp",
            title="TCP retransmission increase",
            category="tcp",
            severity="warning",
            summary=(
                f"TCP retransmission rate is {det_rate:.2f}% vs baseline {train_rate:.2f}% "
                f"(threshold {rule.threshold:.0f}%)."
            ),
            uncertainty=(
                "Retransmissions can stem from either end of a connection or middleboxes; "
                "OS-level counters cannot attribute cause."
            ),
        )

    # ---- public API ----

    def evaluate_all(self, now: float | None = None) -> list[RuleEvaluation]:
        """Evaluate every rule for every applicable target."""
        if now is None:
            now = time.time()
        evaluations: list[RuleEvaluation] = []
        for target_id in ("gateway", "primary", "secondary"):
            evaluations.append(self._rule_latency(target_id, now))
            evaluations.append(self._rule_loss(target_id, now))
        evaluations.append(self._rule_dns(now))
        evaluations.append(self._rule_gateway(now))
        evaluations.append(self._rule_tcp(now))
        return evaluations

    def evaluate_rule(self, rule_id: str, target_id: str | None = None, now: float | None = None) -> RuleEvaluation:
        """Evaluate a single rule (used by tests and manual runs)."""
        if now is None:
            now = time.time()
        if rule_id == "sustained_latency_increase":
            return self._rule_latency(target_id or "primary", now)
        if rule_id == "sustained_packet_loss":
            return self._rule_loss(target_id or "primary", now)
        if rule_id == "dns_resolution_degradation":
            return self._rule_dns(now)
        if rule_id == "gateway_reachability_loss":
            return self._rule_gateway(now)
        if rule_id == "tcp_retransmission_increase":
            return self._rule_tcp(now)
        raise ValueError(f"Unknown rule_id: {rule_id}")

    # ---- correlation (spec §15.3) ----

    def correlate(self, evaluations: list[RuleEvaluation], now: float | None = None) -> RuleEvaluation | None:
        """Correlate rule outputs into an upstream-degradation incident.

        Conditions (spec §15.3):
        1. Gateway remains reachable.
        2. At least 2 internet targets show increased latency.
        3. DNS remains normal.
        4. TCP retransmission indicators rise.
        """
        if now is None:
            now = time.time()
        by_rule: dict[str, list[RuleEvaluation]] = {}
        for ev in evaluations:
            by_rule.setdefault(ev.rule_id, []).append(ev)

        latency_by_target = {ev.affected_target: ev for ev in by_rule.get("sustained_latency_increase", [])}
        internet_targets = ["primary", "secondary"]
        degraded = [t for t in internet_targets
                    if latency_by_target.get(t) is not None and latency_by_target[t].triggered]

        gateway_ok = True
        for ev in by_rule.get("gateway_reachability_loss", []):
            if ev.triggered:
                gateway_ok = False

        dns_ok = True
        for ev in by_rule.get("dns_resolution_degradation", []):
            if ev.triggered:
                dns_ok = False

        tcp_rising = any(ev.triggered for ev in by_rule.get("tcp_retransmission_increase", []))

        if not (gateway_ok and len(degraded) >= 2 and dns_ok and tcp_rising):
            return None

        detection, training = self._windows(now)
        return RuleEvaluation(
            rule_id="upstream_network_degradation_correlation",
            triggered=True,
            confidence=0.65,
            observations={
                "triggering_observations": [
                    {"rule_id": ev.rule_id, "target": ev.affected_target, "summary": ev.summary}
                    for ev in evaluations if ev.triggered
                ],
                "timestamp_range": {"start": detection[0], "end": detection[1]},
            },
            baseline={
                "gateway_reachable": gateway_ok,
                "degraded_internet_targets": degraded,
                "dns_normal": dns_ok,
                "tcp_retransmission_rising": tcp_rising,
                "conditions_required": ["gateway reachable", ">=2 internet targets latency increased",
                                         "dns normal", "tcp retransmission rising"],
            },
            detection_window=detection,
            baseline_window=training,
            affected_target="upstream",
            title="Possible upstream network degradation",
            category="route",
            severity="warning",
            summary=(
                "Gateway reachable, DNS normal, but >=2 internet targets show sustained latency increase "
                "together with rising TCP retransmissions. This pattern suggests possible upstream network "
                "degradation; the responsible party cannot be confirmed from this host."
            ),
            uncertainty=(
                "Correlation is heuristic: it cannot attribute responsibility (no ISP fault is implied or "
                "confirmed) and may reflect coincident target-side slowness."
            ),
        )


# Kept for the RuleDefinition contract check in tests: every rule must declare all 8 fields.
def all_rule_definitions() -> dict[str, RuleDefinition]:
    analyzer = IncidentAnalyzer.__new__(IncidentAnalyzer)
    analyzer.config = _ConfigShim()
    return {
        rule_id: analyzer._rule_def(rule_id)
        for rule_id in (
            "sustained_latency_increase",
            "sustained_packet_loss",
            "dns_resolution_degradation",
            "gateway_reachability_loss",
            "tcp_retransmission_increase",
        )
    }


class _ConfigShim:
    """Standalone defaults for RuleDefinition extraction without touching global config."""

    min_detection_samples = 20
    min_baseline_samples = 100
    latency_increase_threshold_pct = 200.0
    loss_sustained_threshold_pct = 5.0
    dns_degradation_threshold_ms = 500.0
    gateway_loss_threshold_pct = 10.0
    tcp_retransmit_rate_threshold_pct = 1.0
