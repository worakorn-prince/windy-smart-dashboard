"""Internet Insights configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InternetInsightsConfig:
    # Collection intervals (seconds)
    quality_gateway_interval: float = 5.0
    quality_primary_interval: float = 5.0
    quality_secondary_interval: float = 15.0
    interface_interval: float = 10.0
    tcp_stats_interval: float = 15.0
    dns_probe_interval: float = 60.0
    wifi_interval: float = 30.0
    route_interval: float = 300.0
    connection_interval: float = 5.0

    # Probe targets
    primary_target: str = "1.1.1.1"
    secondary_target: str = "8.8.8.8"
    dns_test_hostnames: list[str] = field(default_factory=lambda: ["cloudflare.com", "google.com", "example.com"])

    # Probe policy
    probe_timeout_ms: int = 2000
    max_concurrent_probes: int = 3
    icmp_payload_bytes: int = 32

    # Retention (days)
    retention_quality_days: int = 14
    retention_interface_days: int = 14
    retention_tcp_stats_days: int = 14
    retention_dns_probe_days: int = 14
    retention_diagnostic_days: int = 30
    retention_incident_days: int = 90

    # Diagnostic limits
    max_diagnostic_duration_sec: int = 120
    max_traceroute_hops: int = 30
    max_session_duration_sec: int = 180
    diagnostic_concurrency: int = 2

    # Analyzer thresholds (configurable, with defaults)
    latency_increase_threshold_pct: float = 200.0  # 3x baseline
    loss_sustained_threshold_pct: float = 5.0
    dns_degradation_threshold_ms: float = 500.0
    gateway_loss_threshold_pct: float = 10.0
    interface_error_rate_threshold: float = 0.01
    tcp_retransmit_rate_threshold_pct: float = 1.0

    # Baseline windows
    baseline_window_hours: int = 24
    detection_window_hours: int = 1
    min_baseline_samples: int = 100
    min_detection_samples: int = 20

    # Database path
    db_path: Path = field(default_factory=lambda: Path("backend/.cache/history.db"))


def _parse_float_env(key: str, default: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _parse_int_env(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _parse_str_env(key: str, default: str) -> str:
    val = os.environ.get(key)
    if val is None:
        return default
    return val


def _parse_list_env(key: str, default: list[str]) -> list[str]:
    val = os.environ.get(key)
    if val is None:
        return default
    return [x.strip() for x in val.split(",") if x.strip()]


def load_config() -> InternetInsightsConfig:
    """Load configuration from environment variables with INTERNET_INSIGHTS_ prefix."""
    return InternetInsightsConfig(
        quality_gateway_interval=_parse_float_env("INTERNET_INSIGHTS_QUALITY_GATEWAY_INTERVAL", 5.0),
        quality_primary_interval=_parse_float_env("INTERNET_INSIGHTS_QUALITY_PRIMARY_INTERVAL", 5.0),
        quality_secondary_interval=_parse_float_env("INTERNET_INSIGHTS_QUALITY_SECONDARY_INTERVAL", 15.0),
        interface_interval=_parse_float_env("INTERNET_INSIGHTS_INTERFACE_INTERVAL", 10.0),
        tcp_stats_interval=_parse_float_env("INTERNET_INSIGHTS_TCP_STATS_INTERVAL", 15.0),
        dns_probe_interval=_parse_float_env("INTERNET_INSIGHTS_DNS_PROBE_INTERVAL", 60.0),
        wifi_interval=_parse_float_env("INTERNET_INSIGHTS_WIFI_INTERVAL", 30.0),
        route_interval=_parse_float_env("INTERNET_INSIGHTS_ROUTE_INTERVAL", 300.0),
        connection_interval=_parse_float_env("INTERNET_INSIGHTS_CONNECTION_INTERVAL", 5.0),
        primary_target=_parse_str_env("INTERNET_INSIGHTS_PRIMARY_TARGET", "1.1.1.1"),
        secondary_target=_parse_str_env("INTERNET_INSIGHTS_SECONDARY_TARGET", "8.8.8.8"),
        dns_test_hostnames=_parse_list_env("INTERNET_INSIGHTS_DNS_TEST_HOSTNAMES", ["cloudflare.com", "google.com", "example.com"]),
        probe_timeout_ms=_parse_int_env("INTERNET_INSIGHTS_PROBE_TIMEOUT_MS", 2000),
        max_concurrent_probes=_parse_int_env("INTERNET_INSIGHTS_MAX_CONCURRENT_PROBES", 3),
        icmp_payload_bytes=_parse_int_env("INTERNET_INSIGHTS_ICMP_PAYLOAD_BYTES", 32),
        retention_quality_days=_parse_int_env("INTERNET_INSIGHTS_RETENTION_QUALITY_DAYS", 14),
        retention_interface_days=_parse_int_env("INTERNET_INSIGHTS_RETENTION_INTERFACE_DAYS", 14),
        retention_tcp_stats_days=_parse_int_env("INTERNET_INSIGHTS_RETENTION_TCP_STATS_DAYS", 14),
        retention_dns_probe_days=_parse_int_env("INTERNET_INSIGHTS_RETENTION_DNS_PROBE_DAYS", 14),
        retention_diagnostic_days=_parse_int_env("INTERNET_INSIGHTS_RETENTION_DIAGNOSTIC_DAYS", 30),
        retention_incident_days=_parse_int_env("INTERNET_INSIGHTS_RETENTION_INCIDENT_DAYS", 90),
        max_diagnostic_duration_sec=_parse_int_env("INTERNET_INSIGHTS_MAX_DIAGNOSTIC_DURATION_SEC", 120),
        max_traceroute_hops=_parse_int_env("INTERNET_INSIGHTS_MAX_TRACEROUTE_HOPS", 30),
        max_session_duration_sec=_parse_int_env("INTERNET_INSIGHTS_MAX_SESSION_DURATION_SEC", 180),
        diagnostic_concurrency=_parse_int_env("INTERNET_INSIGHTS_DIAGNOSTIC_CONCURRENCY", 2),
        latency_increase_threshold_pct=_parse_float_env("INTERNET_INSIGHTS_LATENCY_INCREASE_THRESHOLD_PCT", 200.0),
        loss_sustained_threshold_pct=_parse_float_env("INTERNET_INSIGHTS_LOSS_SUSTAINED_THRESHOLD_PCT", 5.0),
        dns_degradation_threshold_ms=_parse_float_env("INTERNET_INSIGHTS_DNS_DEGRADATION_THRESHOLD_MS", 500.0),
        gateway_loss_threshold_pct=_parse_float_env("INTERNET_INSIGHTS_GATEWAY_LOSS_THRESHOLD_PCT", 10.0),
        interface_error_rate_threshold=_parse_float_env("INTERNET_INSIGHTS_INTERFACE_ERROR_RATE_THRESHOLD", 0.01),
        tcp_retransmit_rate_threshold_pct=_parse_float_env("INTERNET_INSIGHTS_TCP_RETRANSMIT_RATE_THRESHOLD_PCT", 1.0),
        baseline_window_hours=_parse_int_env("INTERNET_INSIGHTS_BASELINE_WINDOW_HOURS", 24),
        detection_window_hours=_parse_int_env("INTERNET_INSIGHTS_DETECTION_WINDOW_HOURS", 1),
        min_baseline_samples=_parse_int_env("INTERNET_INSIGHTS_MIN_BASELINE_SAMPLES", 100),
        min_detection_samples=_parse_int_env("INTERNET_INSIGHTS_MIN_DETECTION_SAMPLES", 20),
    )


# Global config instance
_config: InternetInsightsConfig | None = None


def get_config() -> InternetInsightsConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config
