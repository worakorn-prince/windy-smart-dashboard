# Internet Insights — SQLite Data Model

**Version:** 1.0  
**Database File:** `backend/.cache/history.db` (shared with existing history)  
**Migration Version Table:** `internet_insights_schema_version`  
**Current Schema Version:** 1

---

## 1. Design Principles

- **Independent tables** — Do not alter existing `samples` table (owned by `history.py`).
- **Separate connection** — Internet Insights uses its own SQLite connection pool; never access `history._conn` or `history._lock`.
- **WAL mode** — `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000;`
- **Parameterized SQL only** — No string interpolation in queries.
- **Batch inserts** — Use `executemany` for bulk writes.
- **Short transactions** — Commit immediately after each batch.
- **Prepared statements** — Cache `cursor.execute` for hot paths.
- **JSON size limits** — Diagnostic payloads capped at 64 KB; larger payloads truncated with flag.

---

## 2. Tables Overview (7 Tables)

| Table | Purpose | Retention |
|-------|---------|-----------|
| `internet_quality_samples` | Latency, jitter, packet loss per target/probe | 14 days |
| `internet_interface_samples` | Per-interface traffic, errors, discards | 14 days |
| `internet_tcp_stats_samples` | Global TCP statistics (retransmits, opens, resets) | 14 days |
| `internet_dns_probe_samples` | DNS resolver probe results | 14 days |
| `internet_diagnostic_sessions` | Troubleshooting/diagnostic session metadata | 30 days |
| `internet_diagnostic_results` | Individual diagnostic results per session | 30 days |
| `internet_incidents` | Detected network incidents | 90 days |
| `internet_incident_evidence` | Evidence linked to incidents | 90 days |
| `internet_insights_schema_version` | Migration version tracking | Permanent |

---

## 3. Table Schemas

### 3.1 `internet_quality_samples`

Stores raw probe measurements for latency, jitter, packet loss calculation.

```sql
CREATE TABLE internet_quality_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                          -- UTC Unix timestamp (monotonic source)
    target_id TEXT NOT NULL,                   -- 'primary', 'secondary', 'gateway', 'custom:<host>'
    probe_type TEXT NOT NULL,                  -- 'icmp', 'tcp', 'udp', 'http'
    rtt_ms REAL,                               -- Round-trip time in milliseconds (null on failure)
    status TEXT NOT NULL,                      -- 'success', 'timeout', 'unreachable', 'dns_failure', 'error'
    error_code TEXT,                           -- OS error code or custom: 'TIMEOUT', 'HOST_UNREACH', 'DNS_FAIL'
    timeout_ms INTEGER,                        -- Configured probe timeout
    interface_id TEXT,                         -- Interface used for probe (when known)
    CONSTRAINT chk_status CHECK (status IN ('success','timeout','unreachable','dns_failure','error')),
    CONSTRAINT chk_probe_type CHECK (probe_type IN ('icmp','tcp','udp','http'))
);

CREATE INDEX idx_quality_target_ts ON internet_quality_samples (target_id, ts);
CREATE INDEX idx_quality_probe_ts ON internet_quality_samples (probe_type, ts);
CREATE INDEX idx_quality_ts ON internet_quality_samples (ts);
```

**Notes:**
- `target_id` distinguishes independent probe series (do not combine unrelated targets).
- `rtt_ms` is NULL on failure; `status` + `error_code` explain why.
- Counter deltas calculated at collection time, not derived from this table.

### 3.2 `internet_interface_samples`

Per-interface traffic counters and error/discard statistics.

```sql
CREATE TABLE internet_interface_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                          -- UTC Unix timestamp
    interface_id TEXT NOT NULL,                -- e.g., 'Ethernet0', 'Wi-Fi', '\\Device\\NPF_{GUID}'
    bytes_sent INTEGER NOT NULL,               -- Absolute counter (psutil)
    bytes_recv INTEGER NOT NULL,
    send_bps REAL NOT NULL,                    -- Calculated rate (bytes/sec)
    recv_bps REAL NOT NULL,
    packets_sent INTEGER NOT NULL,
    packets_recv INTEGER NOT NULL,
    errors_in INTEGER DEFAULT 0,
    errors_out INTEGER DEFAULT 0,
    discards_in INTEGER DEFAULT 0,
    discards_out INTEGER DEFAULT 0,
    link_status TEXT,                          -- 'up', 'down', 'unknown'
    CONSTRAINT chk_link_status CHECK (link_status IN ('up','down','unknown') OR link_status IS NULL)
);

CREATE INDEX idx_interface_id_ts ON internet_interface_samples (interface_id, ts);
CREATE INDEX idx_interface_ts ON internet_interface_samples (ts);
```

**Notes:**
- Absolute counters (`bytes_sent`, `bytes_recv`) from `psutil.net_io_counters(pernic=True)`.
- Rates (`send_bps`, `recv_bps`) calculated independently by collector using monotonic delta — **do not reuse `metrics._net_rates()` or `history._prev_*` state**.
- Error/discard counters from `psutil.net_io_counters(pernic=True)` where available (Windows: `GetIfEntry2`).

### 3.3 `internet_tcp_stats_samples`

Global TCP stack statistics from Windows IP Helper (`GetTcpStatisticsEx`) or psutil fallback.

```sql
CREATE TABLE internet_tcp_stats_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                          -- UTC Unix timestamp
    active_opens INTEGER NOT NULL,
    passive_opens INTEGER NOT NULL,
    failed_attempts INTEGER NOT NULL,
    established_resets INTEGER NOT NULL,
    current_established INTEGER NOT NULL,
    segments_sent INTEGER NOT NULL,
    segments_received INTEGER NOT NULL,
    segments_retransmitted INTEGER NOT NULL,
    source TEXT NOT NULL,                      -- 'GetTcpStatisticsEx' | 'psutil_fallback' | 'estimated'
    CONSTRAINT chk_source CHECK (source IN ('GetTcpStatisticsEx','psutil_fallback','estimated'))
);

CREATE INDEX idx_tcp_stats_ts ON internet_tcp_stats_samples (ts);
```

**Notes:**
- Counter deltas must be calculated safely (account for counter wrap/reset on reboot).
- `source` field identifies collection method for data quality assessment.
- Per-connection retransmission NOT available from global counters — do not infer.

### 3.4 `internet_dns_probe_samples`

Controlled DNS probe results (not passive DNS monitoring).

```sql
CREATE TABLE internet_dns_probe_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,                          -- UTC Unix timestamp
    resolver TEXT NOT NULL,                    -- Resolver IP used for query
    hostname TEXT NOT NULL,                    -- Queried hostname
    record_type TEXT NOT NULL,                 -- 'A', 'AAAA', 'CNAME', 'TXT', 'MX'
    duration_ms REAL,                          -- Query duration (null on failure)
    status TEXT NOT NULL,                      -- 'success', 'timeout', 'servfail', 'nxdomain', 'refused', 'error'
    answer_count INTEGER DEFAULT 0,
    error_code TEXT,                           -- DNS RCODE or OS error
    probe_method TEXT NOT NULL,                -- 'system_resolver', 'direct_udp', 'direct_tcp', 'doh', 'dot'
    CONSTRAINT chk_dns_status CHECK (status IN ('success','timeout','servfail','nxdomain','refused','error')),
    CONSTRAINT chk_record_type CHECK (record_type IN ('A','AAAA','CNAME','TXT','MX','NS','SOA')),
    CONSTRAINT chk_probe_method CHECK (probe_method IN ('system_resolver','direct_udp','direct_tcp','doh','dot'))
);

CREATE INDEX idx_dns_resolver_ts ON internet_dns_probe_samples (resolver, ts);
CREATE INDEX idx_dns_hostname_ts ON internet_dns_probe_samples (hostname, ts);
CREATE INDEX idx_dns_ts ON internet_dns_probe_samples (ts);
```

**Notes:**
- `probe_method` distinguishes system resolver (OS cache/VPN) vs direct resolver queries.
- Only controlled diagnostic queries persisted by default (privacy).
- Passive DNS collection is opt-in future feature.

### 3.5 `internet_diagnostic_sessions`

Troubleshooting and on-demand diagnostic session metadata.

```sql
CREATE TABLE internet_diagnostic_sessions (
    id TEXT PRIMARY KEY,                       -- UUID v4: 'sess_abc123def456'
    started_at REAL NOT NULL,                  -- UTC Unix timestamp
    completed_at REAL,                         -- Null if running/cancelled
    status TEXT NOT NULL,                      -- 'running', 'completed', 'cancelled', 'failed'
    target TEXT,                               -- Primary target (host/IP)
    diagnostic_type TEXT NOT NULL,             -- 'ping', 'dns', 'traceroute', 'tcp', 'tls', 'http', 'mtu', 'full_session'
    config_json TEXT NOT NULL,                 -- JSON: request parameters
    summary_json TEXT,                         -- JSON: aggregated results (populated on completion)
    error TEXT,                                -- Error message if failed
    CONSTRAINT chk_session_status CHECK (status IN ('running','completed','cancelled','failed')),
    CONSTRAINT chk_diagnostic_type CHECK (diagnostic_type IN ('ping','dns','traceroute','tcp','tls','http','mtu','full_session'))
);

CREATE INDEX idx_session_started ON internet_diagnostic_sessions (started_at);
CREATE INDEX idx_session_status ON internet_diagnostic_sessions (status);
```

**config_json example:**
```json
{
  "profile": "standard",
  "targets": ["1.1.1.1", "8.8.8.8", "example.com"],
  "ping_count": 10,
  "traceroute_max_hops": 30,
  "include_speedtest": false
}
```

**summary_json example:**
```json
{
  "overall_state": "degraded",
  "quality": {"primary": {"median_rtt_ms": 85, "loss_pct": 5.0}},
  "dns": {"1.1.1.1": {"status": "ok", "duration_ms": 12}},
  "route": {"hops": 12, "destination_reached": true},
  "tcp_stats": {"retransmission_rate_pct": 1.2}
}
```

### 3.6 `internet_diagnostic_results`

Individual results within a diagnostic session.

```sql
CREATE TABLE internet_diagnostic_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,                  -- FK to internet_diagnostic_sessions(id)
    ts REAL NOT NULL,                          -- UTC Unix timestamp
    sequence INTEGER NOT NULL,                 -- Order within session
    result_type TEXT NOT NULL,                 -- 'probe', 'hop', 'tcp_connect', 'tls_handshake', 'http_request', 'mtu_probe'
    payload_json TEXT NOT NULL,                -- JSON: structured result (max 64 KB)
    CONSTRAINT chk_result_type CHECK (result_type IN ('probe','hop','tcp_connect','tls_handshake','http_request','mtu_probe'))
);

CREATE INDEX idx_diag_result_session ON internet_diagnostic_results (session_id, sequence);
CREATE INDEX idx_diag_result_ts ON internet_diagnostic_results (ts);

-- Foreign key (enforced by application; SQLite FK optional for performance)
-- FOREIGN KEY (session_id) REFERENCES internet_diagnostic_sessions(id) ON DELETE CASCADE
```

**payload_json examples:**

*Probe (ping):*
```json
{"target": "1.1.1.1", "seq": 5, "rtt_ms": 18.4, "status": "success"}
```

*Hop (traceroute):*
```json
{"hop": 3, "ip": "10.0.1.1", "rtt_ms": [1.2, 1.3, 1.1], "status": "success"}
```

*TCP Connect:*
```json
{"target": "example.com", "port": 443, "duration_ms": 45.2, "status": "success", "local_port": 54321}
```

*TLS Handshake:*
```json
{"target": "example.com", "port": 443, "duration_ms": 120.5, "version": "TLS 1.3", "cipher": "TLS_AES_256_GCM_SHA384", "cert_valid": true, "cert_expiry": "2026-12-01T00:00:00Z", "status": "success"}
```

*HTTP Request:*
```json
{"url": "https://example.com/", "method": "GET", "status_code": 200, "duration_ms": 230.1, "redirect_chain": [], "status": "success"}
```

*MTU Probe:*
```json
{"target": "1.1.1.1", "test_size": 1472, "status": "success", "path_mtu": 1500}
```

### 3.7 `internet_incidents`

Detected network incidents with lifecycle.

```sql
CREATE TABLE internet_incidents (
    id TEXT PRIMARY KEY,                       -- UUID v4: 'inc_abc123def456'
    started_at REAL NOT NULL,                  -- UTC Unix timestamp
    ended_at REAL,                             -- Null if active
    category TEXT NOT NULL,                    -- 'latency', 'loss', 'dns', 'gateway', 'interface', 'tcp', 'route'
    severity TEXT NOT NULL,                    -- 'info', 'warning', 'critical'
    status TEXT NOT NULL,                      -- 'active', 'acknowledged', 'resolved', 'suppressed'
    title TEXT NOT NULL,                       -- Human-readable summary
    summary TEXT,                              -- Detailed description
    confidence REAL NOT NULL,                  -- 0.0–1.0
    analyzer_version TEXT NOT NULL,            -- e.g., '1.0.0'
    CONSTRAINT chk_category CHECK (category IN ('latency','loss','dns','gateway','interface','tcp','route')),
    CONSTRAINT chk_severity CHECK (severity IN ('info','warning','critical')),
    CONSTRAINT chk_status CHECK (status IN ('active','acknowledged','resolved','suppressed')),
    CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_incident_started ON internet_incidents (started_at);
CREATE INDEX idx_incident_category ON internet_incidents (category);
CREATE INDEX idx_incident_status ON internet_incidents (status);
```

**Notes:**
- `confidence` reflects evidence strength, not root-cause certainty.
- Hypotheses are NOT presented as confirmed root causes.
- `analyzer_version` enables rule evolution tracking.

### 3.8 `internet_incident_evidence`

Observations that triggered or support an incident.

```sql
CREATE TABLE internet_incident_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,                 -- FK to internet_incidents(id)
    evidence_type TEXT NOT NULL,               -- 'quality_sample', 'interface_counter', 'dns_probe', 'tcp_stat', 'route_change', 'diagnostic_result'
    observed_at REAL NOT NULL,                 -- UTC Unix timestamp
    payload_json TEXT NOT NULL,                -- JSON: raw observation data
    CONSTRAINT chk_evidence_type CHECK (evidence_type IN ('quality_sample','interface_counter','dns_probe','tcp_stat','route_change','diagnostic_result'))
);

CREATE INDEX idx_evidence_incident ON internet_incident_evidence (incident_id, observed_at);
CREATE INDEX idx_evidence_type ON internet_incident_evidence (evidence_type);

-- FOREIGN KEY (incident_id) REFERENCES internet_incidents(id) ON DELETE CASCADE
```

**payload_json example:**
```json
{"target_id": "primary", "median_rtt_ms": 85.2, "baseline_median_rtt_ms": 18.4, "duration_sec": 600, "samples": 120}
```

### 3.9 `internet_insights_schema_version`

Migration version tracking (independent from `history.schema_version`).

```sql
CREATE TABLE internet_insights_schema_version (
    version INTEGER PRIMARY KEY
);

-- Initial row:
INSERT INTO internet_insights_schema_version (version) VALUES (1);
```

---

## 4. Indexes Summary

| Table | Indexes |
|-------|---------|
| `internet_quality_samples` | `(target_id, ts)`, `(probe_type, ts)`, `(ts)` |
| `internet_interface_samples` | `(interface_id, ts)`, `(ts)` |
| `internet_tcp_stats_samples` | `(ts)` |
| `internet_dns_probe_samples` | `(resolver, ts)`, `(hostname, ts)`, `(ts)` |
| `internet_diagnostic_sessions` | `(started_at)`, `(status)` |
| `internet_diagnostic_results` | `(session_id, sequence)`, `(ts)` |
| `internet_incidents` | `(started_at)`, `(category)`, `(status)` |
| `internet_incident_evidence` | `(incident_id, observed_at)`, `(evidence_type)` |

---

## 5. Retention Policy

| Data | Retention | Prune Strategy |
|------|-----------|----------------|
| Quality samples | 14 days | Daily batch delete `ts < now - 14d` |
| Interface samples | 14 days | Daily batch delete `ts < now - 14d` |
| TCP stats samples | 14 days | Daily batch delete `ts < now - 14d` |
| DNS probe samples | 14 days | Daily batch delete `ts < now - 14d` |
| Diagnostic sessions | 30 days | Daily batch delete `started_at < now - 30d` (cascades to results) |
| Diagnostic results | 30 days | Cascaded via session delete |
| Incidents | 90 days | Daily batch delete `started_at < now - 90d` (cascades to evidence) |
| Incident evidence | 90 days | Cascaded via incident delete |

- Retention configurable via `config.INTERNET_INSIGHTS_RETENTION_DAYS` (dict per table group).
- Aggregate before pruning where long-term trends needed (future: downsampled hourly aggregates).
- Never retain packet payloads in MVP.

---

## 6. Connection Management

```python
# backend/internet_insights/storage/database.py

class InternetInsightsDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        # Thread-local connection for WAL concurrency
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=5.0,
                isolation_level=None  # autocommit mode; explicit transactions
            )
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params_seq: list[tuple]) -> sqlite3.Cursor:
        with self._lock:
            return self._get_conn().executemany(sql, params_seq)

    def commit(self) -> None:
        with self._lock:
            self._get_conn().commit()

    def close(self) -> None:
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
```

- **Separate from `history._conn` and `history._lock`** — no shared state.
- Thread-local connections for WAL read concurrency.
- Write serialization via `_lock` (short critical sections only).

---

## 7. Migration Version Table

- **Table:** `internet_insights_schema_version`
- **Single row:** `version INTEGER PRIMARY KEY`
- **Current version:** 1 (initial schema)
- **Migration logic:** See `INTERNET_INSIGHTS_MIGRATION.md`

---

## 8. Integration with Existing Tables

| Existing Table | Owner | Internet Insights Access |
|----------------|-------|--------------------------|
| `samples` | `history.py` | **Read-only** via `history.query_range()` — never write |
| `schema_version` | `history.py` | **Read-only** — separate version namespace |
| `process_samples` | `process_history.py` | **Read-only** — join for process-to-port mapping |
| `disk_samples` | `disk_health.py` | **Read-only** — correlate disk I/O with network |

**No foreign keys** to existing tables (different ownership, different retention).
Cross-table correlations done at query time in analyzers/services.