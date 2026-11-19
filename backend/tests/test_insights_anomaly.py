import time
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

import config
import history
import insights
import main


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "h.db")
    history._conn = None
    yield
    if history._conn is not None:
        history._conn.close()
        history._conn = None


@pytest.fixture()
def client():
    return TestClient(main.app)


def _clear_anomaly_caches() -> None:
    for cache in main._anomalies_caches.values():
        cache.clear()


@pytest.fixture(autouse=True)
def _fresh_anomaly_caches():
    _clear_anomaly_caches()
    yield
    _clear_anomaly_caches()


_INSERT_SQL = (
    "INSERT OR REPLACE INTO samples "
    "(ts, cpu_pct, ram_pct, swap_pct, cpu_temp, gpu_temp, disk_temp_max, "
    "cpu_power_w, gpu_power_w, net_sent_bps, net_recv_bps, "
    "disk_read_bps, disk_write_bps) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

_COLS = ("ts", "cpu_pct", "ram_pct", "swap_pct", "cpu_temp", "gpu_temp",
         "disk_temp_max", "cpu_power_w", "gpu_power_w", "net_sent_bps",
         "net_recv_bps", "disk_read_bps", "disk_write_bps")

_DEFAULTS: dict[str, float | None] = {
    "cpu_pct": 50.0, "ram_pct": 40.0, "swap_pct": 5.0, "cpu_temp": 60.0,
    "gpu_temp": None, "disk_temp_max": None, "cpu_power_w": None, "gpu_power_w": None,
    "net_sent_bps": 1000.0, "net_recv_bps": 2000.0,
    "disk_read_bps": 300_000.0, "disk_write_bps": 400_000.0,
}


def _hour_start(hours_ago: int) -> float:
    return (int(time.time() // 3600) - hours_ago) * 3600 + 60.0


def _insert_series(start_ts: float, count: int, step: float, **overrides: float | None) -> None:
    conn = history._get_conn()
    for i in range(count):
        values = {**_DEFAULTS, **overrides, "ts": start_ts + i * step}
        conn.execute(_INSERT_SQL, tuple(values[c] for c in _COLS))
    conn.commit()


def test_baseline_flat_when_history_short(tmp_db):
    _insert_series(_hour_start(0), count=50, step=10.0)
    payload = insights.compute_anomalies("24h")
    cpu = payload["baseline"]["cpu_pct"]
    assert cpu["mode"] == "flat"
    assert cpu["hours"] == {}
    assert cpu["n"] == 50
    assert cpu["mean"] == 50.0
    assert cpu["std"] == 1.0
    assert cpu["lo"] == 47.0
    assert cpu["hi"] == 53.0


def test_baseline_flat_when_distinct_hours_below_minimum(tmp_db):
    base = _hour_start(3)
    for hour in range(4):
        _insert_series(base + hour * 3600, count=30, step=100.0, cpu_pct=50.0 + hour)
    payload = insights.compute_anomalies("24h")
    cpu = payload["baseline"]["cpu_pct"]
    assert cpu["mode"] == "flat"
    assert cpu["hours"] == {}
    assert cpu["n"] == 120
    assert cpu["mean"] == pytest.approx(51.5, abs=0.01)


def test_baseline_hourly_profile(tmp_db):
    base = _hour_start(7)
    for hour in range(8):
        _insert_series(base + hour * 3600, count=20, step=100.0, cpu_pct=50.0 + hour)
    payload = insights.compute_anomalies("24h")
    cpu = payload["baseline"]["cpu_pct"]
    assert cpu["mode"] == "hourly"
    assert cpu["n"] == 160
    assert len(cpu["hours"]) == 8
    first_hour = datetime.fromtimestamp(base, tz=insights.LOCAL_TZ).hour
    entry = cpu["hours"][str(first_hour)]
    assert entry["n"] == 20
    assert entry["mean"] == 50.0
    assert entry["std"] == 1.0
    assert entry["lo"] == 47.0
    assert entry["hi"] == 53.0


def test_baseline_skips_all_null_metrics(tmp_db):
    _insert_series(_hour_start(0), count=10, step=10.0)
    payload = insights.compute_anomalies("24h")
    assert "gpu_temp" not in payload["baseline"]
    assert "cpu_power_w" not in payload["baseline"]


def test_anomaly_triggers_after_run_length(tmp_db):
    now = time.time()
    _insert_series(now - 600, count=60, step=8.0)
    first_anomaly_ts = now - 100
    _insert_series(first_anomaly_ts, count=3, step=8.0, cpu_pct=100.0)
    payload = insights.compute_anomalies("24h")
    anomalies = payload["anomalies"]
    assert len(anomalies) == 1
    entry = anomalies[0]
    assert entry["metric"] == "cpu_pct"
    assert entry["ts"] == pytest.approx(first_anomaly_ts, abs=1e-6)
    assert entry["value"] == 100.0
    assert entry["direction"] == "high"
    assert entry["run_len"] == 3
    assert abs(entry["z"]) >= 3.0
    assert entry["expected"] == pytest.approx(payload["baseline"]["cpu_pct"]["mean"], abs=1.0)


def test_anomaly_requires_consecutive_run(tmp_db):
    now = time.time()
    _insert_series(now - 600, count=60, step=8.0)
    _insert_series(now - 100, count=2, step=8.0, cpu_pct=100.0)
    payload = insights.compute_anomalies("24h")
    assert payload["anomalies"] == []


def test_anomaly_run_interrupted_by_in_band_sample(tmp_db):
    now = time.time()
    _insert_series(now - 600, count=60, step=8.0)
    _insert_series(now - 100, count=2, step=8.0, cpu_pct=100.0)
    _insert_series(now - 80, count=1, step=8.0)
    _insert_series(now - 60, count=2, step=8.0, cpu_pct=100.0)
    payload = insights.compute_anomalies("24h")
    assert payload["anomalies"] == []


def test_anomaly_clears_when_back_in_band(tmp_db, client):
    now = time.time()
    _insert_series(now - 600, count=60, step=8.0)
    _insert_series(now - 100, count=3, step=8.0, cpu_pct=100.0)
    r = client.get("/api/anomalies", params={"range": "24h"})
    assert r.status_code == 200
    assert len(r.json()["anomalies"]) == 1
    _insert_series(now - 60, count=1, step=8.0)
    _clear_anomaly_caches()
    r = client.get("/api/anomalies", params={"range": "24h"})
    assert r.status_code == 200
    assert r.json()["anomalies"] == []


@pytest.mark.parametrize("rng", ["6h", "5m", "1h", "30m", "bogus"])
def test_anomalies_reject_unknown_range(client, rng):
    r = client.get("/api/anomalies", params={"range": rng})
    assert r.status_code == 422


@pytest.mark.parametrize("rng", ["24h", "7d", "30d"])
def test_anomalies_empty_history_returns_empty_payload(tmp_db, client, rng):
    r = client.get("/api/anomalies", params={"range": rng})
    assert r.status_code == 200
    payload = r.json()
    assert payload["range"] == rng
    assert payload["baseline"] == {}
    assert payload["anomalies"] == []
    assert payload["n_samples"] == 0


def test_endpoint_serves_single_flight_cache(client, monkeypatch):
    calls = {"count": 0}

    def fake_compute(range_str: str = "24h") -> dict[str, Any]:
        calls["count"] += 1
        return {"range": range_str, "generated_at": "test", "n_samples": 0,
                "baseline": {}, "anomalies": []}

    monkeypatch.setattr(insights, "compute_anomalies", fake_compute)
    r1 = client.get("/api/anomalies", params={"range": "7d"})
    r2 = client.get("/api/anomalies", params={"range": "7d"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert calls["count"] == 1
