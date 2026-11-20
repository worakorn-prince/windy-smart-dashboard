"""Route analyzer for route change detection, gateway reachability, and path comparison."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from ..config import get_config
from ..storage.repositories import (
    DiagnosticSessionRepository,
    DiagnosticResultRepository,
    DiagnosticSession,
    DiagnosticResult,
)

logger = logging.getLogger("dashboard.internet_insights.analyzers.route")


@dataclass
class RouteChange:
    timestamp: float
    change_type: str  # gateway_changed, interface_changed, metric_changed, route_added, route_removed
    details: dict[str, Any]
    severity: str  # info, warning, critical


@dataclass
class GatewayReachability:
    gateway_ip: str
    interface_index: int | None
    reachable: bool
    latency_ms: float | None
    last_check: float
    consecutive_failures: int


@dataclass
class PathComparison:
    destination: str
    baseline_hops: list[dict[str, Any]]
    current_hops: list[dict[str, Any]]
    changed: bool
    change_details: list[str]


class RouteAnalyzer:
    """Analyze route snapshots and traceroute results for changes and reachability."""

    def __init__(self):
        self.config = get_config()
        self._session_repo: DiagnosticSessionRepository | None = None
        self._result_repo: DiagnosticResultRepository | None = None

    def _get_repos(self):
        if self._session_repo is None:
            from ..storage.repositories import DiagnosticSessionRepository, DiagnosticResultRepository
            self._session_repo = DiagnosticSessionRepository()
            self._result_repo = DiagnosticResultRepository()
        return self._session_repo, self._result_repo

    def get_route_history(
        self,
        since: float,
        until: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get route snapshots from diagnostic sessions."""
        if until is None:
            until = time.time()

        session_repo, result_repo = self._get_repos()
        sessions = session_repo.list_sessions(status="completed", limit=limit)

        route_snapshots = []
        for session in sessions:
            if session.diagnostic_type == "route" and session.started_at >= since and session.started_at <= until:
                results = result_repo.get_by_session(session.id)
                routes = []
                for r in results:
                    if r.result_type == "route":
                        try:
                            routes.append(json.loads(r.payload_json))
                        except Exception:
                            pass
                if routes:
                    route_snapshots.append({
                        "timestamp": session.started_at,
                        "session_id": session.id,
                        "routes": routes,
                        "summary": json.loads(session.summary_json) if session.summary_json else {},
                    })

        return sorted(route_snapshots, key=lambda x: x["timestamp"], reverse=True)

    def detect_route_changes(
        self,
        since: float,
        until: float | None = None,
    ) -> list[RouteChange]:
        """Detect route table changes over time."""
        if until is None:
            until = time.time()

        snapshots = self.get_route_history(since, until)
        if len(snapshots) < 2:
            return []

        changes = []
        for i in range(1, len(snapshots)):
            prev = snapshots[i - 1]
            curr = snapshots[i]

            prev_routes = self._normalize_routes(prev["routes"])
            curr_routes = self._normalize_routes(curr["routes"])

            # Compare default gateway
            prev_gw = self._get_default_gateway(prev_routes)
            curr_gw = self._get_default_gateway(curr_routes)

            if prev_gw != curr_gw:
                changes.append(RouteChange(
                    timestamp=curr["timestamp"],
                    change_type="gateway_changed",
                    details={
                        "previous_gateway": prev_gw,
                        "current_gateway": curr_gw,
                    },
                    severity="warning" if prev_gw and curr_gw else "critical",
                ))

            # Compare interface for default route
            prev_iface = self._get_default_interface(prev_routes)
            curr_iface = self._get_default_interface(curr_routes)

            if prev_iface != curr_iface:
                changes.append(RouteChange(
                    timestamp=curr["timestamp"],
                    change_type="interface_changed",
                    details={
                        "previous_interface": prev_iface,
                        "current_interface": curr_iface,
                    },
                    severity="warning",
                ))

            # Compare route metrics for same destinations
            for dest, curr_route in curr_routes.items():
                if dest in prev_routes:
                    prev_route = prev_routes[dest]
                    if prev_route.get("metric") != curr_route.get("metric"):
                        changes.append(RouteChange(
                            timestamp=curr["timestamp"],
                            change_type="metric_changed",
                            details={
                                "destination": dest,
                                "previous_metric": prev_route.get("metric"),
                                "current_metric": curr_route.get("metric"),
                            },
                            severity="info",
                        ))

            # Detect added/removed routes
            prev_dests = set(prev_routes.keys())
            curr_dests = set(curr_routes.keys())

            for added in curr_dests - prev_dests:
                changes.append(RouteChange(
                    timestamp=curr["timestamp"],
                    change_type="route_added",
                    details={"destination": added, "route": curr_routes[added]},
                    severity="info",
                ))

            for removed in prev_dests - curr_dests:
                changes.append(RouteChange(
                    timestamp=curr["timestamp"],
                    change_type="route_removed",
                    details={"destination": removed, "route": prev_routes[removed]},
                    severity="warning",
                ))

        return changes

    def _normalize_routes(self, routes: list[dict]) -> dict[str, dict]:
        """Normalize route list to dict keyed by destination/prefix."""
        normalized = {}
        for r in routes:
            dest = r.get("destination", "unknown")
            prefix = r.get("prefix_length", 0)
            key = f"{dest}/{prefix}"
            normalized[key] = r
        return normalized

    def _get_default_gateway(self, routes: dict[str, dict]) -> str | None:
        """Extract default gateway from routes."""
        for route in routes.values():
            if route.get("prefix_length") == 0 or route.get("destination") == "0.0.0.0":
                return route.get("next_hop")
        return None

    def _get_default_interface(self, routes: dict[str, dict]) -> int | None:
        """Extract default route interface index."""
        for route in routes.values():
            if route.get("prefix_length") == 0 or route.get("destination") == "0.0.0.0":
                return route.get("interface_index")
        return None

    def check_gateway_reachability(
        self,
        gateway_ip: str,
        interface_index: int | None = None,
    ) -> GatewayReachability:
        """Check if default gateway is reachable."""
        # This would typically use ICMP ping or TCP connect
        # For now, return a structure that can be populated by caller
        return GatewayReachability(
            gateway_ip=gateway_ip,
            interface_index=interface_index,
            reachable=False,
            latency_ms=None,
            last_check=time.time(),
            consecutive_failures=0,
        )

    def compare_traceroute_paths(
        self,
        destination: str,
        baseline_session_id: str,
        current_session_id: str,
    ) -> PathComparison:
        """Compare two traceroute paths to the same destination."""
        _, result_repo = self._get_repos()

        baseline_results = result_repo.get_by_session(baseline_session_id)
        current_results = result_repo.get_by_session(current_session_id)

        baseline_hops = []
        current_hops = []

        for r in baseline_results:
            if r.result_type == "hop":
                try:
                    baseline_hops.append(json.loads(r.payload_json))
                except Exception:
                    pass

        for r in current_results:
            if r.result_type == "hop":
                try:
                    current_hops.append(json.loads(r.payload_json))
                except Exception:
                    pass

        # Compare paths
        changed = False
        change_details = []

        min_len = min(len(baseline_hops), len(current_hops))
        for i in range(min_len):
            b = baseline_hops[i]
            c = current_hops[i]
            if b.get("address") != c.get("address"):
                changed = True
                change_details.append(f"Hop {i+1}: {b.get('address')} -> {c.get('address')}")

        if len(baseline_hops) != len(current_hops):
            changed = True
            change_details.append(f"Path length changed: {len(baseline_hops)} -> {len(current_hops)} hops")

        return PathComparison(
            destination=destination,
            baseline_hops=baseline_hops,
            current_hops=current_hops,
            changed=changed,
            change_details=change_details,
        )

    def get_traceroute_history(
        self,
        destination: str | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get traceroute history from diagnostic sessions."""
        if until is None:
            until = time.time()
        if since is None:
            since = until - 86400  # 24h default

        session_repo, result_repo = self._get_repos()
        sessions = session_repo.list_sessions(status="completed", limit=limit)

        traceroutes = []
        for session in sessions:
            if session.diagnostic_type == "traceroute" and session.started_at >= since and session.started_at <= until:
                if destination and session.target != destination:
                    continue
                results = result_repo.get_by_session(session.id)
                hops = []
                for r in results:
                    if r.result_type == "hop":
                        try:
                            hops.append(json.loads(r.payload_json))
                        except Exception:
                            pass
                if hops:
                    traceroutes.append({
                        "timestamp": session.started_at,
                        "session_id": session.id,
                        "destination": session.target,
                        "hops": hops,
                        "hop_count": len(hops),
                        "max_rtt_ms": max((h.get("rtt_ms") or 0 for h in hops), default=0),
                    })

        return sorted(traceroutes, key=lambda x: x["timestamp"], reverse=True)