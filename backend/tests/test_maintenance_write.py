import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

import config
import main
from maintenance import actions, cleaner, error_codes, export
from maintenance import history as action_log

router_module = sys.modules["maintenance.router"]


DEVICE = {
    "name": 'ACME, "Pro" Laptop',
    "driverName": "Contoso",
    "version": "1.2.3",
    "date": "2024-01-02",
    "status": "ok",
    "deviceId": "PCI\\GOOD",
    "problemCode": 0,
    "errorText": "",
}


def _no_real_scripts(*_args, **_kwargs):
    raise AssertionError("real PowerShell script must never run in tests")


@pytest.fixture(autouse=True)
def _isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "history.db")
    monkeypatch.setattr(actions, "run_powershell", _no_real_scripts)
    monkeypatch.setattr(cleaner, "run_powershell", _no_real_scripts)
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


def _post(path: str, payload: dict | None = None):
    client = _client()
    return client.post(f"/api/maintenance{path}", json=payload or {}, headers=_headers())


def test_unsupported_action_rejected_without_runner(monkeypatch):
    calls: list[str] = []

    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        calls.append(script)
        return "{}"

    monkeypatch.setattr(actions, "run_powershell", _runner)

    with pytest.raises(actions.ActionError) as excinfo:
        asyncio.run(actions.run_action("open-devmgmt"))

    assert excinfo.value.code == actions.UNSUPPORTED_ACTION
    assert excinfo.value.status_code == 400
    assert calls == []

    rows = action_log.query(limit=5)
    assert rows[0]["action"] == "open-devmgmt"
    assert rows[0]["ok"] is False
    assert rows[0]["error"] == actions.UNSUPPORTED_ACTION


def test_run_action_allowlist_contents():
    assert actions.ALLOWED_ACTIONS == ("wu-scan", "pnputil-scan")
    assert "open-devmgmt" not in actions.ALLOWED_ACTIONS


def test_pnputil_scan_records_history(monkeypatch):
    calls: list[str] = []

    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        calls.append(script)
        assert timeout == actions.PNPUTIL_TIMEOUT
        return json.dumps({"exitCode": 0, "output": "Scanning all devices..."})

    monkeypatch.setattr(actions, "run_powershell", _runner)

    result = asyncio.run(actions.run_action("pnputil-scan"))

    assert result["ok"] is True
    assert result["action"] == "pnputil-scan"
    assert result["result"]["exitCode"] == 0
    assert "Scanning" in result["result"]["output"]
    assert result["durationMs"] >= 0
    assert len(calls) == 1
    assert "pnputil" in calls[0]

    row = action_log.query(limit=1)[0]
    assert row["action"] == "pnputil-scan"
    assert row["ok"] is True
    assert "exitCode" in (row["detail"] or "")


def test_wu_scan_parses_count(monkeypatch):
    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        return json.dumps([{"count": 3, "titles": ["A", "B", "C"]}])

    monkeypatch.setattr(actions, "run_powershell", _runner)

    result = asyncio.run(actions.run_action("wu-scan"))
    assert result["result"]["updateCount"] == 3
    assert result["result"]["titles"] == ["A", "B", "C"]


def test_action_failure_is_recorded(monkeypatch):
    async def _boom(script: str, *, timeout: float = 30.0) -> str:
        raise RuntimeError("powershell exploded")

    monkeypatch.setattr(actions, "run_powershell", _boom)

    with pytest.raises(actions.ActionError) as excinfo:
        asyncio.run(actions.run_action("wu-scan"))

    assert excinfo.value.code == actions.ACTION_FAILED
    assert excinfo.value.status_code == 502
    assert action_log.query(limit=1)[0]["ok"] is False


@pytest.mark.parametrize("confirm", [False, None, 1, "true", 0])
def test_clean_requires_explicit_confirm(monkeypatch, confirm):
    calls: list[str] = []

    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        calls.append(script)
        return '{"filesDeleted":9,"filesSkipped":0,"bytesFreed":99}'

    monkeypatch.setattr(cleaner, "run_powershell", _runner)

    with pytest.raises(cleaner.CleanError) as excinfo:
        asyncio.run(cleaner.clean(["user-temp"], confirm=confirm))

    assert excinfo.value.code == cleaner.CONFIRM_REQUIRED
    assert excinfo.value.status_code == 400
    assert calls == []


def test_clean_rejects_unknown_target_without_runner(monkeypatch):
    calls: list[str] = []

    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        calls.append(script)
        return "{}"

    monkeypatch.setattr(cleaner, "run_powershell", _runner)

    for bad in ([], ["C:\\Windows\\System32"], ["user-temp", "boot"], "user-temp", [1]):
        with pytest.raises(cleaner.CleanError) as excinfo:
            asyncio.run(cleaner.clean(bad, confirm=True))
        assert excinfo.value.code == cleaner.INVALID_TARGETS
        assert excinfo.value.status_code == 400

    assert calls == []
    assert cleaner.ALLOWED_TARGETS == ("user-temp", "windows-temp", "recycle-bin")


def test_clean_aggregates_target_results(monkeypatch):
    seen: list[str] = []

    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        seen.append(script)
        if "Clear-RecycleBin" in script:
            return '{"filesDeleted":0,"filesSkipped":0,"bytesFreed":100}'
        return '{"filesDeleted":2,"filesSkipped":1,"bytesFreed":2048}'

    monkeypatch.setattr(cleaner, "run_powershell", _runner)

    result = asyncio.run(cleaner.clean(["user-temp", "recycle-bin"], confirm=True))

    assert result["ok"] is True
    assert result["filesDeleted"] == 2
    assert result["filesSkipped"] == 1
    assert result["bytesFreed"] == 2148
    assert result["total"] == {
        "filesDeleted": 2,
        "filesSkipped": 1,
        "bytesFreed": 2148,
    }
    assert set(result["details"]) == {"user-temp", "recycle-bin"}
    assert len(seen) == 2
    rows = action_log.query(limit=5)
    assert {row["target"] for row in rows if row["action"] == "clean"} == {
        "user-temp",
        "recycle-bin",
    }


def test_history_record_query_and_purge():
    action_log.record("wu-scan", ok=True, duration_ms=12, detail={"updateCount": 0})
    action_log.record(
        "clean",
        target="windows-temp",
        ok=False,
        duration_ms=7,
        error="boom",
    )

    rows = action_log.query(limit=10)
    assert len(rows) == 2
    newest, oldest = rows
    assert newest["action"] == "clean"
    assert newest["target"] == "windows-temp"
    assert newest["ok"] is False
    assert newest["error"] == "boom"
    assert newest["durationMs"] == 7
    assert oldest["ok"] is True
    assert json.loads(oldest["detail"]) == {"updateCount": 0}
    assert oldest["ts"].endswith("Z")

    assert action_log.query(limit=1)[0]["action"] == "clean"

    conn = action_log._connect()
    try:
        conn.execute(
            "INSERT INTO maintenance_actions (ts, action, ok, duration_ms) "
            "VALUES ('2000-01-01T00:00:00Z', 'wu-scan', 1, 1)"
        )
        conn.commit()
    finally:
        conn.close()

    assert action_log.purge(days=30) == 1
    assert len(action_log.query(limit=10)) == 2


def test_history_db_stays_in_tmp_path(tmp_path):
    response = _post("/clean", {"targets": ["user-temp"], "confirm": False})
    assert response.status_code == 400

    action_log.record("wu-scan", ok=True, duration_ms=1)

    assert config.HISTORY_DB == tmp_path / "history.db"
    assert config.HISTORY_DB.parent == tmp_path
    assert action_log.query(limit=1)[0]["action"] == "wu-scan"


def test_history_write_failure_does_not_raise(monkeypatch, tmp_path):
    bad = tmp_path / "not-a-dir"
    bad.write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "HISTORY_DB", bad / "history.db")
    action_log.record("wu-scan", ok=True)
    assert action_log.query(limit=1) == []


def test_build_csv_matches_updater_layout():
    csv_text = export.build_csv(
        [DEVICE, {"name": "Plain", "errorCode": 10, "errorText": "line1\nline2"}]
    )

    assert csv_text.startswith("\uFEFF")
    lines = csv_text.lstrip("\uFEFF").split("\r\n")
    assert lines[0] == "device,driverName,version,date,status,deviceId,errorCode,errorText"
    assert len(lines) == 3
    assert lines[1].startswith('"ACME, ""Pro"" Laptop",Contoso,1.2.3,2024-01-02,ok,')
    assert lines[2].endswith(',10,"line1\nline2"')
    assert len(lines[0].split(",")) == 8
    assert export.build_csv([]).lstrip("\uFEFF") == ",".join(export.DEVICE_HEADER)


def test_build_payload_history_json_and_guards():
    rows = [{"ts": "2024-01-01T00:00:00Z", "action": "wu-scan", "ok": True}]
    body, media_type, filename = export.build_payload("history", history_rows=rows, format="json")
    assert media_type == "application/json"
    assert filename.startswith("maintenance-history-") and filename.endswith(".json")
    assert json.loads(body) == rows

    csv_body, csv_type, csv_name = export.build_payload("history", history_rows=rows, format="csv")
    assert csv_type == export.CSV_MEDIA_TYPE
    assert csv_name.endswith(".csv")
    assert "ts,action,target,ok,durationMs,detail,error" in csv_body

    for kind, fmt in (("devices", "xml"), ("secrets", "json")):
        with pytest.raises(ValueError):
            export.build_payload(kind, format=fmt)


def test_action_endpoint_rejects_unsupported(monkeypatch):
    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        raise AssertionError("runner must not be called")

    monkeypatch.setattr(actions, "run_powershell", _runner)

    response = _post("/action", {"action": "open-devmgmt"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == actions.UNSUPPORTED_ACTION
    assert detail["action"] == "action"


def test_clean_endpoint_requires_confirm(monkeypatch):
    async def _runner(script: str, *, timeout: float = 30.0) -> str:
        raise AssertionError("runner must not be called")

    monkeypatch.setattr(cleaner, "run_powershell", _runner)

    response = _post("/clean", {"targets": ["user-temp"], "confirm": False})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == cleaner.CONFIRM_REQUIRED

    response = _post("/clean", {"targets": ["not-a-target"], "confirm": True})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == cleaner.INVALID_TARGETS


def test_export_endpoint_devices_csv(monkeypatch):
    async def _fake_scan(*, force: bool = False) -> dict:
        return {"devices": [DEVICE], "counts": {"total": 1, "ok": 1, "issues": 0}}

    monkeypatch.setattr(router_module, "scan", _fake_scan)

    response = _post("/export", {"kind": "devices", "format": "csv"})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert ".csv" in response.headers["content-disposition"]
    assert response.text.startswith("\uFEFF")
    assert "device,driverName,version,date,status,deviceId,errorCode,errorText" in response.text
    assert 'ACME, ""Pro"" Laptop' in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "secrets", "format": "json"},
        {"kind": "devices", "format": "xml"},
    ],
)
def test_export_rejects_invalid_before_scan(monkeypatch, payload):
    async def _runner(*_args, **_kwargs):
        raise AssertionError("scan must not run for an invalid export request")

    monkeypatch.setattr(router_module, "scan", _runner)

    response = _post("/export", payload)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_EXPORT"
    assert detail["action"] == "export"


def test_export_endpoint_history_json():
    action_log.record("wu-scan", ok=True, duration_ms=1)

    response = _post("/export", {"kind": "history", "format": "json"})
    assert response.status_code == 200
    rows = response.json()
    assert isinstance(rows, list)
    assert rows[0]["action"] == "wu-scan"


def test_relaunch_stays_disabled():
    response = _post("/relaunch", {})
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["code"] == "RELAUNCH_DISABLED"
    assert "run.ps1" in detail["hint"]

    error_codes.NOT_IMPLEMENTED  # legacy constant still importable


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
