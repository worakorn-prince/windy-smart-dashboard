# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
