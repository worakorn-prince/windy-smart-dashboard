import time

import pytest

import config
import history


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "h.db")
    history._conn = None
    yield
    if history._conn is not None:
        history._conn.close()
        history._conn = None


def _seed(conn, start_ts, count, step=10):
    for i in range(count):
        conn.execute(
            "INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (start_ts + i * step, 50 + (i % 10), 40, 5, 60, 55, 35, 1200, 30,
             1000, 2000, 300000, 400000),
        )
    conn.commit()


def test_schema_created_and_bucketing_1h(tmp_db):
    conn = history._get_conn()
    _seed(conn, time.time() - 3000, count=300)
    r = history.query_range("1h")
    assert r["range"] == "1h"
    assert r["bucket_sec"] == 10
    assert r["count"] >= 290
    p = r["points"][0]
    assert 50 <= p["cpu_pct"] <= 59
    assert p["cpu_temp"] == 60
    assert p["net_recv_bps"] == 2000


def test_6h_uses_60s_buckets(tmp_db):
    conn = history._get_conn()
    _seed(conn, time.time() - 7000, count=700)
    r = history.query_range("6h")
    assert r["bucket_sec"] == 60
    assert r["count"] >= 100


def test_unknown_range_falls_back_to_1h(tmp_db):
    conn = history._get_conn()
    _seed(conn, time.time() - 60, count=6)
    r = history.query_range("bogus")
    assert r["range"] == "bogus"
    assert r["bucket_sec"] == 10


def test_null_values_survive_roundtrip(tmp_db):
    conn = history._get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (time.time(), 10, 20, 5, None, None, None, None, None, 0, 0, 0, 0),
    )
    conn.commit()
    r = history.query_range("1h")
    assert r["count"] >= 1
    assert r["points"][-1]["cpu_temp"] is None
    assert r["points"][-1]["cpu_power_w"] is None


def test_old_rows_excluded_by_range(tmp_db):
    conn = history._get_conn()
    _seed(conn, time.time() - 7200, count=60)
    r = history.query_range("1h")
    assert r["count"] == 0
