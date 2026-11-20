"""Integration adapters for reusing existing modules."""

from .metrics_adapter import MetricsAdapter
from .ws_metrics_adapter import WSMetricsAdapter
from .ping_adapter import PingAdapter
from .speedtest_adapter import SpeedtestAdapter
from .net_cache_adapter import NetCacheAdapter
from .history_adapter import HistoryAdapter

__all__ = [
    "HistoryAdapter",
    "MetricsAdapter",
    "NetCacheAdapter",
    "PingAdapter",
    "SpeedtestAdapter",
    "WSMetricsAdapter",
]
