"""DNS analyzer for resolver baseline, comparison, and degradation detection."""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass
from typing import Any

from ..config import get_config
from ..storage.repositories import DnsProbeRepository, DnsProbeSample

logger = logging.getLogger("dashboard.internet_insights.analyzers.dns")


@dataclass
class ResolverBaseline:
    resolver: str
    hostname: str
    record_type: str
    probe_method: str
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    latency_p99_ms: float | None
    success_rate: float
    total_probes: int
    timeout_count: int
    error_counts: dict[str, int]


@dataclass
class ResolverComparison:
    resolver: str
    probe_method: str
    current_latency_ms: float | None
    current_status: str
    baseline_latency_p50_ms: float | None
    baseline_success_rate: float
    degraded: bool
    degradation_reason: str | None


@dataclass
class DnsDegradationEvidence:
    degraded: bool
    reason: str | None
    confidence: float
    details: dict[str, Any]


class DnsAnalyzer:
    """Analyze DNS probe samples for baselines, comparison, and degradation."""

    def __init__(self, repository: DnsProbeRepository | None = None):
        self.config = get_config()
        self.repository = repository or DnsProbeRepository()

    def get_resolver_baseline(
        self,
        resolver: str,
        hostname: str | None = None,
        record_type: str | None = None,
        probe_method: str | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> ResolverBaseline | None:
        """Get baseline statistics for a resolver."""
        if until is None:
            until = time.time()
        if since is None:
            since = until - self.config.baseline_window_hours * 3600

        samples = self.repository.query_range(resolver, since, until, limit=10000)

        if hostname:
            samples = [s for s in samples if s.hostname == hostname]
        if record_type:
            samples = [s for s in samples if s.record_type == record_type]
        if probe_method:
            samples = [s for s in samples if s.probe_method == probe_method]

        if not samples:
            return None

        successful = [s for s in samples if s.status == "success" and s.duration_ms is not None]
        durations = [s.duration_ms for s in successful]
        timeouts = sum(1 for s in samples if s.status == "timeout")
        errors = [s for s in samples if s.status not in ("success", "timeout")]

        error_counts: dict[str, int] = {}
        for e in errors:
            code = e.error_code or e.status
            error_counts[code] = error_counts.get(code, 0) + 1

        total = len(samples)
        success_rate = (len(successful) / total * 100) if total > 0 else 0.0

        latency_p50 = None
        latency_p95 = None
        latency_p99 = None
        if durations:
            sorted_d = sorted(durations)
            n = len(sorted_d)
            latency_p50 = sorted_d[n // 2]
            latency_p95 = sorted_d[int(n * 0.95)] if n > 1 else sorted_d[0]
            latency_p99 = sorted_d[int(n * 0.99)] if n > 1 else sorted_d[0]

        return ResolverBaseline(
            resolver=resolver,
            hostname=hostname or "all",
            record_type=record_type or "all",
            probe_method=probe_method or "all",
            latency_p50_ms=latency_p50,
            latency_p95_ms=latency_p95,
            latency_p99_ms=latency_p99,
            success_rate=round(success_rate, 1),
            total_probes=total,
            timeout_count=timeouts,
            error_counts=error_counts,
        )

    def get_all_resolver_baselines(
        self,
        since: float | None = None,
        until: float | None = None,
    ) -> list[ResolverBaseline]:
        """Get baselines for all resolvers."""
        if until is None:
            until = time.time()
        if since is None:
            since = until - self.config.baseline_window_hours * 3600

        # Get all unique resolvers from recent samples
        all_samples = self.repository.query_range("", since, until, limit=10000)
        resolvers = list(set(s.resolver for s in all_samples))

        baselines = []
        for resolver in resolvers:
            baseline = self.get_resolver_baseline(resolver, since=since, until=until)
            if baseline:
                baselines.append(baseline)
        return baselines

    def compare_resolvers(
        self,
        hostname: str,
        record_type: str = "A",
        since: float | None = None,
        until: float | None = None,
    ) -> list[ResolverComparison]:
        """Compare all resolvers for a specific hostname."""
        if until is None:
            until = time.time()
        if since is None:
            since = until - self.config.detection_window_hours * 3600

        # Get current window samples
        all_samples = self.repository.query_range("", since, until, limit=10000)
        current_samples = [
            s for s in all_samples
            if s.hostname == hostname and s.record_type == record_type
        ]

        if not current_samples:
            return []

        # Group by resolver
        by_resolver: dict[str, list[DnsProbeSample]] = {}
        for s in current_samples:
            by_resolver.setdefault(s.resolver, []).append(s)

        # Get baselines for comparison
        baseline_since = until - self.config.baseline_window_hours * 3600
        baseline_until = since

        comparisons = []
        for resolver, samples in by_resolver.items():
            successful = [s for s in samples if s.status == "success" and s.duration_ms is not None]
            current_latency = statistics.median([s.duration_ms for s in successful]) if successful else None
            current_status = samples[-1].status if samples else "unknown"
            probe_method = samples[0].probe_method if samples else "unknown"

            # Get baseline
            baseline = self.get_resolver_baseline(
                resolver, hostname, record_type, probe_method,
                baseline_since, baseline_until
            )

            baseline_latency = baseline.latency_p50_ms if baseline else None
            baseline_success = baseline.success_rate if baseline else 0.0

            # Degradation detection
            degraded = False
            reason = None

            if baseline_latency is not None and current_latency is not None:
                latency_increase_pct = ((current_latency - baseline_latency) / baseline_latency * 100) if baseline_latency > 0 else 0
                if latency_increase_pct > 200:  # 3x baseline
                    degraded = True
                    reason = f"Latency increased {latency_increase_pct:.0f}% (baseline: {baseline_latency:.1f}ms, current: {current_latency:.1f}ms)"

            success_rate = (len(successful) / len(samples) * 100) if samples else 0
            if baseline_success > 0 and success_rate < baseline_success * 0.5:  # 50% drop
                degraded = True
                reason = f"Success rate dropped from {baseline_success:.1f}% to {success_rate:.1f}%"

            timeout_count = sum(1 for s in samples if s.status == "timeout")
            if timeout_count > len(samples) * 0.3:  # 30% timeouts
                degraded = True
                reason = f"Timeout spike: {timeout_count}/{len(samples)} timeouts"

            comparisons.append(ResolverComparison(
                resolver=resolver,
                probe_method=probe_method,
                current_latency_ms=current_latency,
                current_status=current_status,
                baseline_latency_p50_ms=baseline_latency,
                baseline_success_rate=baseline_success,
                degraded=degraded,
                degradation_reason=reason,
            ))

        return comparisons

    def detect_degradation(
        self,
        resolver: str,
        hostname: str | None = None,
        record_type: str | None = None,
        probe_method: str | None = None,
        detection_since: float | None = None,
        baseline_since: float | None = None,
    ) -> DnsDegradationEvidence:
        """Detect DNS degradation for a resolver."""
        if detection_since is None:
            detection_since = time.time() - self.config.detection_window_hours * 3600
        if baseline_since is None:
            baseline_since = detection_since - self.config.baseline_window_hours * 3600
        until = time.time()

        # Current window
        current_samples = self.repository.query_range(resolver, detection_since, until, limit=10000)
        if hostname:
            current_samples = [s for s in current_samples if s.hostname == hostname]
        if record_type:
            current_samples = [s for s in current_samples if s.record_type == record_type]
        if probe_method:
            current_samples = [s for s in current_samples if s.probe_method == probe_method]

        if not current_samples:
            return DnsDegradationEvidence(
                degraded=False,
                reason="No current samples",
                confidence=0.0,
                details={},
            )

        # Baseline window
        baseline_samples = self.repository.query_range(resolver, baseline_since, detection_since, limit=10000)
        if hostname:
            baseline_samples = [s for s in baseline_samples if s.hostname == hostname]
        if record_type:
            baseline_samples = [s for s in baseline_samples if s.record_type == record_type]
        if probe_method:
            baseline_samples = [s for s in baseline_samples if s.probe_method == probe_method]

        if len(baseline_samples) < self.config.min_baseline_samples:
            return DnsDegradationEvidence(
                degraded=False,
                reason=f"Insufficient baseline samples ({len(baseline_samples)} < {self.config.min_baseline_samples})",
                confidence=0.0,
                details={"baseline_samples": len(baseline_samples), "current_samples": len(current_samples)},
            )

        # Compute metrics
        current_successful = [s for s in current_samples if s.status == "success" and s.duration_ms is not None]
        baseline_successful = [s for s in baseline_samples if s.status == "success" and s.duration_ms is not None]

        current_durations = [s.duration_ms for s in current_successful]
        baseline_durations = [s.duration_ms for s in baseline_successful]

        current_success_rate = len(current_successful) / len(current_samples) * 100 if current_samples else 0
        baseline_success_rate = len(baseline_successful) / len(baseline_samples) * 100 if baseline_samples else 0

        current_timeouts = sum(1 for s in current_samples if s.status == "timeout")
        current_timeout_rate = current_timeouts / len(current_samples) * 100 if current_samples else 0

        reasons = []
        confidence_factors = []

        # Latency increase
        if current_durations and baseline_durations:
            current_median = statistics.median(current_durations)
            baseline_median = statistics.median(baseline_durations)
            latency_increase_pct = ((current_median - baseline_median) / baseline_median * 100) if baseline_median > 0 else 0

            if latency_increase_pct > self.config.latency_increase_threshold_pct:
                reasons.append(f"Latency increased {latency_increase_pct:.0f}% (baseline: {baseline_median:.1f}ms, current: {current_median:.1f}ms)")
                confidence_factors.append(min(latency_increase_pct / 300.0, 1.0))

        # Success rate drop
        if baseline_success_rate > 0:
            success_rate_drop = baseline_success_rate - current_success_rate
            if success_rate_drop > 20:  # 20% absolute drop
                reasons.append(f"Success rate dropped {success_rate_drop:.1f}% (baseline: {baseline_success_rate:.1f}%, current: {current_success_rate:.1f}%)")
                confidence_factors.append(min(success_rate_drop / 50.0, 1.0))

        # Timeout spike
        if current_timeout_rate > 30:  # 30% timeout rate
            reasons.append(f"Timeout rate {current_timeout_rate:.1f}%")
            confidence_factors.append(min(current_timeout_rate / 50.0, 1.0))

        degraded = len(reasons) > 0
        confidence = max(confidence_factors) if confidence_factors else 0.0

        return DnsDegradationEvidence(
            degraded=degraded,
            reason="; ".join(reasons) if reasons else None,
            confidence=round(confidence, 2),
            details={
                "resolver": resolver,
                "baseline_median_ms": round(statistics.median(baseline_durations), 1) if baseline_durations else None,
                "current_median_ms": round(statistics.median(current_durations), 1) if current_durations else None,
                "baseline_success_rate": round(baseline_success_rate, 1),
                "current_success_rate": round(current_success_rate, 1),
                "current_timeout_rate": round(current_timeout_rate, 1),
                "baseline_samples": len(baseline_samples),
                "current_samples": len(current_samples),
            },
        )
