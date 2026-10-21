"""Tests for scheduled self-contained HTML reports (FEAT-305).

Covers:
  - generate_report with seeded history/disk/process/security data
  - generate_report with no database at all (all sections "no data")
  - XSS escaping of process names / event details
  - list_reports ordering and prune_reports(keep)
  - API admin gating, days validation, download + traversal rejection
  - DASH_REPORT_INTERVAL_HOURS parser (0/negative disables the scheduler)
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import config
import disk_health
import main
import process_history
import reports
from security import persistence

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples(
    ts REAL PRIMARY KEY,
    cpu_pct REAL,
    ram_pct REAL
);
CREATE TABLE IF NOT EXISTS disk_samples(
    ts TEXT,
    mount TEXT,
    used_gb REAL,
    total_gb REAL
);
CREATE TABLE IF NOT EXISTS process_samples(
    ts TEXT,
    pid INTEGER,
    name TEXT,
    cpu_pct REAL,
    mem_mb REAL
);
CREATE TABLE IF NOT EXISTS security_events(
    id INTEGER PRIMARY KEY,
    ts TEXT,
    kind TEXT,
    source_ip TEXT,
    detail TEXT
);
"""


def _iso(days_ago: float = 0.0) -> str:
    moment = datetime.now(UTC) - timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _seed(db: Path, statements: list[tuple[str, tuple]]) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.executescript(_SCHEMA)
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def report_env(tmp_path, monkeypatch):
    """Isolate the shared history DB and the report output directory."""
    db = tmp_path / "history.db"
    out = tmp_path / "reports"
    out.mkdir()
    monkeypatch.setattr(config, "HISTORY_DB", db)
    monkeypatch.setattr(reports, "REPORTS_DIR", out)
    disk_health.close()
    process_history.close()
    persistence.close()
    yield SimpleNamespace(db=db, out=out)
    disk_health.close()
    process_history.close()
    persistence.close()


@pytest.fixture()
def client():
    return TestClient(main.app)


def _auth() -> dict[str, str]:
    return {"X-Admin-Token": "secret"}


def _seed_example(db: Path) -> None:
    now = time.time()
    ts = _iso()
    detail = json.dumps({"port": 8080, "name": "<script>alert('detail')</script>"})
    _seed(db, [
        ("INSERT INTO samples(ts, cpu_pct, ram_pct) VALUES (?,?,?)",
         (now - 3600, 10.0, 40.0)),
        ("INSERT INTO samples(ts, cpu_pct, ram_pct) VALUES (?,?,?)",
         (now - 60, 20.0, 60.0)),
        ("INSERT INTO disk_samples(ts, mount, used_gb, total_gb) VALUES (?,?,?,?)",
         (_iso(2), "C:\\", 10.0, 100.0)),
        ("INSERT INTO disk_samples(ts, mount, used_gb, total_gb) VALUES (?,?,?,?)",
         (_iso(1), "C:\\", 20.0, 100.0)),
        ("INSERT INTO disk_samples(ts, mount, used_gb, total_gb) VALUES (?,?,?,?)",
         (ts, "C:\\", 30.0, 100.0)),
        ("INSERT INTO process_samples(ts, pid, name, cpu_pct, mem_mb) VALUES (?,?,?,?,?)",
         (ts, 4242, "<script>alert(1)</script>", 55.5, 128.0)),
        ("INSERT INTO process_samples(ts, pid, name, cpu_pct, mem_mb) VALUES (?,?,?,?,?)",
         (ts, 7, "svc.exe", 5.0, 64.0)),
        ("INSERT INTO security_events(ts, kind, source_ip, detail) VALUES (?,?,?,?)",
         (ts, "port_opened", "1.2.3.4", detail)),
    ])


def test_generate_report_with_data(report_env, monkeypatch):
    _seed_example(report_env.db)
    monkeypatch.setattr(
        disk_health, "disk_usage",
        lambda: [{"mount": "C:\\", "used_gb": 30.0, "total_gb": 100.0, "used_pct": 30.0}],
    )

    path = reports.generate_report(1)
    content = path.read_text(encoding="utf-8")

    assert path.parent == report_env.out
    assert reports.REPORT_NAME_RE.match(path.name)
    assert content.startswith("<!DOCTYPE html>")
    assert "สรุปภาพรวมระบบ" in content
    assert "จำนวน samples: 2" in content
    assert "15.0" in content and "20.0" in content
    assert "เหตุการณ์ความปลอดภัย" in content
    assert "port_opened" in content
    assert "1.2.3.4" in content
    assert "C:\\" in content
    assert "เต็มใน ~" in content
    assert "svc.exe" in content
    assert "UTC" in content
    assert "http://" not in content and "https://" not in content


def test_generate_report_escapes_xss(report_env, monkeypatch):
    _seed_example(report_env.db)
    monkeypatch.setattr(disk_health, "disk_usage", lambda: [])

    content = reports.generate_report(1).read_text(encoding="utf-8")

    assert "<script>alert" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "&lt;script&gt;alert(&#x27;detail&#x27;)&lt;/script&gt;" in content


def test_generate_report_without_data(report_env):
    path = reports.generate_report(7)
    content = path.read_text(encoding="utf-8")

    assert path.name.endswith("-d7.html")
    assert reports.REPORT_NAME_RE.match(path.name)
    assert content.count("no data") >= 3
    assert "no prediction" not in content or "สุขภาพดิสก์" in content


def test_generate_report_rejects_unsupported_days(report_env):
    with pytest.raises(ValueError):
        reports.generate_report(2)


def test_list_reports_newest_first(report_env):
    names = [
        "report-20260101-000000-d1.html",
        "report-20260102-000000-d7.html",
        "report-20260103-000000-d1.html",
    ]
    for index, name in enumerate(names):
        target = report_env.out / name
        target.write_text("x", encoding="utf-8")
        stamp = 1_700_000_000 + index * 10
        os.utime(target, (stamp, stamp))
    (report_env.out / "notes.txt").write_text("ignored", encoding="utf-8")

    listed = reports.list_reports()
    assert [item["name"] for item in listed] == list(reversed(names))
    assert all(item["size"] == 1 for item in listed)
    assert all(isinstance(item["mtime"], float) for item in listed)


def test_prune_reports_keeps_newest(report_env):
    names = [f"report-2026010{day}-000000-d1.html" for day in range(1, 5)]
    for index, name in enumerate(names):
        target = report_env.out / name
        target.write_text("x", encoding="utf-8")
        stamp = 1_700_000_000 + index * 10
        os.utime(target, (stamp, stamp))

    removed = reports.prune_reports(keep=2)

    assert removed == 2
    assert sorted(p.name for p in report_env.out.iterdir()) == sorted(names[2:])


def test_reports_endpoints_require_admin(client, report_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    assert client.post("/api/reports/generate", json={"days": 1}).status_code == 401
    assert client.get("/api/reports").status_code == 401
    assert client.get("/api/reports/report-20260101-000000-d1.html").status_code == 401


def test_generate_endpoint_creates_report(client, report_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    r = client.post("/api/reports/generate", json={"days": 7}, headers=_auth())

    assert r.status_code == 200
    payload = r.json()
    assert payload["name"].endswith("-d7.html")
    assert reports.REPORT_NAME_RE.match(payload["name"])
    written = report_env.out / payload["name"]
    assert written.is_file()
    assert payload["size"] == written.stat().st_size
    assert Path(payload["path"]) == written

    listing = client.get("/api/reports", headers=_auth())
    assert listing.status_code == 200
    assert isinstance(listing.json(), list)
    assert listing.json()[0]["name"] == payload["name"]


def test_generate_endpoint_defaults_to_daily(client, report_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    r = client.post("/api/reports/generate", headers=_auth())

    assert r.status_code == 200
    assert r.json()["name"].endswith("-d1.html")


@pytest.mark.parametrize("days", [2, 0, 30, "7", True, None])
def test_generate_endpoint_rejects_bad_days(client, report_env, monkeypatch, days):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    r = client.post("/api/reports/generate", json={"days": days}, headers=_auth())

    assert r.status_code == 400


def test_download_endpoint_returns_html(client, report_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    name = client.post("/api/reports/generate", json={"days": 1}, headers=_auth()).json()["name"]

    r = client.get(f"/api/reports/{name}", headers=_auth())

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    assert "<!DOCTYPE html>" in r.text


@pytest.mark.parametrize("bad_name", [
    "evil.html",
    "report-20260101-000000-d3.html",
    "report-20260101-000000-d1.txt",
    "..%5C..%5Cmain.py",
    "report-20200101-000000-d1.html",
])
def test_download_endpoint_rejects_bad_names(client, report_env, monkeypatch, bad_name):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    r = client.get(f"/api/reports/{bad_name}", headers=_auth())

    assert r.status_code == 404


def test_download_endpoint_never_serves_outside_dir(tmp_path, client, report_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    outside = tmp_path / "report-20260105-000000-d1.html"
    outside.write_text("<html>outside</html>", encoding="utf-8")

    r = client.get("/api/reports/report-20260105-000000-d1.html", headers=_auth())

    assert r.status_code == 404


@pytest.mark.parametrize(("raw", "expected"), [
    ("24", 24.0),
    ("0", 0.0),
    ("-1", 0.0),
    ("0.5", 0.5),
    ("bogus", 24.0),
])
def test_report_interval_parser(monkeypatch, raw, expected):
    monkeypatch.setenv("DASH_REPORT_INTERVAL_HOURS", raw)
    assert main._report_interval_hours() == expected


def test_report_interval_parser_default(monkeypatch):
    monkeypatch.delenv("DASH_REPORT_INTERVAL_HOURS", raising=False)
    assert main._report_interval_hours() == 24.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
