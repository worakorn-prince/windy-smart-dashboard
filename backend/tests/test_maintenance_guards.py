import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
import main

CSRF = {"X-Requested-With": "windy-dashboard"}
router_module = sys.modules["maintenance.router"]


@pytest.fixture()
def client():
    try:
        return TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 51000))
    except TypeError:
        return TestClient(main.app)


@pytest.fixture()
def relaunch_spy(monkeypatch):
    scheduled: list[int] = []
    audited: list[dict[str, object]] = []

    def _fake_schedule(pid: int) -> Path:
        scheduled.append(pid)
        return Path("fake-relaunch.ps1")

    def _fake_audit(request, *, ok, pid, duration_ms=0, script=None, error=None):
        audited.append({"ok": ok, "pid": pid, "error": error})

    monkeypatch.setattr(router_module, "_schedule_relaunch", _fake_schedule)
    monkeypatch.setattr(router_module, "_audit_relaunch", _fake_audit)
    return scheduled, audited


def test_status_ok(client, monkeypatch):
    from maintenance import system

    async def _fake_run(script, *, timeout=30.0):
        return '{"isAdmin": false, "osCaption": "Test OS", "osVersion": "10.0", "osBuild": "1"}'

    monkeypatch.setattr(system, "run_powershell", _fake_run)
    system.reset_cache()
    r = client.get("/api/maintenance/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["module"] == "maintenance"
    assert body["stage"] == "write"


def test_write_endpoints_reject_empty_payload_without_403(client):
    for path in ("/api/maintenance/action", "/api/maintenance/clean"):
        r = client.post(path, headers=CSRF, json={})
        assert r.status_code != 403, path
        assert r.status_code in (400, 422), path


def test_relaunch_without_confirm_400(client):
    r = client.post("/api/maintenance/relaunch", headers=CSRF, json={})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "CONFIRMATION_REQUIRED"
    assert detail["action"] == "relaunch"


def test_missing_csrf_403(client):
    for path in ("/api/maintenance/action", "/api/maintenance/relaunch"):
        r = client.post(path, json={"confirm": "relaunch"})
        assert r.status_code == 403, path
        assert r.json()["detail"] == "forbidden: csrf"


def test_bad_host_403(client):
    r = client.get("/api/maintenance/status", headers={"Host": "evil.com"})
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden: host"

    r = client.post(
        "/api/maintenance/relaunch",
        headers={**CSRF, "Host": "evil.com"},
        json={"confirm": "relaunch"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden: host"


def test_admin_token_required_401(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    for path in ("/api/maintenance/action", "/api/maintenance/relaunch"):
        r = client.post(path, headers=CSRF, json={"confirm": "relaunch"})
        assert r.status_code == 401, path


def test_admin_token_accepted_202(client, monkeypatch, relaunch_spy):
    scheduled, audited = relaunch_spy
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    r = client.post(
        "/api/maintenance/relaunch",
        headers={**CSRF, "x-admin-token": "secret"},
        json={"confirm": "relaunch"},
    )
    assert r.status_code == 202
    pid = os.getpid()
    assert r.json() == {"status": "relaunch_scheduled", "pid": pid}
    assert scheduled == [pid]
    assert audited == [{"ok": True, "pid": pid, "error": None}]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
