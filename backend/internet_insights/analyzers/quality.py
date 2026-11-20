"""Quality analyzer for latency, jitter, packet loss statistics and degradation detection."""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass
from typing import Any

from ..config import get_config
from ..storage.repositories import QualitySampleRepository, QualitySample

logger = logging.getLogger("dashboard.internet_insights.analyzers.quality")


@dataclass
class LatencyStats:
    min_ms: float | None
    median_ms: float | None
    p95_ms: float | None
    max_ms: float | None
    count: int
    timeouts: int


@dataclass
class JitterStats:
    mean_abs_diff_ms: float | None
    samples_used: int


@dataclass
class LossBreakdown:
    total_samples: int
    loss_pct: float
    by_error_code: dict[str, int]


@dataclass
class DegradationEvidence:
    degraded: bool
    reason: str | None
    confidence: float
    details: dict[str, Any]


@dataclass
class QualityAnalysis:
    target_id: str
    latency: LatencyStats
    jitter: JitterStats
    loss: LossBreakdown
    degradation: DegradationEvidence
    last_probe_at: float | None
    sample_count: int
    window_start: float
    window_end: float


class QualityAnalyzer:
    """Analyze quality samples for latency, jitter, loss, and degradation."""

    def __init__(self, repository: QualitySampleRepository | None = None):
        self.config = get_config()
        self.repository = repository or QualitySampleRepository()

    def analyze(
        self,
        target_id: str,
        since: float,
        until: float | None = None,
        baseline_since: float | None = None,
    ) -> QualityAnalysis:
        """Analyze quality for a target within time window."""
        if until is None:
            until = time.time()

        samples = self.repository.query_range(target_id, since, until, limit=10000)

        if not samples:
            return self._empty_analysis(target_id, since, until)

        # Separate successful and failed samples
        successful = [s for s in samples if s.rtt_ms is not None and s.status == "success"]
        failed = [s for s in samples if s.rtt_ms is None or s.status != "success"]

        rtts = [s.rtt_ms for s in successful] if successful else []

        # Latency stats
        latency = self._compute_latency_stats(rtts, len(failed))

        # Jitter stats
        jitter = self._compute_jitter(rtts)

        # Loss breakdown
        loss = self._compute_loss_breakdown(samples)

        # Degradation detection
        degradation = self._detect_degradation(
            target_id,
            rtts,
            loss.loss_pct,
            baseline_since or (since - self.config.baseline_window_hours * 3600),
            since,
        )

        last_probe = max((s.ts for s in samples), default=None)

        return QualityAnalysis(
            target_id=target_id,
            latency=latency,
            jitter=jitter,
            loss=loss,
            degradation=degradation,
            last_probe_at=last_probe,
            sample_count=len(samples),
            window_start=since,
            window_end=until,
        )

    def _compute_latency_stats(self, rtts: list[float], timeouts: int) -> LatencyStats:
        if not rtts:
            return LatencyStats(None, None, None, None, 0, timeouts)

        sorted_rtts = sorted(rtts)
        n = len(sorted_rtts)

        return LatencyStats(
            min_ms=sorted_rtts[0],
            median_ms=sorted_rtts[n // 2],
            p95_ms=sorted_rtts[int(n * 0.95)] if n > 1 else sorted_rtts[0],
            max_ms=sorted_rtts[-1],
            count=n,
            timeouts=timeouts,
        )

    def _compute_jitter(self, rtts: list[float]) -> JitterStats:
        """Compute jitter as mean absolute difference between consecutive successful samples."""
        if len(rtts) < 2:
            return JitterStats(None, len(rtts))

        diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))]
        return JitterStats(
            mean_abs_diff_ms=round(statistics.mean(diffs), 1),
            samples_used=len(diffs),
        )

    def _compute_loss_breakdown(self, samples: list[QualitySample]) -> LossBreakdown:
        if not samples:
            return LossBreakdown(0, 0.0, {})

        total = len(samples)
        failed = [s for s in samples if s.status != "success"]
        loss_count = len(failed)

        by_error_code: dict[str, int] = {}
        for s in failed:
            code = s.error_code or s.status
            by_error_code[code] = by_error_code.get(code, 0) + 1

        return LossBreakdown(
            total_samples=total,
            loss_pct=round((loss_count / total) * 100, 1) if total > 0 else 0.0,
            by_error_code=by_error_code,
        )

    def _detect_degradation(
        self,
        target_id: str,
        current_rtts: list[float],
        current_loss_pct: float,
        baseline_since: float,
        detection_since: float,
    ) -> DegradationEvidence:
        """Detect quality degradation compared to baseline window."""
        if not current_rtts:
            return DegradationEvidence(
                degraded=False,
                reason="No current samples",
                confidence=0.0,
                details={},
            )

        # Get baseline samples
        baseline_samples = self.repository.query_range(target_id, baseline_since, detection_since, limit=10000)
        baseline_rtts = [s.rtt_ms for s in baseline_samples if s.rtt_ms is not None and s.status == "success"]

        if len(baseline_rtts) < self.config.min_baseline_samples:
            return DegradationEvidence(
                degraded=False,
                reason=f"Insufficient baseline samples ({len(baseline_rtts)} < {self.config.min_baseline_samples})",
                confidence=0.0,
                details={"baseline_samples": len(baseline_rtts), "current_samples": len(current_rtts)},
            )

        baseline_median = statistics.median(baseline_rtts)
        current_median = statistics.median(current_rtts)

        latency_increase_pct = ((current_median - baseline_median) / baseline_median * 100) if baseline_median > 0 else 0

        reasons = []
        confidence_factors = []

        # Check latency increase
        if latency_increase_pct > self.config.latency_increase_threshold_pct:
            reasons.append(f"Latency increased {latency_increase_pct:.0f}% (baseline: {baseline_median:.1f}ms, current: {current_median:.1f}ms)")
            confidence_factors.append(min(latency_increase_pct / 300.0, 1.0))

        # Check sustained loss
        if current_loss_pct > self.config.loss_sustained_threshold_pct:
            reasons.append(f"Sustained packet loss {current_loss_pct:.1f}% (threshold: {self.config.loss_sustained_threshold_pct}%)")
            confidence_factors.append(min(current_loss_pct / 10.0, 1.0))

        degraded = len(reasons) > 0
        confidence = max(confidence_factors) if confidence_factors else 0.0

        return DegradationEvidence(
            degraded=degraded,
            reason="; ".join(reasons) if reasons else None,
            confidence=round(confidence, 2),
            details={
                "baseline_median_ms": round(baseline_median, 1),
                "current_median_ms": round(current_median, 1),
                "latency_increase_pct": round(latency_increase_pct, 1),
                "current_loss_pct": current_loss_pct,
                "baseline_samples": len(baseline_rtts),
                "detection_samples": len(current_rtts),
            },
        )

    def _empty_analysis(self, target_id: str, since: float, until: float) -> QualityAnalysis:
        return QualityAnalysis(
            target_id=target_id,
            latency=LatencyStats(None, None, None, None, 0, 0),
            jitter=JitterStats(None, 0),
            loss=LossBreakdown(0, 0.0, {}),
            degradation=DegradationEvidence(False, "No samples in window", 0.0, {}),
            last_probe_at=None,
            sample_count=0,
            window_start=since,
            window_end=until,
        )

    def analyze_all_targets(
        self,
        targets: list[str] | None = None,
        range_key: str = "1h",
    ) -> dict[str, QualityAnalysis]:
        """Analyze all specified targets."""
        if targets is None:
            targets = ["gateway", "primary", "secondary"]

        range_seconds = {"5m": 300, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}
        since = time.time() - range_seconds.get(range_key, 3600)
        until = time.time()

        results = {}
        for target_id in targets:
            results[target_id] = self.analyze(target_id, since, until)

        return results

    def get_overall_status(self, analyses: dict[str, QualityAnalysis]) -> dict[str, Any]:
        """Compute overall quality status from per-target analyses."""
        if not analyses:
            return {
                "status": "unknown",
                "badge": "unknown",
                "confidence": 0.0,
                "evidence": [],
            }

        degraded_targets = [t for t, a in analyses.items() if a.degradation.degraded]
        total_targets = len(analyses)

        # Determine overall status
        if not degraded_targets:
            status = "good"
            badge = "Good"
        elif len(degraded_targets) == total_targets:
            status = "poor"
            badge = "Poor"
        else:
            status = "degraded"
            badge = "Degraded"

        # Overall confidence (average of degradation confidences)
        confidences = [a.degradation.confidence for a in analyses.values() if a.degradation.confidence > 0]
        overall_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

        # Build evidence list
        evidence = []
        for target_id, analysis in analyses.items():
            evidence.append({
                "target_id": target_id,
                "latency_median_ms": analysis.latency.median_ms,
                "jitter_ms": analysis.jitter.mean_abs_diff_ms,
                "loss_pct": analysis.loss.loss_pct,
                "last_probe_at": analysis.last_probe_at,
                "sample_count": analysis.sample_count,
                "degraded": analysis.degradation.degraded,
                "degradation_reason": analysis.degradation.reason,
                "degradation_confidence": analysis.degradation.confidence,
            })

        return {
            "status": status,
            "badge": badge,
            "confidence": overall_confidence,
            "evidence": evidence,
            "degraded_targets": degraded_targets,
            "analyzed_at": time.time(),
        }