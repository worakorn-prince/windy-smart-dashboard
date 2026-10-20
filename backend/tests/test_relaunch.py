"""Contract tests for the guarded `/relaunch` endpoint.

The real relaunch helper must never run inside pytest: an autouse fixture
replaces `_schedule_relaunch` with a spy and stubs both audit sinks.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
import main

router_module = sys.modules["maintenance.router"]
_REAL_SCHEDULE = router_module._schedule_relaunch

CSRF = {"X-Requested-With": "windy-dashboard"}
RELAUNCH = "/api/maintenance/relaunch"
CONFIRM = {"confirm": "relaunch"}


def _client(host: tuple[str, int] = ("127.0.0.1", 51000)) -> TestClient:
    try:
        return TestClient(main.app, base_url="http://testserver", client=host)
    except TypeError:
        return TestClient(main.app)


@pytest.fixture()
def client() -> TestClient:
    return _client()


@pytest.fixture(autouse=True)
def spies(monkeypatch):
    schedule: list[int] = []
    security: list[dict] = []
    history: list[dict] = []

    def _fake_schedule(pid: int) -> Path:
        schedule.append(pid)
        return Path("fake-relaunch.ps1")

    def _fake_security_event(kind, source_ip, detail=None, ts=None):
        security.append({"kind": kind, "source_ip": source_ip, "detail": detail})
        return True

    def _fake_history_record(
        action, *, target=None, ok, duration_ms=0, detail=None, error=None
    ):
        history.append(
            {"action": action, "ok": ok, "detail": detail, "error": error}
        )

    monkeypatch.setattr(router_module, "_schedule_relaunch", _fake_schedule)
    monkeypatch.setattr(
        router_module.security_persistence, "record_event", _fake_security_event
    )
    monkeypatch.setattr(router_module.action_log, "record", _fake_history_record)
    return {"schedule": schedule, "security": security, "history": history}


def _assert_nothing_scheduled(spies) -> None:
    assert spies["schedule"] == []
    assert spies["security"] == []
    assert spies["history"] == []


def test_missing_body_requires_confirmation(client, spies):
    response = client.post(RELAUNCH, headers=CSRF)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CONFIRMATION_REQUIRED"
    _assert_nothing_scheduled(spies)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"confirm": ""},
        {"confirm": "yes"},
        {"confirm": "RELAUNCH"},
        {"confirm": "relaunch!"},
        {"confirm": True},
        {"confirm": None},
        {"confirm": 1},
    ],
)
def test_invalid_confirm_400(client, spies, payload):
    response = client.post(RELAUNCH, headers=CSRF, json=payload)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CONFIRMATION_REQUIRED"
    assert detail["action"] == "relaunch"
    _assert_nothing_scheduled(spies)


def test_missing_admin_token_401(client, spies, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    response = client.post(RELAUNCH, headers=CSRF, json=CONFIRM)
    assert response.status_code == 401
    _assert_nothing_scheduled(spies)


def test_non_loopback_without_token_403(spies, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    response = _client(("10.1.2.3", 5000)).post(RELAUNCH, headers=CSRF, json=CONFIRM)
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden: loopback only"
    _assert_nothing_scheduled(spies)


def test_missing_csrf_403(client, spies):
    response = client.post(RELAUNCH, json=CONFIRM)
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden: csrf"
    _assert_nothing_scheduled(spies)


def test_bad_host_403(client, spies):
    response = client.post(
        RELAUNCH, headers={**CSRF, "Host": "evil.com"}, json=CONFIRM
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden: host"
    _assert_nothing_scheduled(spies)


def test_confirmed_relaunch_202_and_audited(client, spies):
    response = client.post(RELAUNCH, headers=CSRF, json=CONFIRM)
    pid = os.getpid()

    assert response.status_code == 202
    assert response.json() == {"status": "relaunch_scheduled", "pid": pid}
    assert spies["schedule"] == [pid]

    assert len(spies["security"]) == 1
    event = spies["security"][0]
    assert event["kind"] == "relaunch_scheduled"
    assert event["source_ip"] == "127.0.0.1"
    assert event["detail"]["pid"] == pid

    assert len(spies["history"]) == 1
    record = spies["history"][0]
    assert record["action"] == "relaunch"
    assert record["ok"] is True
    assert record["error"] is None
    assert record["detail"]["pid"] == pid


def test_admin_token_confirmed_relaunch_202(client, spies, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    response = client.post(
        RELAUNCH, headers={**CSRF, "x-admin-token": "secret"}, json=CONFIRM
    )
    assert response.status_code == 202
    assert spies["schedule"] == [os.getpid()]


def test_scheduling_failure_500_and_audited(client, spies, monkeypatch):
    def _boom(pid: int):
        raise RuntimeError("powershell unavailable")

    monkeypatch.setattr(router_module, "_schedule_relaunch", _boom)

    response = client.post(RELAUNCH, headers=CSRF, json=CONFIRM)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "RELAUNCH_FAILED"
    assert spies["schedule"] == []
    assert [event["kind"] for event in spies["security"]] == ["relaunch_failed"]
    assert spies["history"][0]["ok"] is False
    assert "powershell unavailable" in spies["history"][0]["error"]


def test_relaunch_script_contents():
    script = router_module._relaunch_script(4321)

    assert script.endswith("\n")
    assert "Start-Sleep -Seconds 2.0" in script
    assert "Get-Process -Id 4321" in script
    assert "Stop-Process -Id $target.Id -Force" in script
    assert "Start-Process" in script
    assert sys.executable in script
    assert "main.py" in script
    assert str(router_module.BACKEND_DIR) in script


def test_schedule_relaunch_writes_temp_script(monkeypatch, tmp_path):
    calls: list[tuple[list[str], dict]] = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(router_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(router_module.tempfile, "gettempdir", lambda: str(tmp_path))

    script = _REAL_SCHEDULE(4321)

    assert script.parent == tmp_path
    assert script.name.startswith("dashboard-relaunch-4321-")
    assert script.suffix == ".ps1"
    assert "Stop-Process -Id $target.Id -Force" in script.read_text(encoding="utf-8-sig")

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "powershell.exe"
    assert str(script) in args
    assert kwargs["cwd"] == str(router_module.BACKEND_DIR)
    assert kwargs["close_fds"] is True
    if sys.platform == "win32":
        assert kwargs["creationflags"] & subprocess.DETACHED_PROCESS
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert kwargs["creationflags"] == 0

    script.unlink()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
