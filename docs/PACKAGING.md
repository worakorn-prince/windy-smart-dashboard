# Portable Packaging Guide

This document describes how to build and run the **portable package** — a single `.zip` that contains everything needed to run the Windy Smart Dashboard on another Windows machine using only Python (no Node.js required).

---

## What's in the Package

| Included | Reason |
|----------|--------|
| `backend/**/*.py` + `backend/requirements*.txt` | Application code + Python dependencies |
| `frontend/dist/**` | Pre-built Vue/Vite production assets (HTML, JS, CSS) |
| `scripts/*.py` | CLI tooling (metrics, export, aggregate, compare, cost, retention, etc.) |
| `scopeboard/index.html`, `scopeboard/all.html` | Static agent-observability viewer (no build needed) |
| `run_dashboard.bat`, `run.bat`, `run.ps1`, `run_dashboard.sh` | Launchers (Windows + POSIX) |
| `README.md`, `README-viewer.md`, `README.th.md`, `LICENSE` | Documentation + license |
| `docs/PACKAGING.md` | This guide |
| `MANIFEST.json` (auto-generated) | File list with SHA-256 hashes for integrity verification |

### Excluded (and Why — Security / Size)

| Excluded | Reason |
|----------|--------|
| `backend/.cache/` | Runtime caches (geoIP, Tor exits, alert rules, history DB, reports) — contain machine-specific data |
| `backend/__pycache__/` | Compiled bytecode — regenerated on first run |
| `frontend/src/`, `frontend/tests/`, `frontend/e2e/` | Source code + tests — not needed at runtime |
| `frontend/node_modules/` | Node dependencies — only needed for building |
| `scopeboard/*.json` | Runtime datasets (agent logs) — contain private task/session data |
| `*.db`, `*.pyc`, `opencode.json`, `.mcp.json`, `.agent/` | Local config / caches / agent state — never ship |
| `dist/`, `playwright-report/`, `test-results/` | Build artifacts / test outputs |
| `.venv/`, `.git/` | Environment / VCS — irrelevant on target |

> **Security note:** The package deliberately omits all runtime data (`.agent/`, `backend/.cache/`, `scopeboard/*.json`, `*.db`) to prevent leaking task history, session IDs, tokens, or machine-specific caches.

---

## Building the Package

### Prerequisites
1. **Frontend must be built first** (produces `frontend/dist/`):
   ```powershell
   cd frontend
   npm install
   npm run build
   ```
2. Python 3.11+ with `zipfile`, `hashlib`, `json`, `argparse` (all stdlib)

### Build Command
```powershell
# From repository root
python scripts/package_portable.py --out dist/windy-dashboard-portable-v0.5.0.zip
```

#### Options
| Flag | Description |
|------|-------------|
| `--root <path>` | Project root to package (default: repo root) |
| `--out <path>` | Output zip path (default: `dist/windy-dashboard-portable-v<version>.zip`) |
| `--version <str>` | Package version (default: read from `frontend/package.json`) |
| `--dry-run` | Print plan (file counts, sizes, groups) without writing zip |
| `--skip-verify` | Allow building without `frontend/dist` (backend-only package) |

#### Example: Dry Run
```powershell
python scripts/package_portable.py --dry-run
```
Output:
```
Portable package plan (dry-run, nothing written)
  name        : windy-smart-dashboard
  version     : 0.5.0
  python      : 3.12.7
  out         : D:\...\dist\windy-dashboard-portable-v0.5.0.zip
  files       : 247
  total size  : 12.4 MiB
  groups      :
    backend           89
    frontend          42
    scripts           18
    scopeboard         2
    (root)             8
```

---

## Running on the Target Machine

### Prerequisites (Target)
- **Windows 10/11** (the dashboard uses Windows-specific APIs: LibreHardwareMonitorLib, Firewall, Defender, Security Event Log)
- **Python 3.11+** on `PATH`
- **LibreHardwareMonitor** (optional, for CPU/GPU/disk temperatures & power):
  ```powershell
  winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor
  ```
- **Administrator rights** (for full sensor + security features; `run.ps1` auto-elevates via UAC)

### Steps
```powershell
# 1. Extract the zip
Expand-Archive windy-dashboard-portable-v0.5.0.zip -DestinationPath windy-dashboard
cd windy-dashboard

# 2. Create virtual environment & install Python deps
python -m venv .venv
.venv\Scripts\pip.exe install -r backend/requirements.txt

# 3. Run (auto-elevates for sensors)
.\run_dashboard.bat
# or directly:
.\run.ps1
```

The dashboard opens at **http://127.0.0.1:8000**.

### Non-Windows Note
This package **only runs on Windows**. The backend uses `pythonnet` to load `LibreHardwareMonitorLib.dll` (COM), calls Windows Firewall / Defender / Security Event Log APIs, and uses Windows Toast notifications. These have no Linux/macOS equivalent.

---

## Package Manifest (`MANIFEST.json`)

Every package includes a `MANIFEST.json` as the **first entry** in the zip. Structure:

```json
{
  "name": "windy-smart-dashboard",
  "version": "0.5.0",
  "builtAt": "2026-11-11T12:34:56Z",
  "python": "3.12.7",
  "counts": { "files": 247, "totalBytes": 12987654 },
  "files": [
    { "path": "backend/main.py", "size": 45231, "sha256": "a1b2c3..." },
    { "path": "frontend/dist/index.html", "size": 2048, "sha256": "d4e5f6..." }
    ...
  ]
}
```

### Verification
```powershell
# Verify integrity of extracted package
python -c "
import hashlib, json, sys
with open('MANIFEST.json') as f: m = json.load(f)
for entry in m['files']:
    with open(entry['path'], 'rb') as fh:
        h = hashlib.sha256(fh.read()).hexdigest()
    if h != entry['sha256']:
        print(f'MISMATCH: {entry[\"path\"]}')
        sys.exit(1)
print('All files verified OK')
"
```

---

## CI Integration

The `packaging-tests` job in `.github/workflows/ci.yml` runs `python scripts/test_packaging.py` on every push/PR to validate:
- File collection logic (includes/excludes)
- `FRONTEND_NOT_BUILT` error handling
- Manifest version/counts/hashes
- Zip creation with `MANIFEST.json` first, no runtime data
- `--dry-run` CLI behavior

No `npm run build` in CI for this job — tests use a temporary fake repo.

---

## Approximate Package Size

| Component | Typical Size |
|-----------|--------------|
| `backend/` (Python code + requirements) | ~2–3 MB |
| `frontend/dist/` (built Vue assets) | ~8–12 MB |
| `scripts/` | ~200 KB |
| `scopeboard/` | ~500 KB |
| Root files (README, launchers, license) | ~100 KB |
| **Total (zip, compressed)** | **~10–15 MB** |

---

## Supported Python Versions

- **3.11+** (tested on 3.11, 3.12)
- Uses only stdlib modules: `zipfile`, `hashlib`, `json`, `argparse`, `pathlib`, `datetime`, `platform`, `fnmatch`

---

## Limitations

| Limitation | Details |
|------------|---------|
| **Windows only** | Backend uses `pythonnet` + COM for hardware sensors; Windows Firewall / Defender / Security Log APIs |
| **Requires Python** | Target machine must have Python 3.11+ installed |
| **Sensors need LHM** | Without LibreHardwareMonitor, temperature/power cards show "N/A" |
| **Admin for full features** | Failed logins, firewall block rules, killing other users' processes need elevation |
| **No Node.js** | Frontend is pre-built; no `npm` or `node` needed on target |
| **No auto-update** | Package is a snapshot; re-build to update |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `FRONTEND_NOT_BUILT` | Run `cd frontend && npm install && npm run build` first |
| `ModuleNotFoundError` | Ensure `.venv\Scripts\pip.exe install -r backend/requirements.txt` ran |
| Sensors show "unavailable" | Install LibreHardwareMonitor + run as Administrator (run.ps1 auto-elevates) |
| Port 8000 in use | Set `DASH_PORT` env var: `$env:DASH_PORT=8080; .\run.ps1` |
| Zip extraction fails | Use `Expand-Archive` (PowerShell 5+) or 7-Zip; avoid paths > 260 chars |

---

## License

The portable package is released under the same **MIT License** as the source (see `LICENSE`).