"""Metrics adapter - wraps metrics.py network functions (read-only)."""

from __future__ import annotations

import logging
from typing import Any

import metrics

logger = logging.getLogger("dashboard.internet_insights.adapters.metrics")


class MetricsAdapter:
    """Wrap metrics.py network functions — read-only, no side effects."""

    def get_network_snapshot(self) -> dict[str, Any]:
        """Get full network snapshot including adapters, wifi, public IP."""
        try:
            return metrics.network_snapshot()
        except Exception as e:
            logger.warning("Failed to get network snapshot: %s", e)
            return {
                "interfaces": {},
                "bytes_sent": 0,
                "bytes_recv": 0,
                "packets_sent": 0,
                "packets_recv": 0,
                "send_bytes_per_sec": 0,
                "recv_bytes_per_sec": 0,
                "adapters": [],
                "wifi": None,
                "public_ip": None,
            }

    def get_adapters(self) -> list[dict[str, Any]]:
        """Get detailed adapter information."""
        try:
            return metrics._get_adapter_details()
        except Exception as e:
            logger.warning("Failed to get adapter details: %s", e)
            return []

    def get_wifi(self) -> dict[str, Any] | None:
        """Get WiFi connection info."""
        try:
            return metrics._get_wifi_info()
        except Exception as e:
            logger.warning("Failed to get wifi info: %s", e)
            return None

    def get_public_ip(self) -> str | None:
        """Get public IP address."""
        try:
            return metrics._get_public_ip()
        except Exception as e:
            logger.warning("Failed to get public IP: %s", e)
            return None

    def get_gateways(self) -> list[str]:
        """Extract gateway IPs from adapter details."""
        adapters = self.get_adapters()
        gateways = []
        for adapter in adapters:
            for gw in adapter.get("gateway", []):
                if gw and gw not in gateways:
                    gateways.append(gw)
        return gateways
