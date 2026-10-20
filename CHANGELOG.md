# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
