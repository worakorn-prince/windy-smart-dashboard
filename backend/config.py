"""Central configuration for the Dashboard backend."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

GEOIP_CACHE_FILE = CACHE_DIR / "geoip.json"
TOR_CACHE_FILE = CACHE_DIR / "tor_exits.json"
AUDIT_DIR = CACHE_DIR / "reports"
AUDIT_DIR.mkdir(exist_ok=True)

# Bind host: localhost only. Override with env if needed.
HOST = os.environ.get("DASH_HOST", "127.0.0.1")
PORT = int(os.environ.get("DASH_PORT", "8000"))

# WebSocket push interval (seconds) for metrics.
METRICS_INTERVAL = float(os.environ.get("DASH_METRICS_INTERVAL", "1.0"))
PROCESS_INTERVAL = float(os.environ.get("DASH_PROCESS_INTERVAL", "3.0"))
UPTIME_INTERVAL = float(os.environ.get("DASH_UPTIME_INTERVAL", "5.0"))

# Security monitor polling intervals (seconds).
SECURITY_PORTS_INTERVAL = 5.0
SECURITY_CONNECTIONS_INTERVAL = 5.0
SECURITY_FAILED_LOGINS_INTERVAL = 30.0
SECURITY_DEFENDER_INTERVAL = 60.0

# geoIP
GEOIP_ENDPOINT = "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,isp,org,as,query"
GEOIP_CACHE_TTL = 600  # 10 minutes per IP
GEOIP_RATE_PER_MIN = 40  # ip-api.com free tier limit (45) — keep under
GEOIP_USER_AGENT = "WindySmartDashboard/1.0"

# Ping target for live latency check.
PING_TARGET = os.environ.get("DASH_PING_TARGET", "1.1.1.1")

# Suspicious country codes (ISO-3166 alpha-2). Editable via settings UI.
DEFAULT_SUSPICIOUS_COUNTRIES: list[str] = ["RU", "CN", "KP", "IR", "BY", "TR", "UA"]

# Tor exit list (refreshed daily).
TOR_EXIT_LIST_URL = "https://check.torproject.org/torbulkexitlist"
TOR_REFRESH_INTERVAL = 86400  # 24h

# Frontend distribution served by FastAPI in production.
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

# System-critical PIDs that we refuse to kill (cannot kill 0 / 4 on Windows).
PROTECTED_PIDS = {0, 4}

# Metrics history (SQLite, WAL).
HISTORY_DB = CACHE_DIR / "history.db"
HISTORY_SAMPLE_INTERVAL = float(os.environ.get("DASH_HISTORY_INTERVAL", "10.0"))
HISTORY_RETENTION_HOURS = int(os.environ.get("DASH_HISTORY_RETENTION", "24"))
HISTORY_MAX_POINTS = int(os.environ.get("DASH_HISTORY_MAX_POINTS", "360"))

# Alerts (evaluated on every history sample).
ALERTS_ENABLED = os.environ.get("DASH_ALERTS", "1") != "0"
ALERT_CPU_TEMP = float(os.environ.get("DASH_ALERT_CPU_TEMP", "85"))
ALERT_GPU_TEMP = float(os.environ.get("DASH_ALERT_GPU_TEMP", "85"))
ALERT_RAM_PCT = float(os.environ.get("DASH_ALERT_RAM_PCT", "95"))
ALERT_DISK_PCT = float(os.environ.get("DASH_ALERT_DISK_PCT", "90"))
ALERT_SUSTAINED_SAMPLES = int(os.environ.get("DASH_ALERT_SUSTAINED", "3"))
ALERT_COOLDOWN_SEC = int(os.environ.get("DASH_ALERT_COOLDOWN", "300"))
