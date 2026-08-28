# Design: Historical Metrics & Graphs (Temps + Power)

## Goals
เก็บ metrics ย้อนหลังฝั่ง server (SQLite WAL) ทุก 10s นาน 24 ชม. + กราฟ uPlot
ช่วง 1H/6H/24H รวม **อุณหภูมิ (CPU/GPU/Disk-max) และการใช้พลังงาน (CPU W / GPU W)**

## Architecture
[history task] --10s--> metrics.light_snapshot() --> SQLite(WAL) --retention 24h-->
GET /api/history?range=1h|6h|24h (SQL bucketed AVG ~360 pts) --> stores/history.ts --> HistoryCard.vue (uPlot)

## Backend Changes
### config.py (+6 lines)
HISTORY_DB = CACHE_DIR / "history.db"
HISTORY_SAMPLE_INTERVAL = float(os.environ.get("DASH_HISTORY_INTERVAL", "10.0"))
HISTORY_RETENTION_HOURS = int(os.environ.get("DASH_HISTORY_RETENTION", "24"))
HISTORY_MAX_POINTS = 360

### history.py (NEW ~130 lines)
- Schema:
  CREATE TABLE samples(
    ts REAL PRIMARY KEY,
    cpu_pct REAL, ram_pct REAL, swap_pct REAL,
    cpu_temp REAL, gpu_temp REAL, disk_temp_max REAL,
    cpu_power_w REAL, gpu_power_w REAL,
    net_sent_bps REAL, net_recv_bps REAL,
    disk_read_bps REAL, disk_write_bps REAL);
  NULLs allowed (sensor missing / not elevated).
- Single writer connection via asyncio.to_thread + threading.Lock; readers short-lived.
- record_sample(): own prev counters for net/disk rates (psutil.net_io_counters /
  disk_io_counters) — MUST NOT call metrics.disk_snapshot()/network_snapshot()
  (would corrupt _last_disk_ts/_last_net_ts rate fix).
- Temps/power: reuse metrics._get_hw_sensors() (5s cache), _get_cpu_temperature(),
  _get_gpu_sensors_lhm(); disk_temp_max = max(_get_disk_temperatures().values())
- query_range(range): bucket = range_sec/360 → SQL GROUP BY CAST(ts/bucket AS INT), AVG()
- cleanup: DELETE ts < now-retention hourly.

### metrics.py (+~35 lines)
light_snapshot() -> {cpu_pct, ram_pct, swap_pct, cpu_temp, gpu_temp, disk_temp_max,
cpu_power_w, gpu_power_w} — cheap psutil + cached sensors only.

### main.py (+~25 lines)
- lifespan: history_task = create_task(_history_loop()); add to cancel tuple.
- _history_loop(): sleep HISTORY_SAMPLE_INTERVAL → to_thread(history.record_sample); hourly cleanup.
- GET /api/history?range=1h|6h|24h → {range, bucket_sec, points:[{ts,...}], count}

## Frontend Changes
- npm i uplot (~10KB gzip)
- stores/history.ts (NEW): {range:'1h', points:[], loading} + fetch()
- components/dashboard/HistoryCard.vue (NEW ~160 lines):
  * Range buttons 1H|6H|24H; series toggle chips grouped by unit
  * uPlot multi-scale: "%" (cpu_pct,ram_pct), "W" (cpu_power_w,gpu_power_w), "°C" (temps), "MB/s" (net/disk)
  * NULL → gap; auto-refresh 60s; pause on document.hidden; dark theme via CSS vars
- pages/Dashboard.vue: <HistoryCard /> first item in .grid.wide

## Subtasks
Phase A (backend, ~1 session): A1 config → A2 history.py → A3 light_snapshot →
A4 main.py task+endpoint → A5 verify (uptime 1 min, curl /api/history?range=1h ≥ 5 rows)
Phase B (frontend, ~1 session): B1 uplot → B2 store → B3 HistoryCard → B4 wire → B5 build+visual
Phase C (polish, ~30 min): C1 gap handling → C2 refresh/visibility → C3 README

## Risks & Mitigations
1. SQLite contention → WAL + single writer + to_thread
2. Rate interference → sampler keeps OWN counters (do NOT touch metrics globals)
3. Not elevated → temp/power NULL → chart gaps + hint text
4. Unit confusion CPU W vs GPU W → shared "W" scale + labeled chips
5. DB growth ~<1MB/day → retention caps ~24MB

## Acceptance Criteria
- /api/history?range=1h returns ≥50 points after 10 min uptime
- Charts render all 3 ranges; data survives reload
- Temps & power series visible when elevated; graceful gaps when not
- WS 1Hz latency unchanged; ruff check still passes; npm build OK