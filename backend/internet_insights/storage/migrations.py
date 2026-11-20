"""Database migrations for Internet Insights."""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("dashboard.internet_insights.storage.migrations")

# V1 Schema - Initial schema with all 9 tables
V1_SCHEMA_SQL = """
-- internet_quality_samples
CREATE TABLE IF NOT EXISTS internet_quality_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    target_id TEXT NOT NULL,
    probe_type TEXT NOT NULL,
    rtt_ms REAL,
    status TEXT NOT NULL,
    error_code TEXT,
    timeout_ms INTEGER,
    interface_id TEXT,
    CONSTRAINT chk_status CHECK (status IN ('success','timeout','unreachable','dns_failure','error')),
    CONSTRAINT chk_probe_type CHECK (probe_type IN ('icmp','tcp','udp','http'))
);

CREATE INDEX IF NOT EXISTS idx_quality_target_ts ON internet_quality_samples (target_id, ts);
CREATE INDEX IF NOT EXISTS idx_quality_probe_ts ON internet_quality_samples (probe_type, ts);
CREATE INDEX IF NOT EXISTS idx_quality_ts ON internet_quality_samples (ts);

-- internet_interface_samples
CREATE TABLE IF NOT EXISTS internet_interface_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    interface_id TEXT NOT NULL,
    bytes_sent INTEGER NOT NULL,
    bytes_recv INTEGER NOT NULL,
    send_bps REAL NOT NULL,
    recv_bps REAL NOT NULL,
    packets_sent INTEGER NOT NULL,
    packets_recv INTEGER NOT NULL,
    errors_in INTEGER DEFAULT 0,
    errors_out INTEGER DEFAULT 0,
    discards_in INTEGER DEFAULT 0,
    discards_out INTEGER DEFAULT 0,
    link_status TEXT,
    CONSTRAINT chk_link_status CHECK (link_status IN ('up','down','unknown') OR link_status IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_interface_id_ts ON internet_interface_samples (interface_id, ts);
CREATE INDEX IF NOT EXISTS idx_interface_ts ON internet_interface_samples (ts);

-- internet_tcp_stats_samples
CREATE TABLE IF NOT EXISTS internet_tcp_stats_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    active_opens INTEGER NOT NULL,
    passive_opens INTEGER NOT NULL,
    failed_attempts INTEGER NOT NULL,
    established_resets INTEGER NOT NULL,
    current_established INTEGER NOT NULL,
    segments_sent INTEGER NOT NULL,
    segments_received INTEGER NOT NULL,
    segments_retransmitted INTEGER NOT NULL,
    source TEXT NOT NULL,
    CONSTRAINT chk_source CHECK (source IN ('GetTcpStatisticsEx','psutil_fallback','estimated'))
);

CREATE INDEX IF NOT EXISTS idx_tcp_stats_ts ON internet_tcp_stats_samples (ts);

-- internet_dns_probe_samples
CREATE TABLE IF NOT EXISTS internet_dns_probe_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    resolver TEXT NOT NULL,
    hostname TEXT NOT NULL,
    record_type TEXT NOT NULL,
    duration_ms REAL,
    status TEXT NOT NULL,
    answer_count INTEGER DEFAULT 0,
    error_code TEXT,
    probe_method TEXT NOT NULL,
    CONSTRAINT chk_dns_status CHECK (status IN ('success','timeout','servfail','nxdomain','refused','error')),
    CONSTRAINT chk_record_type CHECK (record_type IN ('A','AAAA','CNAME','TXT','MX','NS','SOA')),
    CONSTRAINT chk_probe_method CHECK (probe_method IN ('system_resolver','direct_udp','direct_tcp','doh','dot'))
);

CREATE INDEX IF NOT EXISTS idx_dns_resolver_ts ON internet_dns_probe_samples (resolver, ts);
CREATE INDEX IF NOT EXISTS idx_dns_hostname_ts ON internet_dns_probe_samples (hostname, ts);
CREATE INDEX IF NOT EXISTS idx_dns_ts ON internet_dns_probe_samples (ts);

-- internet_diagnostic_sessions
CREATE TABLE IF NOT EXISTS internet_diagnostic_sessions (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    completed_at REAL,
    status TEXT NOT NULL,
    target TEXT,
    diagnostic_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    summary_json TEXT,
    error TEXT,
    CONSTRAINT chk_session_status CHECK (status IN ('running','completed','cancelled','failed')),
    CONSTRAINT chk_diagnostic_type CHECK (diagnostic_type IN ('ping','dns','traceroute','tcp','tls','http','mtu','full_session'))
);

CREATE INDEX IF NOT EXISTS idx_session_started ON internet_diagnostic_sessions (started_at);
CREATE INDEX IF NOT EXISTS idx_session_status ON internet_diagnostic_sessions (status);

-- internet_diagnostic_results
CREATE TABLE IF NOT EXISTS internet_diagnostic_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    ts REAL NOT NULL,
    sequence INTEGER NOT NULL,
    result_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    CONSTRAINT chk_result_type CHECK (result_type IN ('probe','hop','tcp_connect','tls_handshake','http_request','mtu_probe'))
);

CREATE INDEX IF NOT EXISTS idx_diag_result_session ON internet_diagnostic_results (session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_diag_result_ts ON internet_diagnostic_results (ts);

-- internet_incidents
CREATE TABLE IF NOT EXISTS internet_incidents (
    id TEXT PRIMARY KEY,
    started_at REAL NOT NULL,
    ended_at REAL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    confidence REAL NOT NULL,
    analyzer_version TEXT NOT NULL,
    CONSTRAINT chk_category CHECK (category IN ('latency','loss','dns','gateway','interface','tcp','route')),
    CONSTRAINT chk_severity CHECK (severity IN ('info','warning','critical')),
    CONSTRAINT chk_status CHECK (status IN ('active','acknowledged','resolved','suppressed')),
    CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_incident_started ON internet_incidents (started_at);
CREATE INDEX IF NOT EXISTS idx_incident_category ON internet_incidents (category);
CREATE INDEX IF NOT EXISTS idx_incident_status ON internet_incidents (status);

-- internet_incident_evidence
CREATE TABLE IF NOT EXISTS internet_incident_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    observed_at REAL NOT NULL,
    payload_json TEXT NOT NULL,
    CONSTRAINT chk_evidence_type CHECK (evidence_type IN ('quality_sample','interface_counter','dns_probe','tcp_stat','route_change','diagnostic_result'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_incident ON internet_incident_evidence (incident_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_evidence_type ON internet_incident_evidence (evidence_type);

-- internet_insights_schema_version
CREATE TABLE IF NOT EXISTS internet_insights_schema_version (
    version INTEGER PRIMARY KEY
);

-- Insert initial version if table is empty
INSERT OR IGNORE INTO internet_insights_schema_version (version) VALUES (1);
"""

# V2 Schema - Add route and traceroute tables
V2_SCHEMA_SQL = """
-- internet_route_samples
CREATE TABLE IF NOT EXISTS internet_route_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    destination TEXT NOT NULL,
    prefix_length INTEGER NOT NULL,
    next_hop TEXT,
    interface_index INTEGER NOT NULL,
    metric INTEGER NOT NULL,
    protocol INTEGER NOT NULL,
    age INTEGER NOT NULL,
    origin INTEGER NOT NULL,
    is_default INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_route_ts ON internet_route_samples (ts);
CREATE INDEX IF NOT EXISTS idx_route_dest_ts ON internet_route_samples (destination, ts);
CREATE INDEX IF NOT EXISTS idx_route_default ON internet_route_samples (is_default, ts);

-- internet_traceroute_samples
CREATE TABLE IF NOT EXISTS internet_traceroute_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    destination TEXT NOT NULL,
    hop INTEGER NOT NULL,
    address TEXT,
    rtt_ms REAL,
    status TEXT NOT NULL,
    CONSTRAINT chk_traceroute_status CHECK (status IN ('success','timeout','unreachable','error'))
);

CREATE INDEX IF NOT EXISTS idx_traceroute_dest_ts ON internet_traceroute_samples (destination, ts);
CREATE INDEX IF NOT EXISTS idx_traceroute_ts ON internet_traceroute_samples (ts);

-- Update schema version
UPDATE internet_insights_schema_version SET version = 2;
"""

MIGRATIONS: dict[int, str] = {
    1: V1_SCHEMA_SQL,
    2: V2_SCHEMA_SQL,
}

CURRENT_VERSION = max(MIGRATIONS.keys())


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Returns new version."""
    # Check if version table exists first (first run won't have it)
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='internet_insights_schema_version'"
    ).fetchone()

    if table_exists:
        row = conn.execute("SELECT MAX(version) FROM internet_insights_schema_version").fetchone()
        current = row[0] if row and row[0] is not None else 0
    else:
        current = 0

    for version in range(current + 1, CURRENT_VERSION + 1):
        if version not in MIGRATIONS:
            raise RuntimeError(f"Missing migration for version {version}")
        logger.info("Applying Internet Insights migration v%d", version)
        conn.executescript(MIGRATIONS[version])
        conn.commit()
        logger.info("Migration v%d complete", version)

    return CURRENT_VERSION


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get current schema version."""
    row = conn.execute("SELECT MAX(version) FROM internet_insights_schema_version").fetchone()
    return row[0] if row and row[0] is not None else 0
