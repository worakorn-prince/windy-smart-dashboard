# Windy Smart Dashboard

![License](https://img.shields.io/github/license/worakorn-prince/windy-smart-dashboard)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![Latest Release](https://img.shields.io/github/v/release/worakorn-prince/windy-smart-dashboard)
![Last Commit](https://img.shields.io/github/last-commit/worakorn-prince/windy-smart-dashboard)

Real-time web dashboard for monitoring your own computer (CPU, RAM, disk,
network, top processes, system info, internet speed test) plus a built-in
**security audit module** that inspects your machine for weak-spots:
open ports, listening processes, Defender status, failed logins, hosts
file redirects, ARP spoofing hints, suspicious outbound connections, and
more.

Built with FastAPI (Python 3.12) + Vue 3 / TypeScript / Vite.

> ⚠️ The dashboard binds to `127.0.0.1` only — accessible from this
> computer, not from the network. This is intentional and a security
> feature.

## 🪟 Platform & Requirements

**Windows 10 / 11 only.** This project is not portable to other operating
systems and has not been tested (and is not expected to run) on Linux or
macOS. It relies on Windows-specific pieces:

- PowerShell launcher scripts (`run.ps1` / `run.bat`)
- **LibreHardwareMonitorLib** (in-process COM) for CPU/GPU/disk temperatures
  and power draw
- **Windows Firewall** (block/unblock rules), **Windows Defender** status,
  and the **Security event log** (failed logins)
- **Native Windows Toast** notifications
- `clr_loader` / `pythonnet` to load the `.NET` hardware library

On Windows the backend (FastAPI + psutil) and frontend (Vue/Vite) are plain
Python/Node and would run anywhere, but the platform integrations above are
Windows-only, so the app as a whole only runs on Windows.

### Prerequisites
- Python 3.10+ on `PATH`
- Node.js 18+ on `PATH`
- (Optional, for sensors) LibreHardwareMonitor — `winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor`
- (For full security features) run as **Administrator**

---

## 🚀 Quick Start

```bash
git clone https://github.com/worakorn-prince/windy-smart-dashboard.git
cd windy-smart-dashboard
```

```powershell
# one-time: install backend (venv) + frontend (node_modules) dependencies
.\run.ps1 -Install

# run it — opens at http://127.0.0.1:8000
# (auto-elevates via one UAC prompt so hardware sensors can be read)
.\run.ps1
```

Open **http://127.0.0.1:8000** in your browser.

> 💡 Other launcher flags: `.\run.ps1 -Dev` (backend :8000 + Vite dev :5173),
> `.\run.ps1 -Clean` (wipe caches). On Linux/macOS this project will **not** run —
> it is Windows-only (see above).

> 🤖 Looking for the file-based **agent observability dashboard**? See
> [`README-viewer.md`](README-viewer.md) for live tail (`scripts/watch.py`),
> run comparison (`scripts/compare.py`), token/cost analytics
> (`scripts/cost.py --budget`) and log retention (`scripts/retention.py`).

---

## ✨ Features

### Dashboard
- CPU usage (overall + per-core bars) and frequency
- Memory usage (RAM + swap)
- Disk usage per partition + read/write throughput
- Network interfaces + live upload/download rate
- Top 10 processes (sortable by CPU/RAM)
- **Process drilldown** — click a process row for PID, command line, CPU/RAM,
  a 3-level parent/child tree, listening ports and a uPlot CPU/RAM history
  (`/api/processes/{pid}` and `/api/processes/{pid}/history`, sampled into
  the `process_samples` table)
- **Disk health** — per-volume usage, SMART status via PowerShell
  `Get-PhysicalDisk` and a days-to-full forecast from `disk_samples`
  (`GET /api/health/disk`)
- **Scheduled HTML reports** — self-contained daily (`days=1`) or weekly
  (`days=7`) reports covering usage, top processes, disk forecast and
  security events, written to `reports/` (`ReportsCard` on the Maintenance page)
- System info (hostname, OS, processor, uptime, boot time)
- Internet speedtest **on-demand** (button — uses bandwidth, not polled)
  Implemented against Cloudflare's free `speed.cloudflare.com` endpoint
  (no API key, no rate limit).
- Live ping latency to a configurable target
- **Metrics history** — every metric is sampled to a local SQLite DB
  every 10 s and charted over the last **1 h / 6 h / 24 h**, including
  CPU/GPU/disk temperatures and power draw (CPU W / GPU W), with
  per-series toggles and multiple y-axes
- **Live power usage** — a dedicated card shows current total wattage
  (CPU + GPU) plus a per-component and per-GPU breakdown
- **Health strip** — a one-line summary bar (CPU / RAM / disk / top
  temperatures) pinned at the top of the dashboard
- **Dark / light mode** — header toggle, persisted in `localStorage`
- **Tabbed history charts** — temperature / power / usage graphs split
  into separate tabs instead of one crowded chart
- **Collapsible cards** — every card can be expanded/collapsed to save space
- **Sticky alerts** — active threshold breaches stay pinned at the top
  while they last, plus the in-app toast stack
- **Sensor-aware fallback** — cards render by sensor status; missing
  readings (e.g. iGPU load, RAM temperature on boards without those
  diodes) show `N/A` instead of stale or misleading values

### Security
- **On-demand audit** — produces a risk-scored report with findings
- **Live event stream** — WebSocket push of new ports, outbound
  connections to suspicious countries or Tor exits, failed logins, and
  Defender state changes
- **Persisted event history** — events are also appended to the
  `security_events` table in the history DB and can be replayed from
  `GET /api/security/events?limit=` (Security page: `LiveEventsLog` +
  `SecurityEventsLog`)
- **Risk scoring** (low / medium / high / critical) with weights from
  10+ heuristics (RDP exposure, unsigned listeners, Defender off, etc.)
- **Action buttons** — kill a process by PID, block an outbound IP via
  Windows Firewall, list and unblock rules
- **geoIP lookups** via ip-api.com with rate-limit-aware caching
- **Tor exit-node detection** (daily refreshed)
- **Suspicious countries watchlist** — editable in the UI, persisted
- **Export audit report** as PDF / HTML / JSON

### Alerts
- **Threshold alerts** with sustained-breach confirmation (no false
  alarms from momentary spikes) and per-rule cooldown: CPU/GPU
  temperature, RAM usage, disk-full level
- **Editable alert rules** — `AlertRulesCard` changes thresholds, sustained
  samples, cooldown and notification channels (toast / sound); saved to
  `backend/.cache/alert_rules.json` and hot-reloaded without a restart
  (`GET/PUT /api/alerts/rules`)
- **Native Windows Toast notifications** (zero extra dependencies) plus
  in-app toast stack on every page

> ℹ️ Some security features require running as Administrator:
> reading the Security event log (failed logins), creating firewall
> block rules, and killing processes owned by other users. The UI shows
> a banner when this is the case; non-admin features still work.

---

## 🌡️ Hardware temperatures & power (CPU/GPU/disk/power)

Windows does not expose raw hardware sensors to normal programs. This
dashboard reads them through **LibreHardwareMonitorLib** loaded directly
in-process (no GUI app needs to stay open).

Setup:

```powershell
# one-time install
winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor

# just run it — run.ps1 auto-elevates (one UAC prompt) so sensors are read
.\run.ps1
```

Notes:
- Without admin rights everything else still works — the cards simply
  show "Temperature unavailable".
- `start-sensors.ps1` can launch/verify a standalone LibreHardwareMonitor
  instance if you prefer the GUI route.
- Boards without a given diode report `N/A`: a stuck iGPU load
  (e.g. frozen at 100%) is filtered out, and RAM / iGPU temperatures
  with no sensor data show `N/A` instead of a fallback value.

---

## 📂 Project structure

```
Dashboard/
├── backend/
│   ├── main.py              FastAPI app, WebSocket endpoints, routes
│   ├── config.py            Settings + intervals
│   ├── metrics.py           psutil-based system metrics
│   ├── history.py           SQLite metrics history (sampler + queries)
│   ├── alerts.py            Threshold alerts + rules store + Windows Toast
│   ├── process_history.py   Per-process CPU/RAM samples (`process_samples`)
│   ├── disk_health.py       SMART (`Get-PhysicalDisk`) + disk_samples + forecast
│   ├── reports.py           Self-contained HTML daily/weekly report generator
│   ├── sensors_lhm.py       LibreHardwareMonitorLib interop (temps/power)
│   ├── speedtest_worker.py  On-demand Internet speed test
│   ├── maintenance/         Maintenance module (guards, error codes,
│   │                        PowerShell runner, scanner/system caches,
│   │                        actions, cleaner, history, export, relaunch, router)
│   ├── tests/               pytest suite (alerts/rules, history, parsers,
│   │                        maintenance, security events, process drilldown,
│   │                        relaunch, disk health, reports, retention, WS contract)
│   ├── requirements.txt
│   ├── security/
│   │   ├── audit.py         On-demand audit + finding rules
│   │   ├── monitor.py       Async background pollers → WS events
│   │   ├── actions.py       Kill process / block IP / list rules
│   │   ├── persistence.py   SQLite `security_events` history
│   │   ├── findings.py      Finding + risk-score classes
│   │   ├── geoip.py         ip-api.com lookup + Tor exit list
│   │   └── winapi.py        PowerShell wrappers (Defender, logins, etc.)
│   ├── exporters/
│   │   └── __init__.py      PDF / HTML / JSON report writers
│   └── .cache/              geoip cache, tor exits, alert_rules.json
├── reports/                 Generated self-contained HTML reports
├── scripts/                 Agent-log viewer tooling (see README-viewer.md):
│   ├── watch.py             live tail rebuild loop (`?auto=1` LIVE badge)
│   ├── compare.py           base vs candidate run comparison (exit 1 on regression)
│   ├── cost.py              token/cost per model (+ `--budget` gate)
│   └── retention.py         archive/prune old JSONL rows
└── frontend/
    ├── package.json
    ├── vite.config.ts       proxy /api and /ws → 127.0.0.1:8000
    ├── vitest.config.ts     unit-test config
    ├── tsconfig.json
    ├── tests/               vitest suites (format, security store, settings)
    └── src/
        ├── main.ts          App bootstrap + router
        ├── App.vue          Layout + global styles
        ├── pages/
        │   ├── Dashboard.vue
        │   ├── Security.vue
        │   └── Maintenance.vue
        ├── components/
        │   ├── dashboard/   CpuCard, RamCard, DiskCard, NetworkCard,
        │   │                 GpuCard, AdaptersCard, HistoryCard,
        │   │                 ProcessesCard, ProcessDetailPanel,
        │   │                 SystemCard, SpeedtestCard, PowerCard,
        │   │                 AlertsCard, AlertRulesCard, HealthStrip
        │   ├── security/    AuditCard, PortsCard, ConnectionsCard,
        │   │                 DefenderCard, FailedLoginsCard,
        │   │                 LiveEventsLog, SecurityEventsLog,
        │   │                 SettingsPanel, BlockedRulesCard
        │   └── maintenance/ MaintenanceTable, MaintenancePanel,
        │                     MaintenanceHistory, MaintenanceAdminBanner,
        │                     DiskHealthCard, ReportsCard
        ├── composables/      useWebSocket, format helpers
        ├── directives/       autoTip (hover tooltips on clipped text)
        ├── utils/            format.ts (bytes / duration / percent)
        └── stores/          metrics.ts, history.ts, security.ts,
                              maintenance.ts (Pinia)
```

---

## 📈 Metrics history

A background sampler writes one row of cheap scalar metrics to
`backend/.cache/history.db` (SQLite, WAL mode) every
`HISTORY_SAMPLE_INTERVAL` seconds. The **History** card on the dashboard
queries bucketed averages (~360 points max) for the selected range.

- Ranges: `1h` (10 s buckets), `6h` (60 s), `24h` (240 s)
- Series: CPU/RAM/swap %, CPU/GPU/disk-max temperatures,
  CPU W / GPU W power draw, network & disk throughput (MB/s)
- Rows older than `HISTORY_RETENTION_HOURS` are deleted automatically
  (≈ <1 MB/day of disk usage)
- Temperatures/power are `NULL` when not running elevated — the chart
  shows gaps and a hint instead
- By default 6 of 11 series are shown (CPU/RAM %, CPU/GPU °C, CPU/GPU W);
  use the range buttons (`1H` / `6H` / `24H`) to switch windows and the
  series chips to toggle lines (choice persists in `localStorage`)

---

## 🚀 How to start (one script)

```powershell
# from a normal shell — installs deps, builds frontend, starts server
# (run from the repo root, i.e. the folder containing run.ps1)
.\run.ps1
```

Open **http://127.0.0.1:8000** in your browser.

Optional flags:

| Flag        | What it does                                |
|-------------|---------------------------------------------|
| `-Dev`      | Run backend (8000) and frontend HMR (5173) in two windows |
| `-Install`  | Reinstall backend + frontend dependencies    |
| `-Clean`    | Wipe `backend\.cache` and Python `__pycache__` (keeps deps) |

For full security features (failed logins, firewall block rules,
killing privileged processes) `run.ps1` automatically relaunches itself
elevated (a single UAC prompt) — just run `.\run.ps1` normally.

### Manual setup (alternative)

If you'd rather run the steps yourself:

```powershell
# 1. Install backend dependencies
cd backend
python -m pip install -r requirements.txt

# 2. Build the frontend (production)
cd ..\frontend
npm install
npm run build

# 3. Run the server
cd ..\backend
python main.py
```

---

## 🔧 Development mode (hot reload)

Two processes during development:

```powershell
# Terminal 1 — backend
cd backend
python main.py

# Terminal 2 — frontend with HMR
cd ..\frontend
npm run dev
```

Open **http://localhost:5173** — Vite proxies `/api` and `/ws` to
`127.0.0.1:8000` automatically.

---

## 🔌 API reference

| Method | Path                          | Purpose                                   |
|--------|-------------------------------|-------------------------------------------|
| GET    | `/` (and any non-API path)    | SPA frontend (served from `frontend/dist`) |
| GET    | `/api/system`                 | Initial system snapshot                   |
| GET    | `/api/sensors/status`         | LibreHardwareMonitor init status (availability / elevation) |
| GET    | `/api/history?range=1h|6h|24h`| Bucketed metrics history (~360 points)    |
| GET    | `/api/processes/{pid}`        | Process detail + 3-level tree + listening ports |
| GET    | `/api/processes/{pid}/history?limit=60` | Per-process CPU/RAM samples (1–240) |
| GET    | `/api/health/disk`            | Per-volume usage, SMART health, days-to-full forecast |
| POST   | `/api/speedtest`              | Trigger an Internet speed test            |
| GET    | `/api/alerts/rules`           | Effective alert rules + notification channels |
| PUT    | `/api/alerts/rules`           | Replace rules + channels (validated, hot-reload) |
| GET    | `/api/security/suspicious`    | List currently-flagged country codes      |
| PUT    | `/api/security/suspicious`    | Override suspicious-countries list        |
| POST   | `/api/security/audit`         | Run an on-demand audit; returns full report |
| POST   | `/api/security/kill`          | Kill a process by PID (body: `{pid}`) (admin) |
| POST   | `/api/security/block`         | Add Windows firewall block rule (`{ip}`) (admin) |
| POST   | `/api/security/unblock`       | Delete a block rule (`{rule_name}`) (admin) |
| GET    | `/api/security/blocked`       | List all `WindySmartDashboard_block_*` rules |
| GET    | `/api/security/events?limit=50` | Persisted security event history, newest first (admin) |
| POST   | `/api/security/export`        | Export audit (body: `{fmt, report}`)     |
| POST   | `/api/reports/generate`       | Generate `{"days": 1|7}` self-contained HTML report (admin) |
| GET    | `/api/reports`                | List generated reports, newest first (admin) |
| GET    | `/api/reports/{name}`         | Download one generated report (admin)     |
| WS     | `/ws/metrics`                 | Live metrics push (1 Hz)                  |
| WS     | `/ws/security`                | Live security events push                 |

> 🔐 Endpoints marked **(admin)** call `require_admin`: when
> `DASH_ADMIN_TOKEN` is set they require `X-Admin-Token: <token>`; when it is
> empty only loopback (`127.0.0.1` / `::1`) requests are accepted.

---

## ⚙️ Configuration

Settings live in `backend/config.py` and can be overridden via
environment variables:

| Variable                   | Default | Description                              |
|----------------------------|---------|------------------------------------------|
| `DASH_HOST`                | 127.0.0.1 | Bind host (keep `127.0.0.1` for safety) |
| `DASH_PORT`                | 8000    | Bind port                                |
| `DASH_METRICS_INTERVAL`    | 1.0     | Push interval in seconds                 |
| `DASH_PROCESS_INTERVAL`    | 3.0     | Top-N process push interval              |
| `DASH_PING_TARGET`         | 1.1.1.1 | Quick TCP connect target for latency    |
| `DASH_HISTORY_INTERVAL`    | 10.0    | History sampling interval (seconds)     |
| `DASH_HISTORY_RETENTION`   | 24      | Hours of history to keep                |
| `DASH_HISTORY_MAX_POINTS`  | 360     | Max points returned per /api/history    |
| `DASH_ALERTS`              | 1       | Set `0` to disable alerting             |
| `DASH_ALERT_CPU_TEMP`      | 85      | CPU temperature alert threshold (°C)    |
| `DASH_ALERT_GPU_TEMP`      | 85      | GPU temperature alert threshold (°C)    |
| `DASH_ALERT_RAM_PCT`       | 95      | RAM usage alert threshold (%)           |
| `DASH_ALERT_DISK_PCT`      | 90      | Disk usage alert threshold (%)          |
| `DASH_ALERT_SUSTAINED`     | 3       | Consecutive samples required to fire    |
| `DASH_ALERT_COOLDOWN`      | 300     | Seconds between repeat alerts per rule  |
| `DASH_ADMIN_TOKEN`         | *(empty)* | Require `X-Admin-Token` on admin endpoints; empty = loopback-only |
| `DASH_REPORT_INTERVAL_HOURS` | 24    | Hours between scheduled HTML reports (`<=0` disables) |

---

## 🧰 Maintenance module

Windows housekeeping ported from the legacy `updater` project
(`MERGE-005b`). The backend lives in `backend/maintenance/` (module version
`0.3.1`: guards, 22 error codes, PowerShell runner, scanner cache 30 s,
system cache 60 s, actions, cleaner, history, export, relaunch, router) and
exposes device/driver scan status, action history, CSV/JSON export, a guarded
cleaner for temp folders and the recycle bin, and a confirmed relaunch.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/maintenance/status` | Cached system + scanner status |
| GET | `/api/maintenance/scan?refresh=1` | Device/driver scan (`refresh=1` bypasses the 30 s cache) |
| GET | `/api/maintenance/history?limit=100` | Recent rows from the `maintenance_actions` table (SQLite `HISTORY_DB`) |
| GET | `/api/maintenance/clean/summary` | Read-only size preview per cleanup target (`categories`, `totalBytes`) |
| POST | `/api/maintenance/action` | `{action}` → `wu-scan` or `pnputil-scan` |
| POST | `/api/maintenance/clean` | `{targets, confirm:true}` → `user-temp`, `windows-temp`, `recycle-bin` |
| POST | `/api/maintenance/export` | `{kind, format}` → devices/history × csv/json |
| POST | `/api/maintenance/relaunch` | `{confirm:"relaunch"}` → `202` + detached helper; the page polls until the backend reconnects |

Access control:

- Host allowlist: `127.0.0.1`, `localhost`, `::1` only.
- Every `POST` must send `X-Requested-With: windy-dashboard` (CSRF guard).
- `require_admin`: when `DASH_ADMIN_TOKEN` is set, `X-Admin-Token` is
  required; otherwise only loopback requests are accepted.

UI: route `/maintenance` (`frontend/src/main.ts`) renders
`pages/Maintenance.vue` with `components/maintenance/`
(`MaintenanceTable`, `MaintenancePanel`, `MaintenanceHistory`,
`MaintenanceAdminBanner`, `DiskHealthCard`, `ReportsCard`) and the Pinia
store `stores/maintenance.ts`.
Sort choice persists in `localStorage['dashboard:maintenance:sort']`;
an admin token (if used) is stored in `localStorage['dashboard:adminToken']`.

Tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

> ⛔ Maintenance never auto-installs or auto-updates anything. `wu-scan`
> and `pnputil-scan` are read-only scans and `clean` requires
> `confirm: true`. `relaunch` is enabled but guarded: the body must be
> `{"confirm":"relaunch"}`, the server returns `202` and starts a detached
> helper, and the page polls `GET /api/maintenance/status` until the backend
> reconnects (60 s timeout).

---

## 🧪 Testing

Backend unit tests (pytest) cover the alert engine, history bucketing,
and parsing helpers:

```powershell
cd backend
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

Lint the backend anytime with:

```powershell
cd backend
.\.venv\Scripts\ruff.exe check .
```

---

## 🛡️ Scope and limitations

This dashboard only inspects the **local machine**. It does **not**
scan other hosts, penetrate networks, capture credentials, or perform
any offensive operation. The security module is a defensive audit /
live-monitoring tool intended for self-checking; its action buttons
(kill process, block outbound IP) operate only on this computer.

On Windows 10/11 without Administrator privileges, the following
features are degraded:

- Failed-login history (Security log requires admin)
- Creating/deleting firewall block rules
- Killing processes owned by other users

Other features (metrics, audit, geoIP, TOR detection) work without
elevation. The UI shows a banner so you know what to expect.

---

## 📓 Notes

- ip-api.com free tier allows ~40 req/min; lookups are cached for
  10 minutes per IP and rate-limited gracefully.
- The Tor exit list is refreshed once per day from
  `https://check.torproject.org/torbulkexitlist` and cached locally.
- Reports are also saved to `backend/.cache/reports/` when exported.

---

## 📜 License

Released under the [MIT License](LICENSE). Use at your own risk; do not run
the security audit against systems you do not own.
