"""Internet Insights REST API router."""

from __future__ import annotations

import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from .config import get_config

logger = logging.getLogger("dashboard.internet_insights.router")

router = APIRouter(prefix="/api/internet", tags=["Internet Insights"])


# Lazy initialization helpers
_metrics_adapter = None
_ping_adapter = None
_speedtest_adapter = None
_net_cache_adapter = None
_history_adapter = None
_quality_repo = None
_interface_repo = None
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


@router.get("/overview")
async def get_overview() -> dict:
    """Summary health overview."""
    try:
        quality_repo = _get_quality_repo()
        interface_repo = _get_interface_repo()
        metrics_adapter = _get_metrics_adapter()

        # Get current quality samples
        gateway_sample = quality_repo.get_latest("gateway")
        primary_sample = quality_repo.get_latest("primary")
        secondary_sample = quality_repo.get_latest("secondary")

        # Get active interface
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

        # Get network snapshot for additional info
        net_snapshot = metrics_adapter.get_network_snapshot()
        adapters = net_snapshot.get("adapters", [])
        wifi = net_snapshot.get("wifi")
        public_ip = net_snapshot.get("public_ip")

        # Determine connection status
        connection_status = "disconnected"
        if gateway_sample and gateway_sample.status == "success":
            if primary_sample and primary_sample.status == "success":
                connection_status = "connected"
            else:
                connection_status = "degraded"

        # Get recent incidents (placeholder for now)
        recent_incidents = []

        # DNS health from adapters
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
                # Get more samples for stats
                since = time.time() - 300  # last 5 minutes
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

                    # Calculate jitter (std deviation of RTT)
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
) -> dict:
    """Historical quality samples."""
    try:
        quality_repo = _get_quality_repo()
        # Validate range
        valid_ranges = ["5m", "1h", "6h", "24h", "7d", "30d"]
        if range not in valid_ranges:
            raise HTTPException(status_code=422, detail=f"Invalid range. Must be one of: {valid_ranges}")

        # Calculate time window
        range_seconds = {"5m": 300, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}
        since = time.time() - range_seconds[range]

        samples = quality_repo.query_range(target_id, since, limit=1000)

        # Aggregate into buckets for response
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
            "points": points,
            **_common_metadata(source="storage"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Quality history endpoint failed")
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

        # Merge interface samples with adapter details
        interfaces = []
        for sample in latest_samples:
            # Find matching adapter
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
        valid_ranges = ["5m", "1h", "6h", "24h", "7d", "30d"]
        if range not in valid_ranges:
            raise HTTPException(status_code=422, detail=f"Invalid range. Must be one of: {valid_ranges}")

        range_seconds = {"5m": 300, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800, "30d": 2592000}
        since = time.time() - range_seconds[range]

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
