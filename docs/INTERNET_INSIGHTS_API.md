# Internet Insights — API Contract

**Version:** 1.0  
**Target:** Windy Smart Dashboard v0.7.0+  
**Prefix:** `/api/internet`  
**WebSocket:** `/ws/internet`

---

## 1. REST Endpoints

### 1.1 Read Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/overview` | Summary and current health |
| GET | `/quality` | Current latency, jitter, packet loss |
| GET | `/quality/history` | Historical quality samples |
| GET | `/interfaces` | Interface information |
| GET | `/interfaces/{id}/history` | Per-interface history |
| GET | `/dns` | DNS configuration and health |
| GET | `/dns/history` | DNS probe history |
| GET | `/routes` | Current route table |
| GET | `/connections` | Active connections with normalized filters |
| GET | `/tcp/stats` | Global TCP statistics |
| GET | `/incidents` | Network incidents list |
| GET | `/incidents/{id}` | Incident detail and evidence |

### 1.2 Diagnostic Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/diagnostics/ping` | Ping test |
| POST | `/diagnostics/dns` | DNS lookup |
| POST | `/diagnostics/traceroute` | Route tracing |
| POST | `/diagnostics/tcp` | TCP connect test |
| POST | `/diagnostics/tls` | TLS handshake test |
| POST | `/diagnostics/http` | HTTP diagnostics |
| POST | `/diagnostics/mtu` | MTU discovery |
| POST | `/sessions` | Start troubleshooting session |
| GET | `/sessions/{id}` | Session status and summary |
| GET | `/sessions/{id}/results` | Session results |
| POST | `/sessions/{id}/cancel` | Cancel running session |
| GET | `/sessions/{id}/export` | Export report (JSON/CSV/MD) |

### 1.3 Existing Endpoint Compatibility (Must Not Change)

- `POST /api/speedtest` — Cloudflare speed test (reuse `speedtest_worker.py`)
- `GET /api/insights` — General insights overview (do not duplicate)
- `GET /api/processes/{pid}` — Process drilldown with ports
- `GET /api/processes/{pid}/history` — Per-process CPU/RAM history
- `WS /ws/metrics` — Live metrics push (1 Hz)
- `WS /ws/security` — Live security events

---

## 2. Request/Response Models

### 2.1 Common Response Metadata

All responses include:

```json
{
  "generated_at": 1795000000.123,
  "data_window": {"start": 1794990000.0, "end": 1795000000.0},
  "source": "collector|cache|live",
  "status": "ok|partial|unavailable",
  "errors": [],
  "coverage": 0.95
}
```

- **Never return misleading zero values** for unavailable metrics — use `null` or explicit `unavailable` status.
- `coverage`: fraction of expected samples present (0.0–1.0).

### 2.2 Validation Rules

| Parameter | Constraint |
|-----------|------------|
| `range` (time window) | Max 30 days; enum: `5m`, `1h`, `6h`, `24h`, `7d`, `30d` |
| `limit` (result count) | Max 1000 |
| `target` (hostname/IP) | Max 255 chars; valid hostname or IP |
| `protocol` | Enum: `icmp`, `tcp`, `udp` |
| `diagnostic duration` | Max 120 seconds |
| `hop_limit` (traceroute) | Max 30 |
| `request body size` | Max 64 KB |

### 2.3 Key Response Models

#### Overview (`GET /overview`)

```json
{
  "connection_status": "connected|degraded|disconnected",
  "internet_quality": {
    "primary": {"target_id": "primary", "latency_ms": 18.4, "jitter_ms": 2.1, "loss_pct": 0.0, "status": "success"},
    "secondary": {"target_id": "secondary", "latency_ms": 22.1, "jitter_ms": 3.5, "loss_pct": 0.0, "status": "success"},
    "gateway": {"target_id": "gateway", "latency_ms": 1.2, "jitter_ms": 0.3, "loss_pct": 0.0, "status": "success"}
  },
  "current_throughput": {"send_bps": 1250000, "recv_bps": 5200000, "interface_id": "Ethernet0"},
  "active_interface": {"id": "Ethernet0", "name": "Intel I219-V", "status": "Connected", "speed_mbps": 1000},
  "recent_incidents": [
    {"id": "inc_abc123", "started_at": 1794995000.0, "category": "latency", "severity": "warning", "title": "Sustained latency increase on primary"}
  ],
  "dns_health": {"configured": ["1.1.1.1", "8.8.8.8"], "primary_status": "ok", "secondary_status": "ok"}
}
```

#### Quality (`GET /quality`)

```json
{
  "targets": [
    {
      "target_id": "primary",
      "address": "1.1.1.1",
      "probe_type": "icmp",
      "latency_ms": {"min": 15.2, "median": 18.4, "p95": 24.1, "max": 42.0, "count": 58, "timeouts": 2},
      "jitter_ms": 2.1,
      "loss_pct": 3.4,
      "status": "success",
      "last_probe_at": 1795000000.0
    }
  ]
}
```

#### Interfaces (`GET /interfaces`)

```json
{
  "interfaces": [
    {
      "id": "Ethernet0",
      "name": "Intel I219-V",
      "description": "Intel(R) Ethernet Connection (7) I219-V",
      "mac": "00:11:22:33:44:55",
      "type": "Ethernet 802.3",
      "speed_mbps": 1000,
      "status": "Connected",
      "connection_name": "Ethernet",
      "manufacturer": "Intel Corporation",
      "ipv4": ["192.168.1.50"],
      "ipv6": ["fe80::1234:5678:9abc:def0"],
      "gateway": ["192.168.1.1"],
      "dns": ["1.1.1.1", "8.8.8.8"],
      "current_rates": {"send_bps": 1250000, "recv_bps": 5200000},
      "errors": {"in": 0, "out": 0, "discards_in": 0, "discards_out": 0}
    }
  ]
}
```

#### DNS (`GET /dns`)

```json
{
  "configured_resolvers": [
    {"address": "1.1.1.1", "interface_id": "Ethernet0", "source": "dhcp|static|manual"},
    {"address": "8.8.8.8", "interface_id": "Ethernet0", "source": "dhcp|static|manual"}
  ],
  "probe_results": [
    {"resolver": "1.1.1.1", "hostname": "cloudflare.com", "record_type": "A", "duration_ms": 12.3, "status": "success", "answer_count": 1, "error_code": null}
  ],
  "system_resolver": {"available": true, "duration_ms": 8.1, "status": "success"}
}
```

#### Connections (`GET /connections`)

```json
{
  "connections": [
    {
      "pid": 1234,
      "process_name": "chrome.exe",
      "exe": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "local_ip": "192.168.1.50",
      "local_port": 54321,
      "remote_ip": "142.250.190.46",
      "remote_port": 443,
      "protocol": "tcp",
      "state": "ESTABLISHED",
      "first_seen": 1794998000.0,
      "last_seen": 1795000000.0,
      "interface_id": "Ethernet0",
      "bytes_sent": 102400,
      "bytes_recv": 204800
    }
  ],
  "filters_applied": {"protocol": "tcp", "state": "ESTABLISHED"}
}
```

#### TCP Stats (`GET /tcp/stats`)

```json
{
  "ts": 1795000000.0,
  "source": "GetTcpStatisticsEx|psutil_fallback",
  "active_opens": 1250,
  "passive_opens": 890,
  "failed_attempts": 12,
  "established_resets": 5,
  "current_established": 42,
  "segments_sent": 1500000,
  "segments_received": 1450000,
  "segments_retransmitted": 3400,
  "retransmission_rate_pct": 0.23
}
```

#### Incidents (`GET /incidents`)

```json
{
  "incidents": [
    {
      "id": "inc_abc123",
      "started_at": 1794995000.0,
      "ended_at": 1794996000.0,
      "category": "latency",
      "severity": "warning",
      "status": "resolved",
      "title": "Sustained latency increase on primary",
      "summary": "Median latency rose from 18ms to 85ms for 10 minutes",
      "confidence": 0.82,
      "analyzer_version": "1.0.0"
    }
  ]
}
```

#### Diagnostic Request/Response (Example: Ping)

**Request:** `POST /diagnostics/ping`

```json
{
  "target": "1.1.1.1",
  "count": 10,
  "interval_ms": 1000,
  "timeout_ms": 2000,
  "protocol": "icmp"
}
```

**Response:**

```json
{
  "id": "diag_ping_xyz789",
  "target": "1.1.1.1",
  "protocol": "icmp",
  "sent": 10,
  "received": 9,
  "loss_pct": 10.0,
  "rtt_ms": {"min": 14.2, "median": 17.8, "p95": 23.1, "max": 28.5},
  "jitter_ms": 1.9,
  "errors": [{"seq": 5, "error": "timeout"}],
  "duration_ms": 10250,
  "status": "completed"
}
```

#### Session (`POST /sessions`)

**Request:**

```json
{
  "profile": "standard",  // "quick" (30s) | "standard" (60s) | "deep" (120s)
  "include_speedtest": false,
  "custom_targets": ["example.com", "8.8.8.8"]
}
```

**Response:**

```json
{
  "id": "sess_abc123",
  "started_at": 1795000000.0,
  "status": "running",
  "profile": "standard",
  "config": {"include_speedtest": false, "custom_targets": ["example.com", "8.8.8.8"]}
}
```

---

## 3. WebSocket Contract

### 3.1 Endpoint

```
WS /ws/internet
```

### 3.2 Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `internet_status` | Server → Client | Overall connectivity state change |
| `quality_sample` | Server → Client | New latency/jitter/loss measurement |
| `interface_change` | Server → Client | Interface up/down, config change |
| `dns_status` | Server → Client | DNS resolver health change |
| `incident_created` | Server → Client | New incident detected |
| `incident_updated` | Server → Client | Incident status/severity change |
| `diagnostic_progress` | Server → Client | Running diagnostic progress |
| `diagnostic_completed` | Server → Client | Diagnostic finished with results |
| `collector_status` | Server → Client | Collector start/stop/error |

### 3.3 Message Examples

**Quality Sample:**

```json
{
  "type": "quality_sample",
  "ts": 1795000000.123,
  "target_id": "primary",
  "probe_type": "icmp",
  "rtt_ms": 18.4,
  "status": "success",
  "jitter_ms": 2.1,
  "loss_pct": 0.0
}
```

**Incident Created:**

```json
{
  "type": "incident_created",
  "ts": 1795000000.123,
  "incident": {
    "id": "inc_abc123",
    "started_at": 1795000000.0,
    "category": "latency",
    "severity": "warning",
    "status": "active",
    "title": "Sustained latency increase on primary",
    "confidence": 0.82
  }
}
```

**Diagnostic Progress:**

```json
{
  "type": "diagnostic_progress",
  "ts": 1795000000.123,
  "session_id": "sess_abc123",
  "diagnostic_type": "traceroute",
  "progress_pct": 45,
  "current_hop": 7,
  "message": "Probing hop 7..."
}
```

### 3.4 Rules

- No raw high-frequency event flood — broadcast only meaningful updates.
- Batch where appropriate (e.g., multiple quality samples in 1 message).
- Remove disconnected clients immediately.
- Bound outgoing queues (max 100 pending messages per client).
- Do not block collectors while sending WebSocket messages (use `asyncio.create_task`).
- Separate channel from `/ws/metrics` to avoid traffic collision.

---

## 4. Error Responses

All errors follow RFC 7807 Problem Details:

```json
{
  "type": "https://windy-dashboard.local/errors/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "Invalid target: must be a valid hostname or IP address",
  "instance": "/api/internet/diagnostics/ping",
  "errors": [
    {"field": "target", "message": "must be a valid hostname or IP address"}
  ]
}
```

| HTTP Status | Use Case |
|-------------|----------|
| 400 | Invalid request body (malformed JSON) |
| 422 | Validation failed (field constraints) |
| 404 | Resource not found (session, incident) |
| 409 | Conflict (session already running) |
| 500 | Internal collector/storage error |
| 503 | Service unavailable (collector not started) |
| 504 | Diagnostic timeout |

---

## 5. Integration Notes

### 5.1 Reused Existing Endpoints

| Capability | Current Endpoint | Reuse Strategy |
|------------|------------------|----------------|
| Speed Test | `POST /api/speedtest` | Direct proxy; broadcast result on `/ws/metrics` as `speedtest_result` |
| Live Ping | `/ws/metrics` (ping field) | Read from existing WS; enhance history in Internet Insights |
| Network Snapshot | `metrics.network_snapshot()` | Adapter via `InterfaceCollector` |
| Process Connections | `GET /api/processes/{pid}` | Join with Internet Insights connection data |

### 5.2 Adapter Pattern

All existing integrations go through explicit adapters in `backend/internet_insights/adapters/`:

- `MetricsAdapter` → wraps `metrics.network_snapshot()`, `_get_adapter_details()`, `_get_wifi_info()`, `_get_public_ip()`
- `SpeedtestAdapter` → wraps `speedtest_worker.run_speedtest_async()`
- `HistoryAdapter` → reads `history.query_range()` (read-only)
- `SecurityAdapter` → reads `security.monitor.SecurityMonitor` events (read-only)
- `NetCacheAdapter` → reads `main._net_connection_rows()` (read-only)
- `PingAdapter` → wraps `main._quick_ping()`

**No direct imports of legacy modules in collectors/analyzers.**