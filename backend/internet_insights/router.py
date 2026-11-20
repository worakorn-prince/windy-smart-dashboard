"""Internet Insights REST API router."""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from .config import get_config

logger = logging.getLogger("dashboard.internet_insights.router")

router = APIRouter(prefix="/api/internet", tags=["Internet Insights"])

VALID_RANGES = ("5m", "1h", "6h", "24h", "7d", "30d")
RANGE_SECONDS = {"5m": 300, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}


def _validate_range(range: str) -> int:
    """Validate range parameter and return seconds, or raise HTTPException."""
    if range not in VALID_RANGES:
        raise HTTPException(status_code=422, detail=f"Invalid range. Must be one of: {sorted(VALID_RANGES)}")
    return RANGE_SECONDS[range]


router = APIRouter(prefix="/api/internet", tags=["Internet Insights"])


# Lazy initialization helpers
_metrics_adapter = None
_ping_adapter = None
_speedtest_adapter = None
_net_cache_adapter = None
_history_adapter = None
_quality_repo = None
_interface_repo = None
_tcp_stats_repo = None
_dns_probe_repo = None
_route_repo = None
_traceroute_repo = None
_quality_analyzer = None
_dns_analyzer = None
_route_analyzer = None
_collector_manager = None


def _get_metrics_adapter():
    global _metrics_adapter
    if _metrics_adapter is None:
        from .adapters.metrics_adapter import MetricsAdapter
        _metrics_adapter = MetricsAdapter()
    return _metrics_adapter


def _get_ping_adapter():
    global _ping_adapter
    if _ping_adapter is None:
        from .adapters.ping_adapter import PingAdapter
        _ping_adapter = PingAdapter()
    return _ping_adapter


def _get_speedtest_adapter():
    global _speedtest_adapter
    if _speedtest_adapter is None:
        from .adapters.speedtest_adapter import SpeedtestAdapter
        _speedtest_adapter = SpeedtestAdapter()
    return _speedtest_adapter


def _get_net_cache_adapter():
    global _net_cache_adapter
    if _net_cache_adapter is None:
        from .adapters.net_cache_adapter import NetCacheAdapter
        _net_cache_adapter = NetCacheAdapter()
    return _net_cache_adapter


def _get_history_adapter():
    global _history_adapter
    if _history_adapter is None:
        from .adapters.history_adapter import HistoryAdapter
        _history_adapter = HistoryAdapter()
    return _history_adapter


def _get_quality_repo():
    global _quality_repo
    if _quality_repo is None:
        from .storage.repositories import QualitySampleRepository
        _quality_repo = QualitySampleRepository()
    return _quality_repo


def _get_interface_repo():
    global _interface_repo
    if _interface_repo is None:
        from .storage.repositories import InterfaceSampleRepository
        _interface_repo = InterfaceSampleRepository()
    return _interface_repo


def _get_tcp_stats_repo():
    global _tcp_stats_repo
    if _tcp_stats_repo is None:
        from .storage.repositories import TcpStatsRepository
        _tcp_stats_repo = TcpStatsRepository()
    return _tcp_stats_repo


def _get_dns_probe_repo():
    global _dns_probe_repo
    if _dns_probe_repo is None:
        from .storage.repositories import DnsProbeRepository
        _dns_probe_repo = DnsProbeRepository()
    return _dns_probe_repo


def _get_route_repo():
    global _route_repo
    if _route_repo is None:
        from .storage.repositories import RouteSampleRepository
        _route_repo = RouteSampleRepository()
    return _route_repo


def _get_traceroute_repo():
    global _traceroute_repo
    if _traceroute_repo is None:
        from .storage.repositories import TracerouteSampleRepository
        _traceroute_repo = TracerouteSampleRepository()
    return _traceroute_repo


def _get_quality_analyzer():
    global _quality_analyzer
    if _quality_analyzer is None:
        from .analyzers.quality import QualityAnalyzer
        _quality_analyzer = QualityAnalyzer()
    return _quality_analyzer


def _get_dns_analyzer():
    global _dns_analyzer
    if _dns_analyzer is None:
        from .analyzers.dns import DnsAnalyzer
        _dns_analyzer = DnsAnalyzer()
    return _dns_analyzer


def _get_route_analyzer():
    global _route_analyzer
    if _route_analyzer is None:
        from .analyzers.route import RouteAnalyzer
        _route_analyzer = RouteAnalyzer()
    return _route_analyzer
    global _quality_analyzer
    if _quality_analyzer is None:
        from .analyzers.quality import QualityAnalyzer
        _quality_analyzer = QualityAnalyzer()
    return _quality_analyzer


def _get_collector_manager():
    global _collector_manager
    if _collector_manager is None:
        from .services.collector_manager import get_collector_manager
        _collector_manager = get_collector_manager()
    return _collector_manager


def _common_metadata(source: str = "collector", status: str = "ok", errors: list[str] | None = None, coverage: float = 1.0) -> dict:
    """Generate common response metadata."""
    now = time.time()
    return {
        "generated_at": now,
        "data_window": {"start": now - 300, "end": now},
        "source": source,
        "status": status,
        "errors": errors or [],
        "coverage": coverage,
    }


def _bucket_samples(samples: list, step_seconds: int, value_fn, agg_fn) -> list:
    """Bucket samples into time windows and aggregate."""
    if not samples or step_seconds <= 0:
        return []

    buckets: dict[int, list] = {}
    for s in samples:
        bucket_ts = int(s.ts // step_seconds) * step_seconds
        buckets.setdefault(bucket_ts, []).append(s)

    result = []
    for bucket_ts in sorted(buckets.keys()):
        bucket_samples = buckets[bucket_ts]
        values = [value_fn(s) for s in bucket_samples if value_fn(s) is not None]
        if values:
            result.append({
                "ts": bucket_ts,
                "value": agg_fn(values),
                "count": len(values),
            })
    return result


@router.get("/overview")
async def get_overview() -> dict:
    """Summary health overview."""
    try:
        quality_repo = _get_quality_repo()
        interface_repo = _get_interface_repo()
        metrics_adapter = _get_metrics_adapter()

        gateway_sample = quality_repo.get_latest("gateway")
        primary_sample = quality_repo.get_latest("primary")
        secondary_sample = quality_repo.get_latest("secondary")

        latest_interfaces = interface_repo.get_all_latest()
        active_interface = None
        current_throughput = {"send_bps": 0, "recv_bps": 0, "interface_id": None}

        for iface in latest_interfaces:
            if iface.link_status == "up" and (iface.send_bps > 0 or iface.recv_bps > 0):
                active_interface = iface
                current_throughput = {
                    "send_bps": iface.send_bps,
                    "recv_bps": iface.recv_bps,
                    "interface_id": iface.interface_id,
                }
                break

        net_snapshot = metrics_adapter.get_network_snapshot()
        adapters = net_snapshot.get("adapters", [])

        connection_status = (
            "connected"
            if gateway_sample and gateway_sample.status == "success" and primary_sample and primary_sample.status == "success"
            else "degraded"
            if gateway_sample and gateway_sample.status == "success"
            else "disconnected"
        )

        recent_incidents = []

        dns_configured = []
        for adapter in adapters:
            dns_configured.extend(adapter.get("dns", []))

        response = {
            "connection_status": connection_status,
            "internet_quality": {
                "primary": {
                    "target_id": "primary",
                    "latency_ms": primary_sample.rtt_ms if primary_sample else None,
                    "jitter_ms": None,
                    "loss_pct": 0.0 if primary_sample and primary_sample.status == "success" else 100.0,
                    "status": primary_sample.status if primary_sample else "unavailable",
                },
                "secondary": {
                    "target_id": "secondary",
                    "latency_ms": secondary_sample.rtt_ms if secondary_sample else None,
                    "jitter_ms": None,
                    "loss_pct": 0.0 if secondary_sample and secondary_sample.status == "success" else 100.0,
                    "status": secondary_sample.status if secondary_sample else "unavailable",
                },
                "gateway": {
                    "target_id": "gateway",
                    "latency_ms": gateway_sample.rtt_ms if gateway_sample else None,
                    "jitter_ms": None,
                    "loss_pct": 0.0 if gateway_sample and gateway_sample.status == "success" else 100.0,
                    "status": gateway_sample.status if gateway_sample else "unavailable",
                },
            },
            "current_throughput": current_throughput,
            "active_interface": {
                "id": active_interface.interface_id if active_interface else None,
                "name": None,
                "status": active_interface.link_status if active_interface else "down",
                "speed_mbps": None,
            } if active_interface else None,
            "recent_incidents": recent_incidents,
            "dns_health": {
                "configured": list(set(dns_configured))[:2],
                "primary_status": "ok" if dns_configured else "unavailable",
                "secondary_status": "ok" if len(dns_configured) > 1 else "unavailable",
            },
            **_common_metadata(),
        }
        return response
    except Exception as e:
        logger.exception("Overview endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/quality")
async def get_quality() -> dict:
    """Current latency, jitter, packet loss."""
    try:
        quality_repo = _get_quality_repo()
        targets = ["gateway", "primary", "secondary"]
        result_targets = []

        for target_id in targets:
            sample = quality_repo.get_latest(target_id)
            if sample:
                since = time.time() - 300
                samples = quality_repo.query_range(target_id, since, limit=100)
                if samples:
                    rtts = [s.rtt_ms for s in samples if s.rtt_ms is not None]
                    timeouts = sum(1 for s in samples if s.status == "timeout")
                    total = len(samples)
                    loss_pct = (timeouts / total * 100) if total > 0 else 0.0

                    if rtts:
                        rtts_sorted = sorted(rtts)
                        latency = {
                            "min": rtts_sorted[0],
                            "median": rtts_sorted[len(rtts_sorted) // 2],
                            "p95": rtts_sorted[int(len(rtts_sorted) * 0.95)],
                            "max": rtts_sorted[-1],
                            "count": len(rtts),
                            "timeouts": timeouts,
                        }
                    else:
                        latency = {"min": None, "median": None, "p95": None, "max": None, "count": 0, "timeouts": timeouts}

                    jitter_ms = None
                    if len(rtts) > 1:
                        import statistics
                        jitter_ms = round(statistics.stdev(rtts), 1)

                    result_targets.append({
                        "target_id": target_id,
                        "address": get_config().primary_target if target_id == "primary" else get_config().secondary_target if target_id == "secondary" else "gateway",
                        "probe_type": "tcp",
                        "latency_ms": latency,
                        "jitter_ms": jitter_ms,
                        "loss_pct": round(loss_pct, 1),
                        "status": sample.status,
                        "last_probe_at": sample.ts,
                    })

        return {"targets": result_targets, **_common_metadata()}
    except Exception as e:
        logger.exception("Quality endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/quality/history")
async def get_quality_history(
    range: Literal["5m", "1h", "6h", "24h", "7d", "30d"] = Query(default="1h"),
    target_id: str = Query(default="primary"),
    step: int = Query(default=60, ge=10, le=3600, description="Bucket size in seconds"),
) -> dict:
    """Historical quality samples with optional bucket aggregation."""
    try:
        quality_repo = _get_quality_repo()
        range_seconds = _validate_range(range)
        since = time.time() - range_seconds

        samples = quality_repo.query_range(target_id, since, limit=10000)

        if step > 60 and len(samples) > 200:
            # Bucket aggregation
            def latency_agg(values: list[float]) -> dict:
                sorted_v = sorted(values)
                n = len(sorted_v)
                return {
                    "min": sorted_v[0],
                    "median": sorted_v[n // 2],
                    "p95": sorted_v[int(n * 0.95)] if n > 1 else sorted_v[0],
                    "max": sorted_v[-1],
                }

            buckets = _bucket_samples(
                samples,
                step,
                value_fn=lambda s: s.rtt_ms,
                agg_fn=latency_agg,
            )

            points = []
            for b in buckets:
                points.append({
                    "ts": b["ts"],
                    "latency": b["value"],
                    "count": b["count"],
                })
        else:
            # Raw points
            points = []
            for s in samples:
                points.append({
                    "ts": s.ts,
                    "target_id": s.target_id,
                    "probe_type": s.probe_type,
                    "rtt_ms": s.rtt_ms,
                    "status": s.status,
                    "error_code": s.error_code,
                })

        return {
            "target_id": target_id,
            "range": range,
            "step": step,
            "points": points,
            **_common_metadata(source="storage"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Quality history endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/quality/status")
async def get_quality_status(
    range: Literal["5m", "1h", "6h", "24h", "7d", "30d"] = Query(default="1h"),
) -> dict:
    """Aggregated quality status with evidence."""
    try:
        analyzer = _get_quality_analyzer()

        analyses = analyzer.analyze_all_targets(range_key=range)
        overall = analyzer.get_overall_status(analyses)

        return {
            "range": range,
            "overall": overall,
            "targets": {
                target_id: {
                    "latency": {
                        "min_ms": a.latency.min_ms,
                        "median_ms": a.latency.median_ms,
                        "p95_ms": a.latency.p95_ms,
                        "max_ms": a.latency.max_ms,
                        "count": a.latency.count,
                        "timeouts": a.latency.timeouts,
                    },
                    "jitter": {
                        "mean_abs_diff_ms": a.jitter.mean_abs_diff_ms,
                        "samples_used": a.jitter.samples_used,
                    },
                    "loss": {
                        "total_samples": a.loss.total_samples,
                        "loss_pct": a.loss.loss_pct,
                        "by_error_code": a.loss.by_error_code,
                    },
                    "degradation": {
                        "degraded": a.degradation.degraded,
                        "reason": a.degradation.reason,
                        "confidence": a.degradation.confidence,
                        "details": a.degradation.details,
                    },
                    "last_probe_at": a.last_probe_at,
                    "sample_count": a.sample_count,
                }
                for target_id, a in analyses.items()
            },
            **_common_metadata(source="analyzer"),
        }
    except Exception as e:
        logger.exception("Quality status endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/tcp/stats")
async def get_tcp_stats(
    range: Literal["5m", "1h", "6h", "24h", "7d", "30d"] = Query(default="1h"),
) -> dict:
    """Current TCP statistics and history."""
    try:
        tcp_repo = _get_tcp_stats_repo()
        range_seconds = _validate_range(range)
        since = time.time() - range_seconds

        latest = tcp_repo.get_latest()
        samples = tcp_repo.query_range(since, limit=1000)

        history = []
        for s in samples:
            history.append({
                "ts": s.ts,
                "active_opens": s.active_opens,
                "passive_opens": s.passive_opens,
                "failed_attempts": s.failed_attempts,
                "established_resets": s.established_resets,
                "current_established": s.current_established,
                "segments_sent": s.segments_sent,
                "segments_received": s.segments_received,
                "segments_retransmitted": s.segments_retransmitted,
                "source": s.source,
            })

        return {
            "range": range,
            "current": {
                "active_opens": latest.active_opens if latest else None,
                "passive_opens": latest.passive_opens if latest else None,
                "failed_attempts": latest.failed_attempts if latest else None,
                "established_resets": latest.established_resets if latest else None,
                "current_established": latest.current_established if latest else None,
                "segments_sent": latest.segments_sent if latest else None,
                "segments_received": latest.segments_received if latest else None,
                "segments_retransmitted": latest.segments_retransmitted if latest else None,
                "source": latest.source if latest else None,
                "ts": latest.ts if latest else None,
            },
            "history": history,
            **_common_metadata(source="storage"),
        }
    except Exception as e:
        logger.exception("TCP stats endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/interfaces")
async def get_interfaces() -> dict:
    """Interface information."""
    try:
        interface_repo = _get_interface_repo()
        metrics_adapter = _get_metrics_adapter()

        latest_samples = interface_repo.get_all_latest()
        net_snapshot = metrics_adapter.get_network_snapshot()
        adapters = net_snapshot.get("adapters", [])

        interfaces = []
        for sample in latest_samples:
            adapter_info = next((a for a in adapters if a.get("connection_name") == sample.interface_id or a.get("name") == sample.interface_id), {})

            interfaces.append({
                "id": sample.interface_id,
                "name": adapter_info.get("description", sample.interface_id),
                "description": adapter_info.get("description", ""),
                "mac": adapter_info.get("mac", ""),
                "type": adapter_info.get("type", ""),
                "speed_mbps": adapter_info.get("speed_mbps", 0),
                "status": sample.link_status or "unknown",
                "connection_name": adapter_info.get("connection_name", sample.interface_id),
                "manufacturer": adapter_info.get("manufacturer", ""),
                "ipv4": adapter_info.get("ipv4", []),
                "ipv6": adapter_info.get("ipv6", []),
                "gateway": adapter_info.get("gateway", []),
                "dns": adapter_info.get("dns", []),
                "current_rates": {
                    "send_bps": sample.send_bps,
                    "recv_bps": sample.recv_bps,
                },
                "errors": {
                    "in": sample.errors_in,
                    "out": sample.errors_out,
                    "discards_in": sample.discards_in,
                    "discards_out": sample.discards_out,
                },
            })

        return {"interfaces": interfaces, **_common_metadata()}
    except Exception as e:
        logger.exception("Interfaces endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/interfaces/{interface_id}/history")
async def get_interface_history(
    interface_id: str,
    range: Literal["5m", "1h", "6h", "24h", "7d", "30d"] = Query(default="1h"),
) -> dict:
    """Per-interface history."""
    try:
        interface_repo = _get_interface_repo()
        range_seconds = _validate_range(range)
        since = time.time() - range_seconds

        samples = interface_repo.query_range(interface_id, since, limit=1000)

        points = []
        for s in samples:
            points.append({
                "ts": s.ts,
                "bytes_sent": s.bytes_sent,
                "bytes_recv": s.bytes_recv,
                "send_bps": s.send_bps,
                "recv_bps": s.recv_bps,
                "packets_sent": s.packets_sent,
                "packets_recv": s.packets_recv,
                "errors_in": s.errors_in,
                "errors_out": s.errors_out,
                "discards_in": s.discards_in,
                "discards_out": s.discards_out,
                "link_status": s.link_status,
            })

        return {
            "interface_id": interface_id,
            "range": range,
            "points": points,
            **_common_metadata(source="storage"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Interface history endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/collectors/status")
async def get_collectors_status() -> dict:
    """Get status of all background collectors."""
    try:
        cm = _get_collector_manager()
        return {"collectors": cm.get_status(), **_common_metadata(source="service")}
    except Exception as e:
        logger.exception("Collector status endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ===== DNS Endpoints =====

@router.get("/dns")
async def get_dns() -> dict:
    """DNS configuration and health overview."""
    try:
        dns_repo = _get_dns_probe_repo()
        metrics_adapter = _get_metrics_adapter()
        dns_analyzer = _get_dns_analyzer()

        # Get configured resolvers from adapters
        snapshot = metrics_adapter.get_network_snapshot()
        configured_resolvers = []
        for adapter in snapshot.get("adapters", []):
            for dns in adapter.get("dns", []):
                if dns and dns not in configured_resolvers:
                    configured_resolvers.append(dns)

        # Get latest probe for each resolver
        resolver_health = []
        for resolver in configured_resolvers:
            latest = dns_repo.query_range(resolver, time.time() - 300, limit=10)
            if latest:
                successful = [s for s in latest if s.status == "success" and s.duration_ms is not None]
                timeouts = sum(1 for s in latest if s.status == "timeout")
                total = len(latest)
                avg_latency = statistics.mean([s.duration_ms for s in successful]) if successful else None
                success_rate = (len(successful) / total * 100) if total > 0 else 0
                resolver_health.append({
                    "resolver": resolver,
                    "status": "ok" if success_rate > 50 else "degraded" if success_rate > 0 else "down",
                    "avg_latency_ms": round(avg_latency, 1) if avg_latency else None,
                    "success_rate": round(success_rate, 1),
                    "recent_probes": total,
                    "last_probe_at": latest[0].ts if latest else None,
                })
            else:
                resolver_health.append({
                    "resolver": resolver,
                    "status": "unknown",
                    "avg_latency_ms": None,
                    "success_rate": 0,
                    "recent_probes": 0,
                    "last_probe_at": None,
                })

        return {
            "configured_resolvers": configured_resolvers,
            "resolver_health": resolver_health,
            **_common_metadata(),
        }
    except Exception as e:
        logger.exception("DNS endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/dns/history")
async def get_dns_history(
    range: Literal["5m", "1h", "6h", "24h", "7d", "30d"] = Query(default="1h"),
    resolver: str = Query(default=""),
    hostname: str = Query(default=""),
    record_type: str = Query(default=""),
    probe_method: str = Query(default=""),
    step: int = Query(default=60, ge=10, le=3600),
) -> dict:
    """DNS probe history with optional filters."""
    try:
        import statistics
        dns_repo = _get_dns_probe_repo()
        range_seconds = _validate_range(range)
        since = time.time() - range_seconds

        # Query all resolvers if not specified
        if resolver:
            samples = dns_repo.query_range(resolver, since, limit=10000)
        else:
            # Get all samples by querying each known resolver
            # For simplicity, query with empty resolver (will need adjustment)
            samples = dns_repo.query_range("", since, limit=10000)

        if hostname:
            samples = [s for s in samples if s.hostname == hostname]
        if record_type:
            samples = [s for s in samples if s.record_type == record_type]
        if probe_method:
            samples = [s for s in samples if s.probe_method == probe_method]

        if step > 60 and len(samples) > 200:
            def latency_agg(values: list[float]) -> dict:
                sorted_v = sorted(values)
                n = len(sorted_v)
                return {
                    "min": sorted_v[0],
                    "median": sorted_v[n // 2],
                    "p95": sorted_v[int(n * 0.95)] if n > 1 else sorted_v[0],
                    "max": sorted_v[-1],
                }

            buckets = _bucket_samples(
                samples,
                step,
                value_fn=lambda s: s.duration_ms,
                agg_fn=latency_agg,
            )

            points = []
            for b in buckets:
                points.append({
                    "ts": b["ts"],
                    "latency": b["value"],
                    "count": b["count"],
                })
        else:
            points = []
            for s in samples:
                points.append({
                    "ts": s.ts,
                    "resolver": s.resolver,
                    "hostname": s.hostname,
                    "record_type": s.record_type,
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                    "answer_count": s.answer_count,
                    "error_code": s.error_code,
                    "probe_method": s.probe_method,
                })

        return {
            "range": range,
            "step": step,
            "points": points,
            **_common_metadata(source="storage"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("DNS history endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/dns/compare")
async def get_dns_compare(
    hostname: str = Query(default="cloudflare.com"),
    record_type: str = Query(default="A"),
) -> dict:
    """On-demand resolver comparison for a hostname."""
    try:
        dns_analyzer = _get_dns_analyzer()
        collector_manager = _get_collector_manager()
        dns_collector = collector_manager.get_collector("dns")

        if dns_collector:
            comparison = await dns_collector.compare_resolvers(hostname, record_type)
        else:
            comparison = dns_analyzer.compare_resolvers(hostname, record_type)

        return {
            "hostname": hostname,
            "record_type": record_type,
            "comparison": comparison,
            **_common_metadata(),
        }
    except Exception as e:
        logger.exception("DNS compare endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ===== Route Endpoints =====

@router.get("/routes")
async def get_routes() -> dict:
    """Current route table snapshot."""
    try:
        route_repo = _get_route_repo()
        collector_manager = _get_collector_manager()
        route_collector = collector_manager.get_collector("route")

        # Get latest route snapshot
        routes = route_repo.get_latest_snapshot()

        # Get default gateway info
        gateway_ip = None
        gateway_iface = None
        if route_collector:
            gateway_ip, gateway_iface = route_collector.get_default_gateway()

        route_list = []
        for r in routes:
            route_list.append({
                "destination": r.destination,
                "prefix_length": r.prefix_length,
                "next_hop": r.next_hop,
                "interface_index": r.interface_index,
                "metric": r.metric,
                "protocol": r.protocol,
                "age": r.age,
                "origin": r.origin,
                "is_default": bool(r.is_default),
            })

        return {
            "routes": route_list,
            "default_gateway": gateway_ip,
            "gateway_interface_index": gateway_iface,
            "snapshot_ts": routes[0].ts if routes else None,
            **_common_metadata(),
        }
    except Exception as e:
        logger.exception("Routes endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/diagnostics/traceroute")
async def post_traceroute(
    target: str = Query(...),
    max_hops: int = Query(default=30, ge=1, le=64),
    timeout_ms: int = Query(default=3000, ge=500, le=30000),
    protocol: Literal["icmp", "udp"] = Query(default="udp"),
) -> dict:
    """On-demand traceroute to target."""
    try:
        collector_manager = _get_collector_manager()
        route_collector = collector_manager.get_collector("route")
        traceroute_repo = _get_traceroute_repo()

        if not route_collector:
            raise HTTPException(status_code=503, detail="Route collector not available")

        # Create diagnostic session
        from ..storage.repositories import DiagnosticSessionRepository, DiagnosticResultRepository, generate_session_id
        session_repo = DiagnosticSessionRepository()
        result_repo = DiagnosticResultRepository()
        session_id = generate_session_id()

        session = await asyncio.to_thread(
            session_repo.create,
            type('DiagnosticSession', (), {
                'id': session_id,
                'started_at': time.time(),
                'completed_at': None,
                'status': 'running',
                'target': target,
                'diagnostic_type': 'traceroute',
                'config_json': f'{{"max_hops": {max_hops}, "timeout_ms": {timeout_ms}, "protocol": "{protocol}"}}',
                'summary_json': None,
                'error': None,
            })()
        )

        try:
            hops = await route_collector.traceroute(target, max_hops, timeout_ms, protocol)

            # Store hop results
            results = [
                type('DiagnosticResult', (), {
                    'session_id': session_id,
                    'ts': time.time(),
                    'sequence': i,
                    'result_type': 'hop',
                    'payload_json': json.dumps({
                        "hop": h.hop,
                        "address": h.address,
                        "rtt_ms": h.rtt_ms,
                        "status": h.status,
                    }),
                })()
                for i, h in enumerate(hops)
            ]
            await asyncio.to_thread(result_repo.insert_batch, results)

            # Store in traceroute samples table
            ts = time.time()
            traceroute_samples = [
                type('TracerouteSample', (), {
                    'ts': ts,
                    'destination': target,
                    'hop': h.hop,
                    'address': h.address,
                    'rtt_ms': h.rtt_ms,
                    'status': h.status,
                })()
                for h in hops
            ]
            await asyncio.to_thread(traceroute_repo.insert_batch, traceroute_samples)

            # Update session
            await asyncio.to_thread(
                session_repo.update,
                type('DiagnosticSession', (), {
                    'id': session_id,
                    'started_at': session.started_at,
                    'completed_at': time.time(),
                    'status': 'completed',
                    'target': target,
                    'diagnostic_type': 'traceroute',
                    'config_json': f'{{"max_hops": {max_hops}, "timeout_ms": {timeout_ms}, "protocol": "{protocol}"}}',
                    'summary_json': f'{{"hop_count": {len(hops)}, "max_rtt_ms": max((h.rtt_ms or 0 for h in hops), default=0)}}',
                    'error': None,
                })()
            )

            return {
                "session_id": session_id,
                "target": target,
                "max_hops": max_hops,
                "protocol": protocol,
                "hops": [
                    {
                        "hop": h.hop,
                        "address": h.address,
                        "rtt_ms": h.rtt_ms,
                        "status": h.status,
                    }
                    for h in hops
                ],
                **_common_metadata(),
            }
        except Exception as e:
            await asyncio.to_thread(
                session_repo.update,
                type('DiagnosticSession', (), {
                    'id': session_id,
                    'started_at': session.started_at,
                    'completed_at': time.time(),
                    'status': 'failed',
                    'target': target,
                    'diagnostic_type': 'traceroute',
                    'config_json': f'{{"max_hops": {max_hops}, "timeout_ms": {timeout_ms}, "protocol": "{protocol}"}}',
                    'summary_json': None,
                    'error': str(e),
                })()
            )
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Traceroute endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/routes/history")
async def get_routes_history(
    range: Literal["5m", "1h", "6h", "24h", "7d", "30d"] = Query(default="1h"),
) -> dict:
    """Route changes history."""
    try:
        route_analyzer = _get_route_analyzer()
        range_seconds = _validate_range(range)
        since = time.time() - range_seconds

        changes = route_analyzer.detect_route_changes(since)

        change_list = []
        for c in changes:
            change_list.append({
                "timestamp": c.timestamp,
                "change_type": c.change_type,
                "details": c.details,
                "severity": c.severity,
            })

        return {
            "range": range,
            "changes": change_list,
            **_common_metadata(source="analyzer"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Route history endpoint failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
