Technical Specification & Implementation Plan

Version: 1.0
Target baseline: Windy Smart Dashboard v0.7.0+
Feature: Internet Insights
Product level: Advanced Power User / Developer
Collection strategy: Hybrid
Platform: Windows 10/11
Backend: Python 3.12 + FastAPI
Frontend: Vue 3 + TypeScript + Pinia
Storage: SQLite WAL

───

1. Product Objective

Build an advanced Internet and Network Intelligence module inside Windy Smart Dashboard.

The feature must provide visibility into:

1. Internet connection quality.
2. Network interface and adapter health.
3. Latency, jitter and packet loss.
4. DNS resolver performance.
5. Routing and path diagnostics.
6. TCP/UDP connection behavior.
7. Application-level network diagnostics.
8. Historical network performance.
9. Anomaly detection and incident correlation.
10. Exportable diagnostic reports.

The system must distinguish:

• Observed facts: directly collected measurements.
• Derived metrics: calculated from observations.
• Hypotheses: possible explanations supported by evidence.
• Recommendations: suggested troubleshooting actions.

Never report an unverified root cause as a confirmed fact.

1.1 Non-goals

Do not implement these in v1:

• Full packet capture running continuously.
• Network intrusion detection system replacement.
• Firewall management replacement.
• VPN client or VPN management.
• Router configuration or remote router administration.
• Automatic DNS modification.
• Automatic network repair.
• External cloud telemetry service.
• LLM as a required runtime dependency.
• Rust rewrite.
• New independent speed-test implementation.

───

2. Existing Repository Integration

Repository: "worakorn-prince/windy-smart-dashboard"

Current baseline includes the following capabilities.

Existing capability| Current implementation| Integration decision
Network traffic| "metrics.network_snapshot()"| Reuse
Adapter information| "_get_adapter_details()"| Reuse and enrich
Wi-Fi information| "_get_wifi_info()"| Reuse and enrich
Public IP| "_get_public_ip()"| Reuse
Live throughput| "/ws/metrics"| Reuse
Ping target| Existing live ping metric| Reuse and improve history
Speed test| "speedtest_worker.py"| Reuse
Active connections| Existing "_net_cache"| Reuse
Process-to-port| Existing process drilldown| Reuse
Security connections| "security.monitor"| Reuse
Metrics history| "history.py"| Preserve existing ownership
General Insights| "/api/insights"| Do not duplicate
General anomaly engine| "insights.py"| Reuse design principles, not duplicate its endpoints

Existing implementation details

• "metrics.network_snapshot()" uses psutil and existing adapter/WMI helpers.
• Network snapshot already returns bytes sent/received, packet counters, adapter details, Wi-Fi and public IP.
• "NetworkCard.vue" already presents Upload, Download, total traffic, Ping, Public IP and Wi-Fi.
• "speedtest_worker.py" already performs Cloudflare-based latency, download and upload testing.
• "main.py" has a five-second "_net_cache" used for connection-related operations.
• "history.py" owns the existing "samples" table and samples metrics every 10 seconds.
• Existing Insights page is located at "/insights".
• Frontend currently has routes for Dashboard, Security, Maintenance and Insights.

Integration rules

1. Do not replace "metrics.network_snapshot()".
2. Do not create another process-to-port collector.
3. Do not create another speed-test worker.
4. Do not duplicate Security connection monitoring.
5. Do not add network-specific columns to the existing "samples" table without a demonstrated need.
6. Do not change existing REST response contracts.
7. Do not move or rewrite legacy modules as part of the initial implementation.
8. Add a dedicated Internet Insights domain and reuse existing services through explicit adapters.

───

3. Feature Architecture

Internet Insights
│
├── Overview
│ ├── Connection Status
│ ├── Internet Quality
│ ├── Current Throughput
│ ├── Active Interface
│ └── Recent Incidents
│
├── Performance
│ ├── Latency
│ ├── Jitter
│ ├── Packet Loss
│ ├── TCP Statistics
│ └── Throughput History
│
├── DNS Intelligence
│ ├── Configured Resolvers
│ ├── DNS Probe
│ ├── Resolution Time
│ ├── Resolver Comparison
│ └── DNS Diagnostics
│
├── Route Analysis
│ ├── Route Table
│ ├── Default Gateway
│ ├── Traceroute
│ ├── Hop Latency
│ └── Path Comparison
│
├── Connections
│ ├── Active TCP Connections
│ ├── UDP Endpoints
│ ├── Process Mapping
│ ├── Connection States
│ └── Connection Changes
│
├── Wi-Fi & Adapters
│ ├── Adapter Health
│ ├── Wi-Fi Signal
│ ├── Channel
│ ├── Interface Errors
│ └── Network Configuration
│
├── Diagnostic Lab
│ ├── Ping
│ ├── DNS Lookup
│ ├── Traceroute
│ ├── TCP Connect
│ ├── TLS
│ ├── HTTP
│ ├── MTU
│ └── Diagnostic Session
│
└── Intelligence
├── Baseline
├── Anomaly Detection
├── Correlation
├── Incident Timeline
└── Recommendations

───

4. Backend Module Boundaries

Create a new package:

backend/
└── internet_insights/
├── init.py
├── router.py
├── config.py
│
├── collectors/
│ ├── init.py
│ ├── quality.py
│ ├── interface.py
│ ├── tcp_stats.py
│ ├── dns_probe.py
│ ├── route.py
│ └── wifi.py
│
├── diagnostics/
│ ├── init.py
│ ├── ping.py
│ ├── dns.py
│ ├── traceroute.py
│ ├── tcp.py
│ ├── tls.py
│ ├── http.py
│ └── mtu.py
│
├── analyzers/
│ ├── init.py
│ ├── quality.py
│ ├── baseline.py
│ ├── anomaly.py
│ ├── correlation.py
│ └── recommendations.py
│
├── models/
│ ├── init.py
│ ├── observations.py
│ ├── diagnostics.py
│ └── incidents.py
│
├── services/
│ ├── collector_manager.py
│ ├── diagnostics_manager.py
│ ├── session_manager.py
│ └── incident_manager.py
│
├── storage/
│ ├── init.py
│ ├── database.py
│ ├── migrations.py
│ └── repositories.py
│
└── tests/
├── test_quality.py
├── test_dns.py
├── test_routes.py
├── test_tcp.py
├── test_diagnostics.py
├── test_storage.py
├── test_api.py
└── test_collector_lifecycle.py

Dependency rules

• Collectors collect observations only.
• Collectors must not contain UI logic.
• Collectors must not write directly into SQLite.
• Repositories own SQL operations.
• Services coordinate collectors and repositories.
• Analyzers operate on normalized observations.
• Analyzers must not call Windows APIs directly.
• Diagnostic operations must be bounded and cancellable.
• API routes must not contain collection or analysis logic.
• Existing modules must be integrated through explicit adapters.

───

5. Collection Strategy

Use Hybrid Collection.

5.1 Background Collection

Background collectors run only while the application is active.

Collector| Initial interval| Purpose
Existing network snapshot| Existing cadence| Traffic and adapter status
Gateway probe| 5 seconds| Local connectivity
Primary endpoint probe| 5 seconds| Internet latency
Secondary endpoint probe| 15 seconds| Independent comparison
Interface counters| 10 seconds| Per-interface traffic
TCP statistics| 15 seconds| Global TCP behavior
Active connections| Existing 5-second cache| Process and connection visibility
DNS probe| 60 seconds| Resolver health
Wi-Fi state| 30 seconds| Signal and association state
Route snapshot| 5 minutes + change detection| Routing changes

Intervals must be configurable.

Do not start a new collector if the previous execution is still running.

Use bounded queues, timeouts, cancellation and backpressure.

Probe targets

Initial defaults:

• Local Gateway: resolve from active interface.
• Primary Internet target: "1.1.1.1".
• Secondary Internet target: "8.8.8.8".
• DNS probe: use configured DNS resolver and controlled test domains.

Targets must be user-configurable.

Do not hardcode target-specific quality thresholds as universal truth.

Probe policy

• Use small payloads.
• Limit simultaneous requests.
• Record timeout separately from packet loss.
• Record endpoint and probe protocol.
• Use monotonic time for elapsed measurements.
• Use UTC Unix timestamps for storage.
• Do not let probes saturate the connection.
• Do not assume ICMP response failure means the destination is offline.

5.2 On-demand Collection

Run only when explicitly requested:

• Traceroute.
• DNS record lookup.
• DNS resolver comparison.
• TCP connect test.
• TLS handshake test.
• HTTP diagnostics.
• MTU discovery.
• Extended route inspection.
• Network Snapshot.
• Full Troubleshooting Session.

Each operation must have:

• A timeout.
• Maximum execution duration.
• Maximum number of probes or hops.
• Cancellation support.
• Structured output.
• Clear error states.

5.3 Deep Inspection

Packet capture and ETW must not run continuously.

Future deep-inspection support:

• ETW network providers.
• "netsh trace".
• Optional Npcap integration.
• Packet capture with explicit user approval.

This must be a separate capability with visible resource usage, capture duration and privacy warnings.

Do not require Npcap for normal Internet Insights operation.

───

6. Measurement Definitions

Implement a consistent metric contract.

Latency

RTT in milliseconds.

Store raw probe measurements and calculate:

• Minimum.
• Median.
• P95.
• Maximum.
• Sample count.
• Timeout count.

Use median as the primary displayed latency.

Jitter

Use mean absolute difference between consecutive successful RTT samples within the same probe series.

jitter = mean(abs(rtt[i] - rtt[i-1]))

Do not combine unrelated targets into one jitter series.

Packet Loss

loss_percent = failed_probes / total_probes * 100

Differentiate:

• Timeout.
• Destination unreachable.
• DNS failure.
• Local interface unavailable.
• Probe execution error.

Throughput

Use existing interface counters.

Calculate per-interface rates from independent counter snapshots.

Do not reuse or mutate private rate-calculation state from "metrics.py" or "history.py".

TCP Retransmission

Use the best available Windows TCP statistics.

Distinguish:

• Global TCP retransmission counters.
• Per-connection retransmission statistics.
• Packet-level retransmission observations.

Do not claim to know the exact process responsible from global counters.

If per-connection statistics are unavailable, display "Unavailable" rather than infer.

Connection Quality

Do not reduce all measurements to an unexplained score.

If a composite score is introduced, show:

• Inputs.
• Weights.
• Confidence.
• Missing metrics.
• Calculation version.

Prefer quality labels with explicit evidence.

───

7. Windows Integration

Use Windows-native APIs where practical.

7.1 Initial implementation

• psutil for existing interface counters and connection information.
• Existing adapter and Wi-Fi functions for compatibility.
• Python standard library and existing httpx for diagnostics.
• ctypes for focused Windows API integrations when necessary.

7.2 Native API candidates

Capability| Windows API
TCP connection table| GetExtendedTcpTable
UDP endpoint table| GetExtendedUdpTable
Interface counters| GetIfTable2 / GetIfEntry2
Routing table| GetIpForwardTable2
Route selection| GetBestRoute2
TCP statistics| GetTcpStatisticsEx
Wi-Fi interface| WlanQueryInterface
DNS configuration| GetNetworkParams / adapter configuration
DNS query| DnsQuery_W / DnsQueryEx

Build a "platform_windows" adapter layer inside this feature if native integrations become necessary.

Do not spread ctypes declarations throughout the business logic.

All native calls must have:

• Typed structures.
• Buffer-size retry handling.
• Error-code mapping.
• Memory cleanup.
• Unit tests for parsers.
• Graceful unsupported-platform behavior.

Do not require Administrator for read-only operations unless Windows explicitly requires it.

───

8. DNS Intelligence

8.1 MVP capabilities

• Read configured DNS servers from active adapters.
• Query A and AAAA records.
• Measure controlled DNS lookup duration.
• Record success, timeout and error.
• Compare configured resolvers when explicitly requested.
• Display resolver configuration changes.
• Support custom hostname lookup.

8.2 Important distinction

A normal Windows DNS lookup may use the OS resolver, local cache, VPN configuration or other name-resolution mechanisms.

Therefore:

• Label system-resolver queries separately.
• Label direct-resolver queries separately.
• Do not claim that every application DNS request has been captured.
• Do not claim DoH or DoT usage unless there is direct evidence.

Passive DNS monitoring is outside the MVP.

8.3 Privacy

Do not store every domain visited by the user.

Only persist controlled diagnostic queries by default.

If passive DNS collection is ever added, it must be explicit opt-in.

───

9. Route Analysis

9.1 MVP

• Current route table.
• Default gateway.
• Interface index.
• Destination route selection.
• IPv4 and IPv6 support.
• On-demand traceroute.
• Per-hop RTT and response status.
• Destination reachability.

9.2 Traceroute rules

• Maximum 30 hops by default.
• Configurable timeout.
• Configurable maximum duration.
• Support ICMP/UDP method where available.
• Record non-responsive hops without treating them as confirmed packet loss.
• Stop when destination is reached or limits are exhausted.

9.3 MTU

Implement MTU diagnostics as an on-demand test.

Do not modify system MTU automatically.

Clearly distinguish:

• Interface MTU.
• Path MTU estimate.
• Failed probe.
• Unsupported fragmentation behavior.

───

10. Connection Intelligence

Reuse existing connection enumeration and process drilldown.

Extend presentation and history only where needed.

Fields:

• PID.
• Process name.
• Executable path when available.
• Local IP.
• Local port.
• Remote IP.
• Remote port.
• Protocol.
• Connection state.
• First observed time.
• Last observed time.
• Bytes sent/received when available.
• Interface association when available.

Do not claim per-process byte counters when the underlying collector only provides system-wide counters.

Add filters:

• Process.
• PID.
• Local port.
• Remote IP.
• Protocol.
• Connection state.
• IPv4 / IPv6.

Do not duplicate Firewall or Security actions.

The existing Security module remains the owner of blocking and security enforcement.

───

11. SQLite Data Model

Use the existing database file:

"backend/.cache/history.db"

Create independent tables owned by Internet Insights.

Do not alter the existing "samples" table.

Do not modify the existing "history.py" schema version.

Create a separate migration version table:

"internet_insights_schema_version"

11.1 Tables

"internet_quality_samples"

• id INTEGER PRIMARY KEY
• ts REAL NOT NULL
• target_id TEXT NOT NULL
• probe_type TEXT NOT NOT
• rtt_ms REAL
• status TEXT NOT NULL
• error_code TEXT
• timeout_ms INTEGER

Indexes:

• "(target_id, ts)"
• "(probe_type, ts)"

"internet_interface_samples"

• id INTEGER PRIMARY KEY
• ts REAL NOT NULL
• interface_id TEXT NOT NULL
• bytes_sent INTEGER
• bytes_recv INTEGER
• send_bps REAL
• recv_bps REAL
• packets_sent INTEGER
• packets_recv INTEGER
• errors_in INTEGER
• errors_out INTEGER
• discards_in INTEGER
• discards_out INTEGER
• link_status TEXT

Indexes:

• "(interface_id, ts)"

"internet_tcp_stats_samples"

• id INTEGER PRIMARY KEY
• ts REAL NOT NULL
• active_opens INTEGER
• passive_opens INTEGER
• failed_attempts INTEGER
• established_resets INTEGER
• current_established INTEGER
• segments_sent INTEGER
• segments_received INTEGER
• segments_retransmitted INTEGER
• source TEXT NOT NULL

Indexes:

• "(ts)"

Counter deltas must be calculated safely, accounting for counter resets and system restarts.

"internet_dns_probe_samples"

• id INTEGER PRIMARY KEY
• ts REAL NOT NULL
• resolver TEXT NOT NULL
• hostname TEXT NOT NULL
• record_type TEXT NOT NULL
• duration_ms REAL
• status TEXT NOT NULL
• answer_count INTEGER
• error_code TEXT

Indexes:

• "(resolver, ts)"
• "(hostname, ts)"

"internet_diagnostic_sessions"

• id TEXT PRIMARY KEY
• started_at REAL NOT NULL
• completed_at REAL
• status TEXT NOT NULL
• target TEXT
• diagnostic_type TEXT NOT NULL
• config_json TEXT
• summary_json TEXT
• error TEXT

"internet_diagnostic_results"

• id INTEGER PRIMARY KEY
• session_id TEXT NOT NULL
• ts REAL NOT NULL
• sequence INTEGER
• result_type TEXT NOT NULL
• payload_json TEXT NOT NULL

Foreign key:

"session_id REFERENCES internet_diagnostic_sessions(id) ON DELETE CASCADE"

"internet_incidents"

• id TEXT PRIMARY KEY
• started_at REAL NOT NULL
• ended_at REAL
• category TEXT NOT NULL
• severity TEXT NOT NULL
• status TEXT NOT NULL
• title TEXT NOT NULL
• summary TEXT
• confidence REAL
• analyzer_version TEXT

"internet_incident_evidence"

• id INTEGER PRIMARY KEY
• incident_id TEXT NOT NULL
• evidence_type TEXT NOT NULL
• observed_at REAL NOT NULL
• payload_json TEXT NOT NULL

Foreign key:

"incident_id REFERENCES internet_incidents(id) ON DELETE CASCADE"

11.2 Database Rules

• SQLite WAL mode.
• Busy timeout.
• Short transactions.
• Batch inserts.
• Bounded write queue.
• Prepared statements.
• Parameterized SQL only.
• Explicit schema migrations.
• No database writes from collectors.
• No unbounded JSON payloads.
• JSON size limits for diagnostic output.

Use separate SQLite connections for Internet Insights repositories.

Do not access private connection objects from "history.py".

11.3 Retention

Initial defaults:

Data| Retention
Quality samples| 14 days
Interface samples| 14 days
TCP statistics| 14 days
DNS probe history| 14 days
Diagnostic sessions| 30 days
Diagnostic results| 30 days
Incidents| 90 days
Incident evidence| 90 days

Note: while an incident is still open, its rule skips re-evaluation
(skipped_reason is set), so it is never auto-resolved by a later tick.
Auto-resolve happens only when the rule fully evaluated (skipped_reason is
None) and the condition no longer holds. This is design intent: an open
incident reflects the operator-visible state until recovery is actually
observed, not a bug.

Make retention configurable.

Aggregate before pruning where long-term history is required.

Do not retain packet payloads in the MVP.

───

12. API Contract

Create "backend/internet_insights/router.py".

Prefix:

"/api/internet"

12.1 Read endpoints

Method| Endpoint| Purpose
GET| "/overview"| Summary and current health
GET| "/quality"| Latency, jitter and loss
GET| "/quality/history"| Historical quality samples
GET| "/interfaces"| Interface information
GET| "/interfaces/{id}/history"| Interface history
GET| "/dns"| DNS configuration and health
GET| "/dns/history"| DNS probe history
GET| "/routes"| Current route table
GET| "/connections"| Existing connection data with normalized filters
GET| "/tcp/stats"| TCP statistics
GET| "/incidents"| Network incidents
GET| "/incidents/{id}"| Incident detail and evidence

12.2 Diagnostic endpoints

Method| Endpoint| Purpose
POST| "/diagnostics/ping"| Ping test
POST| "/diagnostics/dns"| DNS lookup
POST| "/diagnostics/traceroute"| Route tracing
POST| "/diagnostics/tcp"| TCP connect
POST| "/diagnostics/tls"| TLS handshake
POST| "/diagnostics/http"| HTTP diagnostics
POST| "/diagnostics/mtu"| MTU discovery
POST| "/sessions"| Start troubleshooting session
GET| "/sessions/{id}"| Session status and summary
GET| "/sessions/{id}/results"| Session results
POST| "/sessions/{id}/cancel"| Cancel running session
GET| "/sessions/{id}/export"| Export report

12.3 API response rules

Use Pydantic request and response models.

Standard response metadata:

• "generated_at"
• "data_window"
• "source"
• "status"
• "errors"
• "coverage"

Never return misleading zero values for unavailable metrics.

Use null or explicit unavailable status.

Validate:

• Maximum time range.
• Maximum result count.
• Maximum target length.
• Allowed protocols.
• Diagnostic duration.
• Hop limit.
• Request body size.

12.4 Existing endpoint compatibility

Do not change:

• "/api/speedtest"
• "/api/insights"
• "/api/processes/{pid}"
• "/api/processes/{pid}/history"
• "/ws/metrics"
• "/ws/security"

The new Internet Insights endpoints must be additive.

───

13. WebSocket Contract

Add:

"/ws/internet"

Use a separate channel to avoid increasing traffic on the existing "/ws/metrics".

Message types:

• "internet_status"
• "quality_sample"
• "interface_change"
• "dns_status"
• "incident_created"
• "incident_updated"
• "diagnostic_progress"
• "diagnostic_completed"
• "collector_status"

Example:

{
"type": "quality_sample",
"ts": 1795000000.0,
"target_id": "primary",
"probe_type": "icmp",
"rtt_ms": 18.4,
"status": "success"
}

Rules:

• No raw high-frequency event flood.
• Broadcast only meaningful updates.
• Batch where appropriate.
• Remove disconnected clients.
• Bound outgoing queues.
• Do not block collectors while sending WebSocket messages.

───

14. Frontend Architecture

Keep the existing Vue 3, TypeScript, Pinia, Vite and uPlot stack.

Add:

frontend/src/
├── pages/
│ └── InternetInsights.vue
│
├── components/
│ └── internet/
│ ├── InternetOverview.vue
│ ├── QualitySummary.vue
│ ├── LatencyChart.vue
│ ├── PacketLossChart.vue
│ ├── InterfaceTable.vue
│ ├── DnsResolverCard.vue
│ ├── DnsHistoryChart.vue
│ ├── RouteTable.vue
│ ├── TracerouteView.vue
│ ├── ConnectionsTable.vue
│ ├── TcpStatsCard.vue
│ ├── DiagnosticLab.vue
│ ├── DiagnosticSession.vue
│ ├── IncidentTimeline.vue
│ └── EvidencePanel.vue
│
├── stores/
│ └── internet.ts
│
├── composables/
│ └── useInternetWebSocket.ts
│
└── types/
└── internet.ts

14.1 Navigation

Add an Internet Insights navigation item.

Do not replace or rename the existing general Insights page.

Suggested pages:

1. Overview
2. Performance
3. DNS
4. Routing
5. Connections
6. Wi-Fi & Adapters
7. Diagnostic Lab
8. Incidents

14.2 UX requirements

• Advanced information density.
• Clear metric units.
• Monospace values for IPs, ports and protocol data.
• Expandable evidence.
• Time-range selection.
• Filterable tables.
• Loading, empty, error and unavailable states.
• No fake or placeholder measurements.
• Responsive layout.
• Tooltips explaining metrics.
• Copy IP, hostname and diagnostic output.
• JSON / CSV / Markdown export.

Show the source and freshness of every major metric.

───

15. Intelligence Engine

Start with deterministic rules and statistical analysis.

Do not introduce an LLM dependency.

15.1 Baseline

Maintain a per-target baseline.

Use historical windows and minimum sample requirements.

Prefer robust statistics such as median and percentiles where outliers can distort the mean.

Keep detection and training windows separate.

15.2 Anomaly Detection

Initial candidate rules:

• Sustained latency increase.
• Sustained packet loss.
• DNS resolution degradation.
• Gateway reachability loss.
• Interface error/discard increase.
• TCP retransmission rate increase.
• Route change.
• Unexpected interface transition.

Every rule must define:

• Input metrics.
• Minimum sample count.
• Threshold.
• Duration.
• Cooldown.
• Recovery condition.
• Confidence.
• Analyzer version.

15.3 Correlation

Example:

1. Gateway remains reachable.
2. Multiple Internet targets show increased latency.
3. DNS remains normal.
4. TCP retransmission indicators rise.

Result:

Possible upstream network degradation.

Do not state that the ISP is confirmed responsible.

15.4 Incident Evidence

Every incident must preserve:

• Triggering observations.
• Timestamp range.
• Affected target.
• Relevant interface.
• Baseline comparison.
• Related diagnostic session.
• Confidence.
• Explanation of uncertainty.

15.5 Recommendations

Recommendations must be based on evidence.

Examples:

• DNS timeout: test an alternative resolver.
• Gateway unreachable: inspect Wi-Fi/LAN and router.
• High latency only on one endpoint: compare other destinations.
• Interface errors increasing: inspect adapter, cable, driver or link.
• TCP failures: inspect destination service and firewall conditions.

Never apply changes automatically.

───

16. Troubleshooting Session

This is the key differentiating feature.

User action:

"Start Troubleshooting"

Session workflow:

1. Capture active adapter and configuration.
2. Capture current route and gateway.
3. Run gateway probes.
4. Run multiple Internet endpoint probes.
5. Run system DNS probe.
6. Capture TCP statistics.
7. Capture active connection snapshot.
8. Run optional DNS/TCP/HTTP diagnostics.
9. Correlate observations.
10. Generate report.

Default session duration: 60 seconds.

Allow 30 / 60 / 120-second profiles.

Do not automatically run a speed test.

Speed test must be an explicit optional action because it consumes significant bandwidth.

Session result:

• Overall connectivity state.
• Quality measurements.
• Local network findings.
• DNS findings.
• Route findings.
• TCP findings.
• Evidence timeline.
• Possible causes.
• Recommended next actions.
• Exportable report.

───

17. Security and Privacy

The existing application is intentionally bound to "127.0.0.1".

Preserve that security boundary.

Requirements:

• Keep localhost-only binding.
• Validate WebSocket Origin.
• Validate all diagnostic targets.
• Restrict diagnostic schemes to HTTP and HTTPS.
• Reject file URLs and unsupported schemes.
• Prevent localhost and private-network probing from being abused through arbitrary remote input.
• Do not create arbitrary command execution endpoints.
• Do not concatenate untrusted input into PowerShell commands.
• Use subprocess argument arrays when subprocesses are necessary.
• Apply strict timeouts.
• Limit diagnostic concurrency.
• Limit response size.
• Avoid storing sensitive payloads.
• Redact credentials, query tokens and authorization headers.
• Do not persist full packet payloads.
• Show a warning before deep capture.
• Require explicit confirmation for resource-intensive diagnostics.

For HTTP diagnostics, default to user-specified destinations and reject redirects to disallowed destinations.

───

18. Performance Requirements

Initial targets:

Metric| Target
Normal background CPU overhead| < 2% average on reference system
Idle memory overhead| < 100 MB incremental
Normal probe bandwidth| < 100 KB/min excluding speed test
API overview response| < 300 ms from warm cache
UI initial render| < 2 seconds after API data is ready
Background queue| Bounded
Diagnostic concurrency| Configurable, default 2
Normal collector failure| Must not crash backend

These are engineering targets, not guaranteed results. Validate them on Windows hardware.

No collector may block the FastAPI event loop.

Use asyncio and "asyncio.to_thread()" for blocking operations where appropriate.

───

19. Implementation Plan

Phase 0 — Repository Audit and Contract

Tasks:

1. Inspect current network collection and connection cache.
2. Identify exact live ping implementation.
3. Map current speedtest response.
4. Identify existing database connection ownership and locks.
5. Map current WebSocket manager.
6. Define integration adapters.
7. Write feature specification and API contract.

Deliverables:

• "docs/INTERNET_INSIGHTS_SPEC.md"
• "docs/INTERNET_INSIGHTS_API.md"
• "docs/INTERNET_INSIGHTS_DATA_MODEL.md"
• "docs/INTERNET_INSIGHTS_MIGRATION.md"

Acceptance:

• No duplicate collector.
• No breaking existing endpoint.
• All existing integration points identified.

Phase 1 — Foundation and Overview

Tasks:

1. Create "backend/internet_insights".
2. Implement dedicated configuration.
3. Implement database connection and migrations.
4. Implement quality collector.
5. Implement interface history collector.
6. Implement collector lifecycle manager.
7. Add REST overview and history APIs.
8. Add frontend route and Pinia store.
9. Build Internet Overview.

Acceptance:

• Existing dashboard works unchanged.
• Quality samples persist.
• Interface history is independent from legacy rate counters.
• Collector starts and stops cleanly.
• Missing data is represented accurately.

Phase 2 — Performance Intelligence

Tasks:

1. Gateway probes.
2. Multiple endpoint probes.
3. Latency statistics.
4. Jitter calculation.
5. Packet loss calculation.
6. TCP global statistics.
7. Historical charts.
8. Quality status and evidence.

Acceptance:

• Measurements have correct timestamps.
• Probe targets are independently tracked.
• Timeout and loss are distinguishable.
• No false claim of per-process retransmission data.
• Resource overhead is measured.

Phase 3 — DNS and Routing

Tasks:

1. Read active DNS configuration.
2. Implement controlled DNS probes.
3. Implement resolver comparison.
4. Implement route snapshot.
5. Implement traceroute session.
6. Add DNS and Route pages.

Acceptance:

• DNS sources are identified.
• System-resolver and direct-resolver results are distinguished.
• Traceroute handles non-responsive hops.
• IPv4 and IPv6 behavior is tested.
• No automatic network configuration changes.

Phase 4 — Developer Diagnostic Lab

Tasks:

1. TCP connect test.
2. TLS handshake test.
3. HTTP diagnostics.
4. MTU discovery.
5. Diagnostic session manager.
6. Cancellation and timeouts.
7. Export JSON, CSV and Markdown.

Acceptance:

• Diagnostics cannot run indefinitely.
• Invalid targets are rejected.
• HTTP redirects are validated.
• Sessions preserve structured evidence.
• Exported reports contain no credentials.

Phase 5 — Intelligence and Incident Correlation

Tasks:

1. Per-target baseline.
2. Anomaly rules.
3. Incident lifecycle.
4. Evidence persistence.
5. Correlation engine.
6. Recommendation engine.
7. Incident timeline UI.

Acceptance:

• Detection and baseline windows are separate.
• Minimum sample requirements are enforced.
• Cooldown and recovery work.
• Every incident includes supporting evidence.
• Hypotheses are not presented as confirmed root causes.

Phase 6 — Hardening and Release

Tasks:

1. Full backend test suite.
2. Frontend unit tests.
3. Playwright E2E.
4. Migration tests from existing v0.6.3 database.
5. Resource profiling.
6. Retention tests.
7. Security review.
8. Update README and API documentation.
9. Release notes.

Acceptance:

• Existing features remain functional.
• Existing database data remains intact.
• No regression in existing WebSocket contracts.
• Windows CI passes.
• New module can fail independently without taking down the dashboard.

───

20. Testing Strategy

Unit tests

• Latency statistics.
• Jitter.
• Packet loss.
• Counter wrap/reset.
• DNS response parsing.
• Route parsing.
• Traceroute parsing.
• MTU result classification.
• Baseline calculations.
• Anomaly lifecycle.
• Correlation rules.

Integration tests

• SQLite migration.
• Concurrent reads and writes.
• Collector lifecycle.
• Cache behavior.
• WebSocket broadcast.
• Diagnostic cancellation.
• API validation.
• Retention.

Frontend tests

• Store state.
• Loading and error states.
• Historical chart.
• Filter controls.
• Session progress.
• Incident evidence.
• Export actions.

E2E scenarios

1. Open Internet Insights.
2. Verify Overview loads.
3. Verify quality samples update.
4. Open DNS page.
5. Run DNS lookup.
6. Run traceroute.
7. Start troubleshooting session.
8. Cancel a running session.
9. View session report.
10. Verify existing Dashboard, Security, Maintenance and Insights remain functional.

Tests must use mocks or controlled local fixtures where possible. CI must not depend on external Internet availability.

───

21. Definition of Done

Internet Insights v1 is complete when:

• All existing Network Monitor capabilities remain intact.
• The new Overview and Performance pages work.
• Historical quality data is persisted.
• DNS diagnostics work.
• Route diagnostics work.
• TCP/HTTP/TLS diagnostics work.
• Troubleshooting sessions work.
• Reports can be exported.
• Basic anomaly detection works.
• Incident evidence is preserved.
• Data retention is enforced.
• No continuous packet capture is required.
• No new paid service is required.
• No Rust dependency is introduced.
• All existing project tests pass.

───

22. Future Enhancements — Not MVP

Potential later features:

• ETW Network Deep Inspection.
• Optional Npcap packet analysis.
• Per-connection retransmission details.
• HTTP/2 and HTTP/3 diagnostics.
• TLS certificate chain inspection.
• QUIC analysis.
• Advanced IPv6 diagnostics.
• VPN route and DNS leak diagnostics.
• DNS-over-HTTPS diagnostics.
• Network benchmark profiles.
• Custom diagnostic plugins.
• Advanced incident correlation.

Do not start these until v1 provides reliable baseline data and diagnostics.

───

23. Final Architectural Decisions

1. Keep the current technology stack.
2. Add Internet Insights as an independent backend domain.
3. Reuse current Network Snapshot, Speed Test, Ping, Connections and Security modules.
4. Keep general Insights separate.
5. Use hybrid collection.
6. Store network-specific history in separate SQLite tables within the existing database.
7. Use REST for queries and diagnostics.
8. Use a dedicated WebSocket channel for real-time updates.
9. Use deterministic intelligence before introducing AI.
10. Keep deep inspection opt-in.
11. Preserve localhost-only security.
12. Implement incrementally without a Big Bang rewrite.

Primary product differentiator:

Windy should not merely report that Internet is slow. It should show what was measured, where degradation appears, which evidence supports the diagnosis, what remains uncertain, and what the user should test next.

1. จุดที่ต้องระวังเป็นพิเศษในการลงมือจริง
มี 4 เรื่องที่ฉันอยากเน้น เพราะถ้าออกแบบผิดตั้งแต่ต้นจะทำให้ข้อมูลวิเคราะห์ไม่น่าเชื่อถือ
1.1 อย่าใช้ Network Throughput แทน Internet Speed
ค่าจาก psutil.net_io_counters() รวม Traffic ของเครื่อง ไม่ใช่ความเร็วแพ็กเกจ Internet และอาจรวม VPN, Virtual Adapter หรือ Traffic ภายใน LAN ด้วย ต้องแยกตาม Interface
1.2 อย่าใช้ Packet Loss จาก ICMP เป็นข้อสรุปทันที
บางปลายทางจำกัด ICMP หรือไม่ตอบ Ping แต่ TCP/HTTPS ยังทำงานได้ ต้องเปรียบเทียบหลายวิธีและหลายปลายทาง
1.3 อย่าเก็บ DNS History ของทุกเว็บไซต์ที่ผู้ใช้เปิด
MVP ควรเก็บเฉพาะ DNS Probe ที่ Windy สั่งเองก่อน เป็นการลดความเสี่ยงด้าน Privacy และทำให้ฐานข้อมูลไม่บวมโดยไม่จำเป็น
1.4 อย่าให้ Collector แต่ละตัวสร้าง Thread หรือ Process เองอย่างไม่มีขอบเขต
ต้องมี Collector Manager กลาง มีรอบทำงาน มี Timeout และมีการหยุดงานอย่างถูกต้อง ไม่อย่างนั้นฟีเจอร์ที่เพิ่มเข้ามาอาจทำให้ Windy เองกินทรัพยากรจนกลายเป็นปัญหา

2. Windows API ที่ใช้เป็นฐาน
สำหรับการพัฒนาระดับ Advanced สามารถใช้ Windows API โดยไม่จำเป็นต้องติดตั้ง Driver เพิ่ม:
GetExtendedTcpTable สำหรับ TCP Endpoints และ Connection Table
GetIpForwardTable2 สำหรับ Routing Table
WlanQueryInterface สำหรับ Wi-Fi Interface และ Connection Attributes
DnsQuery_W สำหรับ DNS Lookup
IP Helper APIs สำหรับ Interface, TCP, UDP และ Network Statistics
ไม่จำเป็นต้อง Implement API เหล่านี้ทั้งหมดใน Phase แรก ให้เริ่มจากของเดิมที่มีอยู่และเพิ่มเฉพาะส่วนที่ขาด

3. ลำดับที่ควรให้ Agent ทำ
ฉันแนะนำให้แบ่งงานเป็น PR หรือ Milestone เล็ก ๆ แทนการสั่ง Agent สร้างทั้งระบบในครั้งเดียว

Implementation Milestones
M0 — Audit & Contract
ตรวจสอบโค้ดเดิม ทำ Integration Map และกำหนด API Contract โดยยังไม่แก้พฤติกรรมเดิม
M1 — Collector & Storage
สร้าง Internet Insights Domain, SQLite Migration และ Collector Lifecycle
M2 — Overview & Performance
สร้างหน้า Overview, Latency, Jitter, Packet Loss และ History
M3 — DNS & Routing
เพิ่ม DNS Intelligence, Route Table และ Traceroute
M4 — Developer Diagnostics
เพิ่ม TCP, TLS, HTTP, MTU และ Troubleshooting Session
M5 — Intelligence
เพิ่ม Baseline, Anomaly, Incident และ Evidence Correlation
M6 — Release
ทดสอบ Regression, Performance, Security และ Migration

คำแนะนำสุดท้าย: ให้ Agent เริ่มจาก M0 เท่านั้นก่อนค่ะ เพราะต้องตรวจสอบจุดเชื่อมต่อใน Code ปัจจุบันให้ครบ โดยเฉพาะ _net_cache, Ping Implementation, WebSocket Manager และ SQLite Connection Ownership แล้วค่อยอนุมัติ M1 จะช่วยป้องกันไม่ให้ Agent สร้าง Collector หรือ Database Layer ซ้ำกับระบบเดิม