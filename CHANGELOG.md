# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-10-21

### Added

- Alert rule management: `GET/PUT /api/alerts/rules`, persistent rules store (`backend/.cache/alert_rules.json`), per-channel toggles (toast/sound), hot-reload, and an Alert Rules card on the dashboard.
- Security event history: `GET /api/security/events` backed by SQLite (`security_events`), plus live and persisted event logs on the Security page.
- Process drilldown: `GET /api/processes/{pid}` (status, tree, listening ports) and `GET /api/processes/{pid}/history` backed by `process_samples`, with a uPlot detail panel.
- Disk health: `GET /api/health/disk` with SMART status (PowerShell `Get-PhysicalDisk`) and days-to-full prediction from `disk_samples`.
- Scheduled reports: `POST /api/reports/generate` (daily/weekly), `GET /api/reports` and `GET /api/reports/{name}`, background scheduler (`DASH_REPORT_INTERVAL_HOURS`, default 24, ≤ 0 disables), self-contained HTML output in `reports/`.
- Viewer tooling: `scripts/watch.py` (live tail, `?auto=1` LIVE badge), `scripts/compare.py` (run-to-run regression detection, exit 1 on regression), `scripts/cost.py` (token/cost analytics per model with `--budget`), `scripts/retention.py` (archive old JSONL rows).
- Frontend test suite (vitest + @vue/test-utils + jsdom): 26 tests across format utils, security store, and SettingsPanel.

### Changed

- `POST /api/maintenance/relaunch` is implemented (previously `501 RELAUNCH_DISABLED`): requires `{"confirm":"relaunch"}`, returns `202`, uses a detached helper script, and the Maintenance page polls for reconnect (60 s) behind a typed confirmation modal.
- History retention: `backend/history.py prune --days` and daily auto-prune via `DASH_HISTORY_DAYS` (default 30).
- Maintenance module bumped to 0.3.1; docs synced across `README.md`, `README-viewer.md`, `docs/MAINTENANCE-MODULE.md`, `docs/BENCHMARKS.md`.

### Security

- XSS hardening: exporters and static viewer escape all rendered values.
- Canonical WebSocket `security_event` envelope, admin token support (`sessionStorage`), and `authHeaders` on security actions.
- CSV export neutralizes spreadsheet formula injection; export failures return actionable 400 details.
- CI runs ruff, backend pytest (228), viewer tests (32), frontend vitest (26), and a production build on every push/PR.

### Fixed

- Viewer metrics: single-pass computation for metrics/failure/observability with a `malformed_rows` counter.
- 23 ruff findings in the maintenance module, behavior-preserving.

## [0.3.1] - 2026-10-20

### Added

- `GET /api/maintenance/clean/summary` — read-only size preview for `user-temp`, `windows-temp`, and `recycle-bin` (`categories`, `totalBytes`, `durationMs`) with a `clean-summary` history row.
- "Size before cleanup" card on `/maintenance` (per-target path + size, total, refresh) and a "clean all" button that still requires the existing confirmation step.
- `frontend/src/utils/format.ts` (`formatBytes`, `formatDuration`, `formatPercent`) used for memory, disk, freed bytes, and durations.

### Changed

- `/maintenance` now renders memory/disk as human-readable values (`12.3 GB / 31.2 GB (39%)`) instead of raw bytes.
- `downloadExport` surfaces `detail.code` / `text` / `hint` and explains `403` admin/host failures; `runClean(targets, confirm)` takes the confirmation from the caller instead of hard-coding `confirm: true` in the store.

### Security

- CSV export neutralizes spreadsheet formula injection: cells starting with `=`, `+`, `-`, `@`, tab, or CR get a leading `'`.
- `testserver` is no longer part of the production host allowlist; it is accepted only while `DASH_TEST_MODE=1` (set by `tests/conftest.py`).

## [0.3.0] - 2026-10-20

### Added

- Maintenance module (`backend/maintenance/`): guards, 22 error codes, PowerShell runner, scanner cache (30 s) and system cache (60 s), actions, cleaner, history, export, and router.
- Endpoints: `GET /api/maintenance/status`, `GET /api/maintenance/scan?refresh=1`, `GET /api/maintenance/history?limit=100`, `POST /api/maintenance/action`, `POST /api/maintenance/clean`, `POST /api/maintenance/export`, `POST /api/maintenance/relaunch`.
- Frontend `/maintenance` route with `pages/Maintenance.vue`, `components/maintenance/` (`MaintenanceTable`, `MaintenancePanel`, `MaintenanceHistory`, `MaintenanceAdminBanner`), and Pinia store `stores/maintenance.ts`.
- Sort persistence in `localStorage['dashboard:maintenance:sort']`; optional admin token in `localStorage['dashboard:adminToken']`.
- Guards: host allowlist (`127.0.0.1` / `localhost` / `::1`), `X-Requested-With: windy-dashboard` required on every `POST`, and `require_admin` (`X-Admin-Token` when `DASH_ADMIN_TOKEN` is set, loopback-only otherwise).
- Parity test `tests/test_parity_updater.py` with fixtures in `tests/fixtures/`.

### Deviations from the legacy `updater` (intentional)

1. 22 error codes instead of 25 (upstream has 22).
2. `open-devmgmt` removed → `UNSUPPORTED_ACTION`.
3. `relaunch` permanently disabled → `501 RELAUNCH_DISABLED`.
4. Added `GET /api/maintenance/history`.
5. History stored in SQLite table `maintenance_actions` (`HISTORY_DB`) instead of JSON.
6. No separate cleanup size-summary endpoint — `/clean` only.

### Tests

- `python -m pytest tests -q` → **87 passed**.
- Review follow-up (MERGE-006a): export now validates `kind`/`format` before scanning (400 `INVALID_EXPORT`), `parse_json_list` raises instead of silently returning `[]` on unparseable output, dead cleanup-summary code removed, `MODULE_STAGE = "write"`, and `tests/conftest.py` isolates `HISTORY_DB` per test module so tests no longer write to the real cache DB.

### Known notes (not blocking)

- CSV export does not yet neutralise spreadsheet formula injection (`=`, `+`, `-`, `@`) — same behaviour as the legacy updater.
- `ALLOWED_HOSTS` includes `testserver` for the FastAPI TestClient; production traffic still has to pass the host allowlist.
- CSRF relies on the custom `X-Requested-With` header (no Origin/Referer check), which is sufficient because custom headers trigger a CORS preflight.
- The maintenance guard dependencies are attached per route; new routes must add them explicitly.

## [0.2.0] - 2026-09-13

### Added

- Health strip summary bar pinned at the top of the dashboard (CPU / RAM / disk / top temperatures).
- Dark / light mode toggle in the header, persisted in `localStorage`.
- Tabbed history charts splitting temperature / power / usage graphs into separate tabs.
- Collapsible dashboard cards to save screen space.
- Sticky alert card keeping active threshold breaches pinned while they last.
- Hero cards for key metrics, responsive layout, and 12px base font for dense tables.
- Live-tick store merge so incoming WebSocket ticks merge into state without flicker or data loss.

### Fixed

- History SQLite schema fixed from 15 back to 13 columns with v3 migration.
- LHM sensor matching: normalized sensor types, `intelcpu` / `amdcpu` keywords, excluded GPU Core readings mixed into CPU temperature, filtered stuck iGPU load at 100%, and sanitized sensor status.
- Frontend renders by sensor status; missing iGPU / RAM readings show `N/A` instead of stale values.
