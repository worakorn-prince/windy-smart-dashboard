"""Services layer for Internet Insights."""

from .collector_manager import CollectorManager, get_collector_manager

__all__ = [
    "CollectorManager",
    "get_collector_manager",
]
