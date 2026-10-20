import json
import sys

import pytest
from fastapi.testclient import TestClient

import config
import main
from maintenance import cleaner, export, system

router_module = sys.modules["maintenance.router"]


STATUS_JSON = (
    '{"isAdmin": false, "osCaption": "Test OS", "osVersion": "10.0", "osBuild": "1"}'
)

SUMMARY_ROWS = [
    {"target": "user-temp", "path": "C:\\Users\\t\\AppData\\Local\\Temp", "bytes": 1000},
    {"target": "windows-temp", "path": "C:\\Windows\\Temp", "bytes": 2500},
    {"target": "recycle-bin", "path": "C:\\$Recycle.Bin", "bytes": 500},
]


def _no_real_scripts(*_args, **_kwargs):
    raise AssertionError("real PowerShell script must never run in tests")


@pytest.fixture(autouse=True)
def _isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "history.db")
    monkeypatch.setattr(system, "run_powershell", _no_real_scripts)
    system.reset_cache()
    monkeypatch.setattr(cleaner, "run_powershell", _no_real_scripts)
    yield


def _client():
    try:
        return TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 51000))
    except TypeError:
        return TestClient(main.app)


def test_csv_formula_cells_are_neutralized():
    body, media_type, _filename = export.build_payload(
        "devices",
        devices=[{"device": "=cmd|' /C calc'!A0", "version": "1.2.3"}],
        format="csv",
    )

    assert media_type.startswith("text/csv")
    assert "'=cmd" in body
    assert "'1.2.3" not in body
    assert "1.2.3" in body


def test_host_guard_denies_testserver_without_test_mode(monkeypatch):
    monkeypatch.delenv("DASH_TEST_MODE", raising=False)
    response = _client().get("/api/maintenance/status")

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden: host"


def test_host_guard_allows_testserver_in_test_mode(monkeypatch):
    monkeypatch.setenv("DASH_TEST_MODE", "1")

    async def _fake_run(script, *, timeout=30.0):
        return STATUS_JSON

    monkeypatch.setattr(system, "run_powershell", _fake_run)
    system.reset_cache()

    response = _client().get("/api/maintenance/status")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_summary_endpoint_totals_rows(monkeypatch):
    rows = json.dumps(SUMMARY_ROWS, ensure_ascii=False)

    async def _fake_run(script, *, timeout=30.0):
        assert "Summary" not in script
        assert "Remove-Item" not in script
        assert timeout == cleaner.SUMMARY_TIMEOUT
        return rows

    monkeypatch.setattr(cleaner, "run_powershell", _fake_run)

    response = _client().get("/api/maintenance/clean/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["totalBytes"] == 4000
    assert len(body["categories"]) == 3
    assert body["categories"][0]["target"] == "user-temp"
    assert isinstance(body["durationMs"], int)


def test_summary_endpoint_reports_failure(monkeypatch):
    async def _fake_run(script, *, timeout=30.0):
        raise RuntimeError("powershell exploded")

    monkeypatch.setattr(cleaner, "run_powershell", _fake_run)

    response = _client().get("/api/maintenance/clean/summary")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == cleaner.SUMMARY_FAILED
    assert "powershell exploded" in detail["text"]
