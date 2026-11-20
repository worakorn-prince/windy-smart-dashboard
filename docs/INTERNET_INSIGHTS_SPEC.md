# Internet Insights — Feature Specification

**Version:** 1.0  
**Target:** Windy Smart Dashboard v0.7.0+  
**Based on:** INTERNET_INSIGHTS.md §2–§10, §12–§16, §19

---

## 1. Integration Adapters (Reuse Map)

Per INTERNET_INSIGHTS.md §2 and Integration Rules, all existing capabilities are reused through **explicit adapters**. No duplicate collectors.

| # | Existing Capability | Current Implementation | Adapter | Reuse Decision |
|---|---------------------|------------------------|---------|----------------|
| 1 | Network traffic | `metrics.network_snapshot()` | `MetricsAdapter` | Reuse |
| 2 | Adapter information | `metrics._get_adapter_details()` | `MetricsAdapter` | Reuse and enrich |
| 3 | Wi-Fi information | `metrics._get_wifi_info()` | `MetricsAdapter` | Reuse and enrich |
| 4 | Public IP | `metrics._get_public_ip()` | `MetricsAdapter` | Reuse |
| 5 | Live throughput | `/ws/metrics` | `WSMetricsAdapter` (read-only) | Reuse |
| 6 | Ping target | `main._quick_ping()` | `PingAdapter` | Reuse and improve history |
| 7 | Speed test | `speedtest_worker.run_speedtest_async()` | `SpeedtestAdapter` | Reuse |
| 8 | Active connections | `main._net_connection_rows()` | `NetCacheAdapter` | Reuse |
| 9 | Process-to-port | `main._process_net_info()` | `ProcessPortAdapter` | Reuse |
| 10 | Security connections | `security.monitor.SecurityMonitor` | `SecurityAdapter` (read-only) | Reuse |
| 11 | Metrics history | `history.query_range()` | `HistoryAdapter` (read-only) | Preserve ownership |
| 12 | General Insights | `/api/insights` | — | Do not duplicate |
| 13 | General anomaly engine | `insights.compute_anomalies()` | — | Reuse design principles |

### Adapter Implementation Contract

```python
# backend/internet_insights/adapters/__init__.py

class MetricsAdapter:
    """Wrap metrics.py network functions — read-only, no side effects."""
    def get_network_snapshot(self) -> dict: ...
    def get_adapter_details(self) -> list[dict]: ...
    def get_wifi_info(self) -> dict | None: ...
    def get_public_ip(self) -> str | None: ...

class PingAdapter:
    """Wrap main._quick_ping() — same target, timeout, method."""
    async def ping(self, host: str = config.PING_TARGET, timeout: float = 1.0) -> float | None: ...

class SpeedtestAdapter:
    """Wrap speedtest_worker.run_speedtest_async() — identical behavior."""
    async def run(self) -> dict: ...

class NetCacheAdapter:
    """Read main._net_connection_rows() — 5s TTL cache, read-only."""
    def get_connections(self) -> list[dict]: ...

class ProcessPortAdapter:
    """Read main._process_net_info(pid) — process-to-port join."""
    def get_ports_and_connections(self, pid: int) -> tuple[list[dict], int]: ...

class SecurityAdapter:
    """Read security events — subscribe to SecurityMonitor events, no control."""
    def get_recent_events(self, limit: int = 50) -> list[dict]: ...
    def subscribe(self, callback: Callable[[Event], None]) -> None: ...

class HistoryAdapter:
    """Read history.query_range() — read-only access to legacy samples."""
    def query(self, range_str: str) -> dict: ...

class WSMetricsAdapter:
    """Subscribe to /ws/metrics broadcasts — read live ping, throughput."""
    def subscribe(self, callback: Callable[[dict], None]) -> None: ...
```

**Rules:**
- Adapters are **stateless** (no internal caching beyond what wrapped module provides).
- Adapters **never write** to wrapped modules.
- Collectors/analyzers **import only adapters**, never legacy modules directly.
- Adapters live in `backend/internet_insights/adapters/`.

---

## 2. Collector Interfaces

### 2.1 Base Collector Protocol

```python
# backend/internet_insights/collectors/__init__.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class CollectorConfig:
    interval_sec: float
    timeout_sec: float = 30.0
    enabled: bool = True
    max_concurrent_runs: int = 1

class Collector(ABC):
    def __init__(self, config: CollectorConfig, repository: "Repository"):
        self.config = config
        self.repository = repository
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_start: float | None = None
        self._last_run_duration: float | None = None
        self._consecutive_failures = 0

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def collect(self) -> Any: ...

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run_loop(self) -> None:
        while self._running:
            if not self.config.enabled:
                await asyncio.sleep(self.config.interval_sec)
                continue
            start = time.monotonic()
            try:
                await asyncio.wait_for(self.collect(), timeout=self.config.timeout_sec)
                self._consecutive_failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning("Collector %s failed (%d): %s", self.name, self._consecutive_failures, e)
            finally:
                self._last_run_duration = time.monotonic() - start
            await asyncio.sleep(max(0.1, self.config.interval_sec - self._last_run_duration))

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "running": self._running,
            "interval_sec": self.config.interval_sec,
            "last_run_duration_sec": self._last_run_duration,
            "consecutive_failures": self._consecutive_failures,
        }
```

### 2.2 Background Collectors (Hybrid Collection)

| Collector | Interval | Purpose | Adapter Dependencies |
|-----------|----------|---------|---------------------|
| `QualityCollector` | 5s (gateway), 5s (primary), 15s (secondary) | Latency, jitter, loss probes | `PingAdapter` |
| `InterfaceCollector` | 10s | Per-interface traffic, errors, discards | `MetricsAdapter` |
| `TcpStatsCollector` | 15s | Global TCP statistics (retransmits, opens) | `PlatformWindowsAdapter` (GetTcpStatisticsEx) |
| `DnsProbeCollector` | 60s | Controlled DNS resolver probes | `DnsAdapter` (new, uses `DnsQuery_W`) |
| `WifiCollector` | 30s | Signal, channel, association state | `MetricsAdapter` (enriched) |
| `RouteCollector` | 5min + change detection | Route table, default gateway | `RouteAdapter` (new, GetIpForwardTable2) |
| `ConnectionCollector` | 5s (reuse cache) | Active connections, process mapping | `NetCacheAdapter`, `ProcessPortAdapter` |

**Collector Rules:**
- Do not start new collection if previous run still executing (single-flight per collector).
- Bounded queues, timeouts, cancellation, backpressure.
- Probe targets configurable (default: gateway, 1.1.1.1, 8.8.8.8).
- Use small payloads; limit simultaneous requests.
- Record timeout separately from packet loss.
- Use monotonic time for elapsed; UTC Unix timestamps for storage.
- No collector blocks FastAPI event loop — use `asyncio.to_thread()` for blocking ops.

### 2.3 On-Demand Collectors (Diagnostics)

| Diagnostic | Trigger | Timeout | Max Duration | Cancellation |
|------------|---------|---------|--------------|--------------|
| Traceroute | `POST /diagnostics/traceroute` | 30s | 60s | Yes |
| DNS Lookup | `POST /diagnostics/dns` | 10s | 15s | Yes |
| DNS Comparison | `POST /diagnostics/dns` (multi-resolver) | 20s | 30s | Yes |
| TCP Connect | `POST /diagnostics/tcp` | 10s | 15s | Yes |
| TLS Handshake | `POST /diagnostics/tls` | 15s | 20s | Yes |
| HTTP Diagnostics | `POST /diagnostics/http` | 30s | 45s | Yes |
| MTU Discovery | `POST /diagnostics/mtu` | 20s | 30s | Yes |
| Full Session | `POST /sessions` | 120s | 180s | Yes |

Each operation returns structured output with clear error states.

### 2.4 Collector Manager

```python
# backend/internet_insights/services/collector_manager.py

class CollectorManager:
    def __init__(self, repositories: dict[str, "Repository"]):
        self.collectors: dict[str, Collector] = {}
        self.repositories = repositories
        self._config = load_collector_config()

    async def start_all(self) -> None:
        for name, collector in self.collectors.items():
            await collector.start()

    async def stop_all(self) -> None:
        for collector in self.collectors.values():
            await collector.stop()

    def get_status(self) -> dict[str, Any]:
        return {name: c.get_status() for name, c in self.collectors.items()}

    def get_collector(self, name: str) -> Collector | None:
        return self.collectors.get(name)
```

---

## 3. Service Boundaries

### 3.1 Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (router.py)                  │
│  REST endpoints + WebSocket handler                         │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                    Services Layer                            │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │CollectorMgr  │ │DiagnosticsMgr│ │  SessionManager    │  │
│  └──────────────┘ └──────────────┘ └────────────────────┘  │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ IncidentMgr  │ │  Analyzers   │ │  Repositories      │  │
│  └──────────────┘ └──────────────┘ └────────────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                    Adapters Layer                            │
│  MetricsAdapter │ PingAdapter │ SpeedtestAdapter │ ...       │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                    Legacy Modules (Read-Only)                │
│  metrics.py │ main.py │ speedtest_worker.py │ history.py    │
│  security.monitor │ process_history │ disk_health           │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Service Responsibilities

| Service | Responsibility | Owns |
|---------|----------------|------|
| `CollectorManager` | Lifecycle, scheduling, health of background collectors | Collector configs, status |
| `DiagnosticsManager` | Execute on-demand diagnostics, enforce timeouts/cancellation | Running diagnostic tasks |
| `SessionManager` | Troubleshooting session orchestration, progress, results | Session state, result aggregation |
| `IncidentManager` | Incident lifecycle (create, update, resolve, evidence) | Incident DB, correlation rules |
| `AnalyzerEngine` | Run baseline, anomaly, correlation, recommendation analyzers | Analyzer versions, configs |
| `Repository` (per table) | SQL operations only — no business logic | Prepared statements, batch inserts |

### 3.3 Dependency Rules (Enforced by Architecture)

```
✓ Collector → Repository (write)
✓ Service → Collector (control)
✓ Service → Repository (read/write)
✓ Analyzer → Repository (read)
✓ API → Service (call)
✓ Adapter → Legacy Module (read-only)

✗ Collector → Legacy Module (direct import)
✗ Collector → Service (circular)
✗ Repository → Service (circular)
✗ Analyzer → Windows API (direct ctypes)
✗ API → Legacy Module (direct import)
✗ API → Collector (direct control)
```

---

## 4. Platform Windows Adapter

For Windows-native APIs needed beyond psutil:

```python
# backend/internet_insights/adapters/platform_windows.py

class PlatformWindowsAdapter:
    """Thin ctypes wrapper for Windows IP Helper APIs."""
    
    def get_tcp_statistics(self) -> dict[str, int] | None:
        """GetTcpStatisticsEx — global TCP counters."""
        ...
    
    def get_extended_tcp_table(self, order: bool = True) -> list[dict] | None:
        """GetExtendedTcpTable — per-connection TCP endpoints."""
        ...
    
    def get_extended_udp_table(self) -> list[dict] | None:
        """GetExtendedUdpTable — UDP endpoints."""
        ...
    
    def get_ip_forward_table2(self) -> list[dict] | None:
        """GetIpForwardTable2 — IPv4/IPv6 route table."""
        ...
    
    def get_best_route2(self, dest_ip: str) -> dict | None:
        """GetBestRoute2 — route selection for destination."""
        ...
    
    def get_if_table2(self) -> list[dict] | None:
        """GetIfTable2 — detailed interface counters (errors, discards)."""
        ...
    
    def wlan_query_interface(self, guid: str) -> dict | None:
        """WlanQueryInterface — Wi-Fi signal, channel, auth, cipher."""
        ...
    
    def dns_query_w(self, name: str, record_type: int, server: str | None = None) -> dict | None:
        """DnsQuery_W — direct DNS query bypassing system resolver."""
        ...
```

**Rules:**
- All ctypes declarations **encapsulated here** — not spread in business logic.
- Typed structures, buffer-size retry, error-code mapping, memory cleanup.
- Graceful degradation: return `None` on unsupported Windows version/API.
- Unit tests for every parser (mock Windows API responses).

---

## 5. Analyzer Interfaces

```python
# backend/internet_insights/analyzers/__init__.py

@dataclass
class AnalyzerResult:
    incidents: list[IncidentDraft]  # New incidents to create
    updates: list[IncidentUpdate]   # Existing incidents to update
    evidence: list[EvidenceDraft]   # Evidence to attach

class Analyzer(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def version(self) -> str: ...
    
    @abstractmethod
    async def analyze(self, repository: "AnalyzerRepository") -> AnalyzerResult: ...

# Analyzers (deterministic, statistical — no LLM):
# - QualityAnalyzer: latency/jitter/loss baselines + anomaly rules
# - DnsAnalyzer: resolver degradation, timeout patterns
# - GatewayAnalyzer: reachability loss, flap detection
# - InterfaceAnalyzer: error/discard rate increase
# - TcpAnalyzer: retransmission rate spikes
# - RouteAnalyzer: route changes, gateway shifts
# - CorrelationAnalyzer: multi-signal correlation (gateway OK + multi-target latency ↑ = upstream)
# - RecommendationAnalyzer: evidence-based next actions
```

**Analyzer Rules:**
- Operate on **normalized observations** from repositories.
- No direct Windows API calls.
- Minimum sample counts, thresholds, durations, cooldowns configurable.
- Every rule defines: inputs, min samples, threshold, duration, cooldown, recovery, confidence, version.
- Hypotheses ≠ confirmed root causes.

---

## 6. Configuration

```python
# backend/internet_insights/config.py

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
```

Loaded from `config.yaml` with environment variable overrides (`INTERNET_INSIGHTS_*`).

---

## 7. Security & Privacy Boundaries

| Requirement | Implementation |
|-------------|----------------|
| Localhost-only binding | Reuse existing `config.HOST = "127.0.0.1"` |
| WebSocket Origin validation | Same as `/ws/metrics` — check `Origin` header |
| Diagnostic target validation | Reject private IPs, localhost, file://, ftp:// schemes |
| No arbitrary command execution | No `shell=True`, no PowerShell concat — use `subprocess` arg arrays |
| Strict timeouts | All diagnostics bounded by `max_diagnostic_duration_sec` |
| Limit diagnostic concurrency | `diagnostic_concurrency` (default 2) |
| Limit response size | JSON payloads capped at 64 KB |
| No sensitive payload storage | Redact credentials, tokens, auth headers in diagnostic results |
| No packet payloads | MVP stores only metadata, never packet data |
| Deep capture opt-in | Future ETW/Npcap requires explicit confirmation |

---

## 8. Performance Targets

| Metric | Target |
|--------|--------|
| Background CPU overhead | < 2% average on reference system |
| Idle memory overhead | < 100 MB incremental |
| Probe bandwidth (excl. speed test) | < 100 KB/min |
| API overview response (warm cache) | < 300 ms |
| UI initial render (after API) | < 2 seconds |
| Background queue | Bounded (max 100 pending per collector) |
| Diagnostic concurrency | Configurable, default 2 |
| Collector failure isolation | Must not crash backend |

---

## 9. Implementation Phases (from INTERNET_INSIGHTS.md §19)

| Phase | Milestone | Key Deliverables |
|-------|-----------|------------------|
| **M0** | Audit & Contract | **This spec + 3 other docs** — no code changes |
| **M1** | Collector & Storage | `internet_insights` package, DB, migrations, collector lifecycle, REST overview/history, frontend route/store |
| **M2** | Overview & Performance | Quality collectors, latency/jitter/loss, historical charts, quality status |
| **M3** | DNS & Routing | DNS probes, resolver comparison, route snapshot, traceroute |
| **M4** | Developer Diagnostics | TCP/TLS/HTTP/MTU diagnostics, session manager, cancellation, export |
| **M5** | Intelligence | Baseline, anomaly rules, incident lifecycle, evidence, correlation, recommendations |
| **M6** | Release | Full test suite, migration tests, profiling, security review, docs |

---

## 10. Acceptance Criteria (M0 — This Document)

- [ ] All 24 existing integration points identified and mapped to adapters.
- [ ] No duplicate collector proposed.
- [ ] No breaking change to existing endpoints.
- [ ] API contract defined with request/response models.
- [ ] Data model: 9 tables, indexes, retention, migration version table.
- [ ] Migration plan: version table, upgrade path, rollback procedure.
- [ ] Feature spec: adapters, collector interfaces, service boundaries, platform adapter.
- [ ] All integration rules from INTERNET_INSIGHTS.md §2 respected.

---

## 11. Appendix: Integration Point Details

### 11.1 `metrics.network_snapshot()` → `MetricsAdapter.get_network_snapshot()`

**Return Structure:**
```python
{
    "interfaces": {"Ethernet0": ["192.168.1.50"], "Wi-Fi": ["192.168.1.51"]},
    "bytes_sent": 1234567890,
    "bytes_recv": 9876543210,
    "packets_sent": 123456,
    "packets_recv": 987654,
    "send_bytes_per_sec": 1250000,
    "recv_bytes_per_sec": 5200000,
    "adapters": [...],  # from _get_adapter_details()
    "wifi": {...},      # from _get_wifi_info()
    "public_ip": "203.0.113.42"  # from _get_public_ip()
}
```

**Interval:** Called by `_metrics_loop()` every 1s (light) and `METRICS_FULL_INTERVAL` (full).

### 11.2 `main._quick_ping()` → `PingAdapter.ping()`

**Implementation:**
```python
async def _quick_ping(host: str, timeout: float = 1.0) -> float | None:
    # TCP connect to port 80, measure connect latency
    # Returns RTT in ms (even on connection refused)
    # None on DNS failure or timeout
```

**Current Use:** Runs every 5s in `_metrics_loop()`, broadcast on `/ws/metrics` as `{"ping": {"target": PING_TARGET, "latency_ms": 18.4}}`.

**Integration:** `PingAdapter` exposes same function; `QualityCollector` uses it for gateway/primary/secondary targets.

### 11.3 `speedtest_worker.run_speedtest_async()` → `SpeedtestAdapter.run()`

**Response Structure:**
```python
{
    "ok": True,
    "ping_ms": 12.3,
    "download_mbps": 450.2,
    "upload_mbps": 210.5,
    "download_bps": 56275000,
    "upload_bps": 26312500,
    "server": {"name": "Cloudflare", "sponsor": "Cloudflare, Inc.", "country": "Cloudflare Edge", "loc": "LAX"},
    "bytes_downloaded": 26214400,
    "bytes_uploaded": 10485760,
    "timestamp": 1795000000.0,
    "duration_ms": 25000
}
```

**Constants:** `DOWN_BYTES=25MB`, `UP_BYTES=10MB`, `TIMEOUT=60s`, `LATENCY_PROBES=5`.

### 11.4 `history.py` → `HistoryAdapter`

**Owned by `history.py`:**
- `samples` table (schema v3): 14 columns, ts PK
- `schema_version` table
- `_conn`, `_lock`, `_prev_lock` (private)
- Retention: 30 days (env `DASH_HISTORY_DAYS`)
- Query ranges: `5m`, `1h`, `6h`, `24h`

**Internet Insights Access:** Read-only via `history.query_range(range_str)`.

### 11.5 `main._net_connection_rows()` → `NetCacheAdapter`

**Cache:** `_net_cache` (5s TTL), `_net_cache_lock`.

**Return:** `list[dict]` with `pid`, `status`, `laddr` ([ip, port]), `type`.

**Used by:** `_process_net_info(pid)` for process drilldown ports/connections.

### 11.6 `security.monitor.SecurityMonitor` → `SecurityAdapter`

**Events emitted:** `port_opened`, `port_closed`, `outbound_connection`, `suspicious_outbound`, `tor_outbound`, `failed_login`, `defender_disabled`, `defender_enabled`.

**GeoIP:** Cached lookups for outbound connections.

**Internet Insights Access:** Subscribe to events (read-only); do not control monitor.

### 11.7 `main.ConnectionManager` → `WSMetricsAdapter`

**Channels:** `metrics`, `security`.

**Broadcast:** `manager.broadcast(channel, message)`.

**Internet Insights Access:** Subscribe to `metrics` channel for live ping/throughput; separate `/ws/internet` channel for Internet Insights WS.