# Windy Smart Dashboard

> 🇹🇭 ไทย: [README.th.md](README.th.md)

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
  and fan speeds
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

## ✨ Features

### Dashboard
- CPU usage (overall + per-core bars) and frequency
- Memory usage (RAM + swap)
- Disk usage per partition + read/write throughput
- Network interfaces + live upload/download rate
- Top 10 processes (sortable by CPU/RAM)
- System info (hostname, OS, processor, uptime, boot time)
- Internet speedtest **on-demand** (button — uses bandwidth, not polled)
  Implemented against Cloudflare's free `speed.cloudflare.com` endpoint
  (no API key, no rate limit).
- Live ping latency to a configurable target
- **Metrics history** — every metric is sampled to a local SQLite DB
  every 10 s and charted over the last **1 h / 6 h / 24 h**, including
  CPU/GPU/disk temperatures and fan speeds (CPU RPM / GPU %), with
  per-series toggles and multiple y-axes

### Security
- **On-demand audit** — produces a risk-scored report with findings
- **Live event stream** — WebSocket push of new ports, outbound
  connections to suspicious countries or Tor exits, failed logins, and
  Defender state changes
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
- **Native Windows Toast notifications** (zero extra dependencies) plus
  in-app toast stack on every page

> ℹ️ Some security features require running as Administrator:
> reading the Security event log (failed logins), creating firewall
> block rules, and killing processes owned by other users. The UI shows
> a banner when this is the case; non-admin features still work.

---

## 🌡️ Hardware temperatures (CPU/GPU/disk/power/fan)

Windows does not expose raw hardware sensors to normal programs. This
dashboard reads them through **LibreHardwareMonitorLib** loaded directly
in-process (no GUI app needs to stay open).

Setup:

```powershell
# one-time install
winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor

# run the dashboard as Administrator so sensors can be read
.\run.ps1   # from an elevated PowerShell window
```

Notes:
- Without admin rights everything else still works — the cards simply
  show "Temperature unavailable".
- `start-sensors.ps1` can launch/verify a standalone LibreHardwareMonitor
  instance if you prefer the GUI route.
- AMD iGPU (Vega) has no own thermal diode reading here; the dashboard
  falls back to the CPU's GFX temperature.

---

## 📂 Project structure

```
Dashboard/
├── backend/
│   ├── main.py              FastAPI app, WebSocket endpoints, routes
│   ├── config.py            Settings + intervals
│   ├── metrics.py           psutil-based system metrics
│   ├── history.py           SQLite metrics history (sampler + queries)
│   ├── alerts.py            Threshold alerts + Windows Toast sender
│   ├── sensors_lhm.py       LibreHardwareMonitorLib interop (temps/fans)
│   ├── speedtest_worker.py  On-demand Internet speed test
│   ├── tests/               pytest suite (alerts, history, parsers)
│   ├── requirements.txt
│   ├── security/
│   │   ├── audit.py         On-demand audit + finding rules
│   │   ├── monitor.py       Async background pollers → WS events
│   │   ├── actions.py       Kill process / block IP / list rules
│   │   ├── findings.py      Finding + risk-score classes
│   │   ├── geoip.py         ip-api.com lookup + Tor exit list
│   │   └── winapi.py        PowerShell wrappers (Defender, logins, etc.)
│   ├── exporters/
│   │   └── __init__.py      PDF / HTML / JSON report writers
│   └── .cache/              geoip cache, tor exits, generated reports
└── frontend/
    ├── package.json
    ├── vite.config.ts       proxy /api and /ws → 127.0.0.1:8000
    ├── tsconfig.json
    └── src/
        ├── main.ts          App bootstrap + router
        ├── App.vue          Layout + global styles
        ├── pages/
        │   ├── Dashboard.vue
        │   └── Security.vue
        ├── components/
        │   ├── dashboard/   CpuCard, RamCard, DiskCard, NetworkCard,
        │   │                 GpuCard, AdaptersCard, HistoryCard,
        │   │                 ProcessesCard, SystemCard, SpeedtestCard
        │   └── security/    AuditCard, PortsCard, ConnectionsCard,
        │                     DefenderCard, FailedLoginsCard,
        │                     SecurityEventsLog, SettingsPanel,
        │                     BlockedRulesCard
        ├── composables/      useWebSocket, format helpers
        ├── directives/       autoTip (hover tooltips on clipped text)
        └── stores/          metrics.ts, history.ts, security.ts (Pinia)
```

---

## 📈 Metrics history

A background sampler writes one row of cheap scalar metrics to
`backend/.cache/history.db` (SQLite, WAL mode) every
`HISTORY_SAMPLE_INTERVAL` seconds. The **History** card on the dashboard
queries bucketed averages (~360 points max) for the selected range.

- Ranges: `1h` (10 s buckets), `6h` (60 s), `24h` (240 s)
- Series: CPU/RAM/swap %, CPU/GPU/disk-max temperatures,
  CPU fan RPM, GPU fan %, network & disk throughput (MB/s)
- Rows older than `HISTORY_RETENTION_HOURS` are deleted automatically
  (≈ <1 MB/day of disk usage)
- Temperatures/fans are `NULL` when not running elevated — the chart
  shows gaps and a hint instead
- On many AMD laptops the fan physically stops at idle (zero-RPM
  cooling); fan series stay empty until load spins it up

---

## 🚀 Quick start (one script)

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
killing privileged processes), launch a new terminal **as
Administrator** and run `.\run.ps1` from there.

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
| GET    | `/api/history?range=1h|6h|24h`| Bucketed metrics history (~360 points)    |
| POST   | `/api/speedtest`              | Trigger an Internet speed test            |
| GET    | `/api/security/suspicious`    | List currently-flagged country codes      |
| PUT    | `/api/security/suspicious`    | Override suspicious-countries list        |
| POST   | `/api/security/audit`         | Run an on-demand audit; returns full report |
| POST   | `/api/security/kill`          | Kill a process by PID (body: `{pid}`)     |
| POST   | `/api/security/block`         | Add Windows firewall block rule (`{ip}`)  |
| POST   | `/api/security/unblock`       | Delete a block rule (`{rule_name}`)       |
| GET    | `/api/security/blocked`       | List all `WindySmartDashboard_block_*` rules |
| POST   | `/api/security/export`        | Export audit (body: `{fmt, report}`)     |
| WS     | `/ws/metrics`                 | Live metrics push (1 Hz)                  |
| WS     | `/ws/security`                | Live security events push                 |

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
