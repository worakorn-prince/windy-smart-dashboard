import sys

import pytest
from fastapi.testclient import TestClient

import config
import main

CSRF = {"X-Requested-With": "windy-dashboard"}
STUBS = ("/api/maintenance/relaunch",)


@pytest.fixture()
def client():
    try:
        return TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 51000))
    except TypeError:
        return TestClient(main.app)


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


def test_stubs_501_with_guards_passed(client):
    for path in STUBS:
        r = client.post(path, headers=CSRF, json={})
        assert r.status_code == 501, path
        detail = r.json()["detail"]
        assert detail["code"] == "RELAUNCH_DISABLED"
        assert detail["text"]
        assert detail["hint"]

    for path in ("/api/maintenance/action", "/api/maintenance/clean"):
        r = client.post(path, headers=CSRF, json={})
        assert r.status_code != 403, path
        assert r.status_code in (400, 422), path


def test_missing_csrf_403(client):
    r = client.post("/api/maintenance/action", json={})
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden: csrf"


def test_bad_host_403(client):
    r = client.get("/api/maintenance/status", headers={"Host": "evil.com"})
    assert r.status_code == 403
    assert r.json()["detail"] == "forbidden: host"


def test_admin_token_required_401(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    r = client.post("/api/maintenance/action", headers=CSRF, json={})
    assert r.status_code == 401


def test_admin_token_accepted_501(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    r = client.post(
        "/api/maintenance/relaunch",
        headers={**CSRF, "x-admin-token": "secret"},
        json={},
    )
    assert r.status_code == 501
    assert "RELAUNCH_DISABLED" in r.text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
