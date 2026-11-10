"""Tests for the Windows Update status endpoint (`maintenance/updates.py`).

Every PowerShell call is faked: the module-level runner is only the default of
the injectable `runner` parameter, and the router tests monkeypatch
`updates.status` / `updates.scan` so the real machine is never touched.
"""
import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

import config
import main
from maintenance import actions, updates
from maintenance import history as action_log


def _no_real_scripts(*_args, **_kwargs):
    raise AssertionError("real PowerShell script must never run in tests")


PENDING_ALL = json.dumps({"cbs": True, "wu": True, "renames": 4})
PENDING_NONE = json.dumps({"cbs": False, "wu": False, "renames": 0})

HOTFIX_FIVE = json.dumps(
    [
        {"id": "KB5036893", "description": "Security Update", "installedOn": "2026-05-14"},
        {"id": "KB5034441", "description": "Security Update", "installedOn": "2026-04-10"},
        {"id": "KB5033375", "description": "Update", "installedOn": "2026-03-12"},
        {"id": "KB5028185", "description": "Update", "installedOn": "2026-02-08"},
        {"id": "KB5027231", "description": "Update", "installedOn": "2026-01-09"},
    ]
)


class FakeRunner:
    """Answers the pending-reboot and hotfix scripts with canned output."""

    def __init__(
        self,
        *,
        pending: object = PENDING_ALL,
        hotfix: object = HOTFIX_FIVE,
        pending_raises: bool = False,
        hotfix_raises: bool = False,
    ) -> None:
        self.pending = pending
        self.hotfix = hotfix
        self.pending_raises = pending_raises
        self.hotfix_raises = hotfix_raises
        self.calls: list[str] = []
        self.timeouts: list[float] = []

    async def __call__(self, script: str, *, timeout: float = 30.0) -> str:
        self.calls.append(script)
        self.timeouts.append(timeout)
        if "RebootPending" in script:
            if self.pending_raises:
                raise RuntimeError("registry probe exploded")
            return str(self.pending)
        if "Get-HotFix" in script:
            if self.hotfix_raises:
                raise RuntimeError("Get-HotFix exploded")
            return str(self.hotfix)
        raise AssertionError(f"unexpected PowerShell script: {script}")


@pytest.fixture(autouse=True)
def _isolated_runner(monkeypatch):
    monkeypatch.setattr(updates, "run_powershell", _no_real_scripts)
    monkeypatch.setattr(actions, "run_powershell", _no_real_scripts)
    yield


def _client():
    try:
        return TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 51000))
    except TypeError:
        return TestClient(main.app)


def _headers() -> dict[str, str]:
    headers = {"X-Requested-With": "windy-dashboard"}
    if config.ADMIN_TOKEN:
        headers["X-Admin-Token"] = config.ADMIN_TOKEN
    return headers


# ---- status() ---- #


def test_status_reports_pending_reboot_hotfixes_and_last_scan():
    action_log.record(
        "wu-scan",
        ok=True,
        duration_ms=1200,
        detail={"updateCount": 3, "titles": ["Cumulative A", "Driver B", "Feature C"]},
    )
    runner = FakeRunner()

    result = asyncio.run(updates.status(runner=runner))

    assert result["pendingReboot"] == {
        "pending": True,
        "reasons": ["CBS", "WU", "PendingFileRename"],
    }
    assert len(runner.calls) == 2

    assert len(result["installed"]) == 5
    assert result["installed"][0] == {
        "id": "KB5036893",
        "description": "Security Update",
        "installedOn": "2026-05-14",
    }
    assert [row["id"] for row in result["installed"]][-1] == "KB5027231"

    last_scan = result["lastScan"]
    assert last_scan["ok"] is True
    assert last_scan["count"] == 3
    assert last_scan["titles"] == ["Cumulative A", "Driver B", "Feature C"]
    assert last_scan["durationMs"] == 1200
    assert last_scan["ts"].endswith("Z")

    assert result["errors"] == {}
    assert result["scannedAt"].endswith("Z")


def test_status_without_pending_reboot_has_empty_reasons():
    result = asyncio.run(updates.status(runner=FakeRunner(pending=PENDING_NONE)))

    assert result["pendingReboot"] == {"pending": False, "reasons": []}
    assert result["errors"] == {}


def test_status_resolves_module_runner_at_call_time(monkeypatch):
    calls: list[str] = []

    async def _fake(script: str, *, timeout: float = 30.0) -> str:
        calls.append(script)
        if "RebootPending" in script:
            return PENDING_ALL
        return HOTFIX_FIVE

    monkeypatch.setattr(updates, "run_powershell", _fake)

    result = asyncio.run(updates.status())

    assert len(calls) == 2
    assert result["pendingReboot"]["reasons"] == ["CBS", "WU", "PendingFileRename"]
    assert len(result["installed"]) == 5
    assert result["errors"] == {}


def test_scan_refreshes_status_with_module_runner(monkeypatch):
    calls: list[str] = []

    async def _action_runner(script: str, *, timeout: float = 30.0) -> str:
        return json.dumps({"count": 1, "titles": ["Only"]})

    async def _status_runner(script: str, *, timeout: float = 30.0) -> str:
        calls.append(script)
        if "RebootPending" in script:
            return PENDING_NONE
        return json.dumps([])

    monkeypatch.setattr(actions, "run_powershell", _action_runner)
    monkeypatch.setattr(updates, "run_powershell", _status_runner)

    result = asyncio.run(updates.scan())

    assert len(calls) == 2
    assert result["status"]["installed"] == []
    assert result["status"]["pendingReboot"]["pending"] is False


def test_status_ignores_empty_pending_file_rename_operations():
    runner = FakeRunner(pending=json.dumps({"cbs": True, "wu": False, "renames": 0}))

    result = asyncio.run(updates.status(runner=runner))

    assert result["pendingReboot"]["pending"] is True
    assert result["pendingReboot"]["reasons"] == ["CBS"]


def test_status_ignores_blank_rename_entries_list():
    payload = json.dumps({"cbs": False, "wu": True, "renames": ["", "  "]})

    result = asyncio.run(updates.status(runner=FakeRunner(pending=payload)))

    assert result["pendingReboot"]["reasons"] == ["WU"]


def test_status_returns_null_last_scan_when_no_wu_scan_history():
    result = asyncio.run(updates.status(runner=FakeRunner()))

    assert result["lastScan"] is None


def test_status_survives_powershell_failure():
    runner = FakeRunner(pending_raises=True, hotfix_raises=True)

    result = asyncio.run(updates.status(runner=runner))

    assert result["installed"] == []
    assert result["pendingReboot"] == {"pending": False, "reasons": []}
    assert "pendingReboot" in result["errors"]
    assert "installed" in result["errors"]
    assert "exploded" in result["errors"]["installed"]
    assert result["scannedAt"].endswith("Z")


def test_status_survives_unparseable_output():
    runner = FakeRunner(pending="Total garbage, not json", hotfix="<html>nope</html>")

    result = asyncio.run(updates.status(runner=runner))

    assert result["installed"] == []
    assert result["pendingReboot"] == {"pending": False, "reasons": []}
    assert set(result["errors"]) == {"pendingReboot", "installed"}


def test_status_skips_hotfix_rows_without_id():
    hotfix = json.dumps(
        [
            {"id": "", "description": "broken", "installedOn": ""},
            {"HotFixID": "KB1", "Description": "Only one", "InstalledOn": "2026-06-01"},
        ]
    )

    result = asyncio.run(updates.status(runner=FakeRunner(hotfix=hotfix)))

    assert result["installed"] == [
        {"id": "KB1", "description": "Only one", "installedOn": "2026-06-01"}
    ]


def test_status_last_scan_parses_failed_scan_row():
    action_log.record("wu-scan", ok=False, duration_ms=5, error=actions.ACTION_FAILED)

    result = asyncio.run(updates.status(runner=FakeRunner()))

    assert result["lastScan"]["ok"] is False
    assert result["lastScan"]["count"] == 0
    assert result["lastScan"]["titles"] == []


# ---- scan() ---- #


def test_scan_delegates_to_allowlisted_action(monkeypatch):
    scripts: list[str] = []

    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        scripts.append(script)
        return json.dumps({"count": 2, "titles": ["A", "B"]})

    monkeypatch.setattr(actions, "run_powershell", _runner)

    result = asyncio.run(updates.scan(runner=FakeRunner(pending=PENDING_NONE)))

    assert result["ok"] is True
    assert result["action"] == "wu-scan"
    assert result["result"]["updateCount"] == 2
    assert result["result"]["titles"] == ["A", "B"]
    assert result["status"]["pendingReboot"]["pending"] is False
    assert scripts == [actions.WU_SCAN_SCRIPT]

    row = action_log.query(limit=1)[0]
    assert row["action"] == "wu-scan"
    assert row["ok"] is True


def test_scan_propagates_action_error(monkeypatch):
    async def _boom(script: str, *, timeout: float = 30.0) -> str:
        raise RuntimeError("downlevel")

    monkeypatch.setattr(actions, "run_powershell", _boom)

    with pytest.raises(actions.ActionError) as excinfo:
        asyncio.run(updates.scan(runner=FakeRunner()))

    assert excinfo.value.code == actions.ACTION_FAILED


# ---- API ---- #


def test_windows_update_endpoint_returns_full_payload(monkeypatch):
    async def _fake_status(*, runner=None):
        return {
            "pendingReboot": {"pending": True, "reasons": ["WU"]},
            "installed": [
                {"id": "KB1", "description": "Update", "installedOn": "2026-06-01"}
            ],
            "lastScan": {
                "ts": "2026-06-01T00:00:00Z",
                "ok": True,
                "count": 1,
                "titles": ["A"],
                "durationMs": 10,
            },
            "scannedAt": "2026-06-01T00:00:00Z",
            "errors": {},
        }

    monkeypatch.setattr(updates, "status", _fake_status)

    response = _client().get("/api/maintenance/windows-update")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["module"] == "maintenance"
    assert body["stage"] == "write"
    assert body["servedAt"].endswith("Z")
    assert body["pendingReboot"]["reasons"] == ["WU"]
    assert body["installed"][0]["id"] == "KB1"
    assert body["lastScan"]["count"] == 1
    assert body["errors"] == {}


def test_windows_update_scan_requires_csrf_header():
    response = _client().post("/api/maintenance/windows-update/scan")

    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden: csrf"


def test_windows_update_scan_returns_fresh_status(monkeypatch):
    calls: list[int] = []

    async def _fake_scan(*, runner=None):
        calls.append(1)
        return {
            "ok": True,
            "action": "wu-scan",
            "result": {"updateCount": 0, "titles": []},
            "durationMs": 42,
            "status": {
                "pendingReboot": {"pending": False, "reasons": []},
                "installed": [],
                "lastScan": None,
                "scannedAt": "2026-06-01T00:00:00Z",
                "errors": {},
            },
        }

    monkeypatch.setattr(updates, "scan", _fake_scan)

    response = _client().post("/api/maintenance/windows-update/scan", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"]["pendingReboot"]["pending"] is False
    assert calls == [1]


def test_windows_update_scan_maps_action_error(monkeypatch):
    async def _boom(*, runner=None):
        raise actions.ActionError(actions.ACTION_FAILED, status_code=502)

    monkeypatch.setattr(updates, "scan", _boom)

    response = _client().post("/api/maintenance/windows-update/scan", headers=_headers())

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == actions.ACTION_FAILED
    assert detail["action"] == "windows-update-scan"
    assert detail["text"]
    assert detail["hint"]


def test_windows_update_scan_maps_generic_exception_as_write_error(monkeypatch):
    async def _boom(*, runner=None):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(updates, "scan", _boom)

    response = _client().post("/api/maintenance/windows-update/scan", headers=_headers())

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "WRITE_FAILED"
    assert detail["code"] != "READ_FAILED"
    assert detail["action"] == "windows-update-scan"
    assert "unexpected failure" in detail["text"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
