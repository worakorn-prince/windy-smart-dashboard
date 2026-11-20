"""Internet Insights — Network intelligence package."""

from .config import InternetInsightsConfig, load_config
from .router import router

__all__ = [
    "InternetInsightsConfig",
    "load_config",
    "router",
]
