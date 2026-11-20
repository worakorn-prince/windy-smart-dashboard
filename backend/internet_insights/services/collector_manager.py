"""Collector Manager - manages lifecycle of background collectors."""

from __future__ import annotations

import logging
from typing import Any

from ..config import get_config
from ..collectors.quality import QualityCollector
from ..collectors.interface import InterfaceCollector
from ..storage.repositories import (
    QualitySampleRepository,
    InterfaceSampleRepository,
)

logger = logging.getLogger("dashboard.internet_insights.services.collector_manager")


class CollectorManager:
    """Manages lifecycle of all background collectors."""

    def __init__(self):
        self.config = get_config()
        self.collectors: dict[str, Any] = {}
        self._repositories: dict[str, Any] = {}
        self._initialized = False

    def _init_repositories(self) -> None:
        """Initialize repositories."""
        self._repositories = {
            "quality": QualitySampleRepository(),
            "interface": InterfaceSampleRepository(),
        }

    def _init_collectors(self) -> None:
        """Initialize collectors with their repositories."""
        self.collectors = {
            "quality": QualityCollector(repository=self._repositories["quality"]),
            "interface": InterfaceCollector(repository=self._repositories["interface"]),
        }

    def initialize(self) -> None:
        """Initialize all collectors and repositories."""
        if self._initialized:
            return
        self._init_repositories()
        self._init_collectors()
        self._initialized = True
        logger.info("CollectorManager initialized with %d collectors", len(self.collectors))

    async def start_all(self) -> None:
        """Start all collectors."""
        if not self._initialized:
            self.initialize()

        for name, collector in self.collectors.items():
            try:
                await collector.start()
                logger.info("Started collector: %s", name)
            except Exception:
                logger.exception("Failed to start collector %s", name)

    async def stop_all(self) -> None:
        """Stop all collectors gracefully."""
        for name, collector in self.collectors.items():
            try:
                await collector.stop()
                logger.info("Stopped collector: %s", name)
            except Exception:
                logger.exception("Error stopping collector %s", name)

    def get_status(self) -> dict[str, Any]:
        """Get status of all collectors."""
        return {name: collector.get_status() for name, collector in self.collectors.items()}

    def get_collector(self, name: str) -> Any | None:
        """Get a specific collector by name."""
        return self.collectors.get(name)

    def get_repository(self, name: str) -> Any | None:
        """Get a specific repository by name."""
        return self._repositories.get(name)


# Global collector manager instance
_collector_manager: CollectorManager | None = None


def get_collector_manager() -> CollectorManager:
    """Get or create the global collector manager instance."""
    global _collector_manager
    if _collector_manager is None:
        _collector_manager = CollectorManager()
    return _collector_manager
