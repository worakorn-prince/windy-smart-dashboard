import sqlite3
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

import config
import disk_health
import history
import insights_overview
import main
import process_history
from security import persistence as sec_persistence


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "h.db")
    history._conn = None
    process_history._conn = None
    disk_health._conn = None
    sec_persistence._conn = None
    yield
    for mod in (history, process_history, disk_health, sec_persistence):
        if mod._conn is not None:
            mod._conn.close()
            mod._conn = None


@pytest.fixture()
def client():
    return TestClient(main.app)


def _clear_insights_caches() -> None:
    for cache in main._insights_caches.values():
        cache.clear()


@pytest.fixture(autouse=True)
def _fresh_insights_caches():
    _clear_insights_caches()
    yield
    _clear_insights_caches()


# ---- samples (REAL epoch ts) seeding, same shape as test_insights_anomaly ---- #

_INSERT_SAMPLE_SQL = (
    "INSERT OR REPLACE INTO samples "
    "(ts, cpu_pct, ram_pct, swap_pct, cpu_temp, gpu_temp, disk_temp_max, "
    "cpu_power_w, gpu_power_w, net_sent_bps, net_recv_bps, "
    "disk_read_bps, disk_write_bps) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

_SAMPLE_COLS = ("ts", "cpu_pct", "ram_pct", "swap_pct", "cpu_temp", "gpu_temp",
                "disk_temp_max", "cpu_power_w", "gpu_power_w", "net_sent_bps",
                "net_recv_bps", "disk_read_bps", "disk_write_bps")

_SAMPLE_DEFAULTS: dict[str, float | None] = {
    "cpu_pct": 50.0, "ram_pct": 40.0, "swap_pct": 5.0, "cpu_temp": 60.0,
    "gpu_temp": None, "disk_temp_max": None, "cpu_power_w": None, "gpu_power_w": None,
    "net_sent_bps": 1000.0, "net_recv_bps": 2000.0,
    "disk_read_bps": 300_000.0, "disk_write_bps": 400_000.0,
}


def _insert_samples(rows: list[dict[str, Any]]) -> None:
    conn = history._get_conn()
    for values in rows:
        conn.execute(_INSERT_SAMPLE_SQL, tuple(values[c] for c in _SAMPLE_COLS))
    conn.commit()


# ---- TEXT-ISO ts helpers (formats must match each owner module) ---- #

def _micro_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sec_z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_iso(dt: datetime) -> str:
    return dt.isoformat()


def _recent_utc() -> datetime:
    """Owner modules stamp process/disk/maintenance rows with UTC."""
    return datetime.now(UTC) - timedelta(minutes=5)


def _recent_local() -> datetime:
    """security_events rows are stamped with local naive datetime.now()."""
    return datetime.now() - timedelta(minutes=5)


def _seed_processes(rows: list[dict[str, Any]]) -> None:
    assert process_history.record_samples(rows) == len(rows)


def _seed_disks(rows: list[dict[str, Any]]) -> None:
    assert disk_health.record_samples(rows) == len(rows)


def _seed_security(kind: str, ip: str, ts: str) -> None:
    assert sec_persistence.record_event(kind, ip, {"note": kind}, ts) is True


def _seed_maintenance(rows: list[tuple[str, str, int]]) -> None:
    with sqlite3.connect(config.HISTORY_DB) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS maintenance_actions("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts TEXT NOT NULL, action TEXT NOT NULL, target TEXT, "
            "ok INTEGER NOT NULL, duration_ms INTEGER, detail TEXT, error TEXT)"
        )
        conn.executemany(
            "INSERT INTO maintenance_actions(ts, action, target, ok, duration_ms, detail, error) "
            "VALUES (?, ?, NULL, ?, 0, NULL, NULL)",
            [(ts, action, ok) for action, ts, ok in rows],
        )
        conn.commit()


# ---- payload shape ---- #

_EXPECTED_KEYS = {"range", "generated_at", "effective_window", "trends", "disk",
                  "top_processes", "maintenance", "security", "baseline", "anomalies"}


def test_insights_payload_shape(tmp_db, client):
    now = time.time()
    _insert_samples([{**_SAMPLE_DEFAULTS, "ts": now - 30}])
    r = client.get("/api/insights", params={"range": "24h"})
    assert r.status_code == 200
    payload = r.json()
    assert set(payload.keys()) == _EXPECTED_KEYS
    assert payload["range"] == "24h"
    assert set(payload["trends"].keys()) == {"range", "bucket_sec", "count", "points"}
    assert set(payload["maintenance"].keys()) == {"total", "ok", "failed", "success_rate", "by_action"}
    assert set(payload["security"].keys()) == {"total", "by_kind", "top_sources"}
    assert payload["baseline"] != {}
    assert payload["anomalies"] == []


@pytest.mark.parametrize("rng", ["6h", "5m", "1h", "30m", "bogus", ""])
def test_insights_reject_unknown_range(client, rng):
    r = client.get("/api/insights", params={"range": rng})
    assert r.status_code == 422


@pytest.mark.parametrize("rng", ["24h", "7d", "30d"])
def test_insights_empty_db_returns_empty_payload(tmp_db, client, rng):
    r = client.get("/api/insights", params={"range": rng})
    assert r.status_code == 200
    payload = r.json()
    assert payload["range"] == rng
    assert payload["effective_window"] is None
    assert payload["trends"]["points"] == []
    assert payload["trends"]["count"] == 0
    assert payload["disk"] == []
    assert payload["top_processes"] == []
    assert payload["maintenance"] == {"total": 0, "ok": 0, "failed": 0,
                                      "success_rate": None, "by_action": []}
    assert payload["security"] == {"total": 0, "by_kind": [], "top_sources": []}
    assert payload["baseline"] == {}
    assert payload["anomalies"] == []


# ---- trends aggregate ---- #

def test_trends_bucketed_average_is_correct(tmp_db, client):
    bucket = 86400 // config.HISTORY_MAX_POINTS
    b0 = int(time.time() // bucket) * bucket
    rows = [
        {**_SAMPLE_DEFAULTS, "ts": b0 + 10.0, "cpu_pct": 10.0, "ram_pct": 40.0},
        {**_SAMPLE_DEFAULTS, "ts": b0 + 20.0, "cpu_pct": 20.0, "ram_pct": 60.0},
        {**_SAMPLE_DEFAULTS, "ts": b0 + 30.0, "cpu_pct": 30.0, "ram_pct": 80.0},
    ]
    _insert_samples(rows)
    r = client.get("/api/insights", params={"range": "24h"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["trends"]["bucket_sec"] == bucket
    assert payload["trends"]["count"] == 1
    point = payload["trends"]["points"][0]
    assert point["ts"] == b0
    assert point["cpu_pct"] == pytest.approx(20.0)
    assert point["ram_pct"] == pytest.approx(60.0)
    assert payload["effective_window"] == {"start": b0 + 10.0, "end": b0 + 30.0, "n": 3}


def test_trends_exclude_samples_outside_requested_range(tmp_db, client):
    _insert_samples([{**_SAMPLE_DEFAULTS, "ts": time.time() - 25 * 3600.0, "cpu_pct": 99.0}])
    recent_disk = _micro_z(_recent_utc())
    _seed_disks([{"ts": recent_disk, "mount": "C:\\", "used_gb": 42.0, "total_gb": 100.0}])
    r = client.get("/api/insights", params={"range": "24h"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["trends"]["points"] == []
    assert payload["effective_window"] is None
    assert payload["baseline"] == {}
    assert [d["mount"] for d in payload["disk"]] == ["C:\\"]
    assert payload["disk"][0]["used_gb"] == 42.0


# ---- disk aggregate ---- #

def test_disk_latest_avg_peak_and_delta(tmp_db, client):
    now = datetime.now(UTC)
    t1, t2, t3 = now - timedelta(hours=2), now - timedelta(hours=1), now - timedelta(minutes=30)
    _seed_disks([
        {"ts": _micro_z(t1), "mount": "C:\\", "used_gb": 10.0, "total_gb": 100.0},
        {"ts": _micro_z(t2), "mount": "C:\\", "used_gb": 15.0, "total_gb": 100.0},
        {"ts": _micro_z(t3), "mount": "C:\\", "used_gb": 20.0, "total_gb": 100.0},
        {"ts": _micro_z(now - timedelta(days=40)), "mount": "D:\\",
         "used_gb": 55.0, "total_gb": 200.0},
    ])
    r = client.get("/api/insights", params={"range": "30d"})
    assert r.status_code == 200
    disks = r.json()["disk"]
    assert [d["mount"] for d in disks] == ["C:\\"]
    disk = disks[0]
    assert disk["used_gb"] == 20.0
    assert disk["total_gb"] == 100.0
    assert disk["first_used_gb"] == 10.0
    assert disk["avg_used_gb"] == 15.0
    assert disk["peak_used_gb"] == 20.0
    assert disk["delta_gb"] == 10.0
    assert disk["n"] == 3
    assert disk["first_ts"] == _micro_z(t1)
    assert disk["last_ts"] == _micro_z(t3)


# ---- top processes aggregate ---- #

def test_top_processes_ranked_by_avg_cpu_with_peak_mem(tmp_db, client):
    ts = _micro_z(_recent_utc())
    rows: list[dict[str, Any]] = []
    for i in range(1, 13):
        name = f"p{i:02d}"
        rows.extend([
            {"ts": ts, "pid": i, "name": name, "cpu_pct": float(i), "mem_mb": float(i * 10)},
            {"ts": ts, "pid": i, "name": name, "cpu_pct": float(i), "mem_mb": float(i * 10 + 5)},
        ])
    rows.append({"ts": _micro_z(datetime.now(UTC) - timedelta(days=40)),
                 "pid": 999, "name": "ancient", "cpu_pct": 99.0, "mem_mb": 9999.0})
    _seed_processes(rows)
    r = client.get("/api/insights", params={"range": "24h"})
    assert r.status_code == 200
    procs = r.json()["top_processes"]
    assert len(procs) == insights_overview.TOP_PROCESSES_LIMIT
    assert procs[0] == {"name": "p12", "avg_cpu_pct": 12.0, "peak_mem_mb": 125.0, "n": 2}
    assert procs[-1]["name"] == "p03"
    names = {p["name"] for p in procs}
    assert "p01" not in names and "p02" not in names and "ancient" not in names


# ---- maintenance aggregate ---- #

def test_maintenance_counts_and_success_rate(tmp_db, client):
    recent = _sec_z(_recent_utc())
    old = _sec_z(datetime.now(UTC) - timedelta(days=40))
    _seed_maintenance([
        ("restart_service", recent, 1),
        ("restart_service", recent, 1),
        ("cleanup_temp", recent, 0),
        ("very_old_action", old, 1),
    ])
    r = client.get("/api/insights", params={"range": "24h"})
    assert r.status_code == 200
    maint = r.json()["maintenance"]
    assert maint["total"] == 3
    assert maint["ok"] == 2
    assert maint["failed"] == 1
    assert maint["success_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert maint["by_action"][0] == {"action": "restart_service", "count": 2, "ok": 2,
                                     "failed": 0, "success_rate": 1.0}
    assert maint["by_action"][1]["action"] == "cleanup_temp"
    assert maint["by_action"][1]["success_rate"] == 0.0


# ---- security aggregate ---- #

def test_security_counts_by_kind_and_top_sources_with_time_filter(tmp_db, client):
    recent = _local_iso(_recent_local())
    _seed_security("port_scan", "1.1.1.1", recent)
    _seed_security("port_scan", "1.1.1.1", recent)
    _seed_security("brute_force", "2.2.2.2", recent)
    _seed_security("port_scan", "", recent)
    _seed_security("old_kind", "9.9.9.9", "2026-01-01T00:00:00")
    r = client.get("/api/insights", params={"range": "24h"})
    assert r.status_code == 200
    security = r.json()["security"]
    assert security["total"] == 4
    assert security["by_kind"] == [{"kind": "port_scan", "count": 3},
                                   {"kind": "brute_force", "count": 1}]
    assert security["top_sources"] == [{"source_ip": "1.1.1.1", "count": 2},
                                       {"source_ip": "2.2.2.2", "count": 1}]


# ---- anomalies reuse ---- #

def test_anomalies_and_baseline_embedded_in_payload(tmp_db, client):
    now = time.time()
    base = [{**_SAMPLE_DEFAULTS, "ts": now - 600 + i * 8.0} for i in range(60)]
    _insert_samples(base)
    _insert_samples([
        {**_SAMPLE_DEFAULTS, "ts": now - 100.0, "cpu_pct": 100.0},
        {**_SAMPLE_DEFAULTS, "ts": now - 92.0, "cpu_pct": 100.0},
        {**_SAMPLE_DEFAULTS, "ts": now - 84.0, "cpu_pct": 100.0},
    ])
    r = client.get("/api/insights", params={"range": "24h"})
    assert r.status_code == 200
    payload = r.json()
    assert len(payload["anomalies"]) == 1
    entry = payload["anomalies"][0]
    assert entry["metric"] == "cpu_pct"
    assert entry["direction"] == "high"
    assert entry["run_len"] == 3
    cpu_baseline = payload["baseline"]["cpu_pct"]
    assert cpu_baseline["n"] == 63
    assert cpu_baseline["mean"] == pytest.approx((60 * 50 + 3 * 100) / 63, abs=0.01)


# ---- cache ---- #

def test_endpoint_serves_single_flight_cache(client, monkeypatch):
    calls = {"count": 0}

    def fake_compute(range_str: str = "24h") -> dict[str, Any]:
        calls["count"] += 1
        return {"range": range_str, "generated_at": "test", "effective_window": None,
                "trends": {"range": range_str, "bucket_sec": 240, "count": 0, "points": []},
                "disk": [], "top_processes": [],
                "maintenance": {"total": 0, "ok": 0, "failed": 0,
                                "success_rate": None, "by_action": []},
                "security": {"total": 0, "by_kind": [], "top_sources": []},
                "baseline": {}, "anomalies": []}

    monkeypatch.setattr(insights_overview, "compute_insights", fake_compute)
    r1 = client.get("/api/insights", params={"range": "7d"})
    r2 = client.get("/api/insights", params={"range": "7d"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert calls["count"] == 1
