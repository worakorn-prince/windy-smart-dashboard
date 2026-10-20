import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

import main
from maintenance import error_codes, powershell, scanner, system

DRIVERS = [
    {
        "DeviceName": "Good Device",
        "DeviceID": "PCI\\GOOD",
        "DriverVersion": "1.0.0",
        "DriverDate": "/Date(1700000000000)/",
        "DriverProviderName": "Contoso",
        "Status": "OK",
    },
    {
        "DeviceName": "Broken Device",
        "DeviceID": "PCI\\BROKEN",
        "DriverVersion": "2.0.0",
        "DriverDate": "2024-01-02T00:00:00Z",
        "DriverProviderName": "Contoso",
        "Status": "OK",
    },
    {
        "DeviceName": "Error Status Device",
        "DeviceID": "USB\\ERROR",
        "DriverVersion": "3.0.0",
        "DriverDate": "",
        "DriverProviderName": "Fabrikam",
        "Status": "Error",
    },
]

PROBLEMS = [
    {"Name": "Broken Device", "DeviceID": "PCI\\BROKEN", "ConfigManagerErrorCode": 10},
]

SYSTEM_PAYLOAD = {
    "isAdmin": False,
    "osCaption": "Microsoft Windows 11 Pro",
    "osVersion": "10.0.22631",
    "osBuild": "22631",
    "osArch": "64-bit",
    "cpuName": "Test CPU",
    "cpuCores": 8,
    "cpuThreads": 16,
    "ramTotalBytes": 16 * 1024**3,
    "ramFreeBytes": 8 * 1024**3,
    "psVersion": "5.1.22621.1",
    "disks": [{"name": "C:", "sizeBytes": 1000, "freeBytes": 250}],
}


def _make_runner(calls: list[str] | None = None):
    async def _run(script: str, *, timeout: float = 30.0) -> str:
        if calls is not None:
            calls.append(script)
        if "Win32_PnPSignedDriver" in script:
            return "WARNING: something noisy\n" + json.dumps(DRIVERS)
        if "Win32_PnPEntity" in script:
            return json.dumps(PROBLEMS)
        if "Win32_OperatingSystem" in script:
            return json.dumps(SYSTEM_PAYLOAD)
        raise AssertionError("unexpected script")

    return _run


@pytest.fixture(autouse=True)
def _clean_caches():
    scanner.reset_cache()
    system.reset_cache()
    yield
    scanner.reset_cache()
    system.reset_cache()


def _client():
    try:
        return TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 51000))
    except TypeError:
        return TestClient(main.app)


def test_parse_json_list_tolerates_warnings():
    assert powershell.parse_json_list("") == []
    assert powershell.parse_json_list('WARNING: noisy\n[{"A": 1}]') == [{"A": 1}]
    assert powershell.parse_json_list('{"A": 1}') == [{"A": 1}]
    assert powershell.parse_json_list('[{"A": 1}]\nVERBOSE: tail') == [{"A": 1}]


def test_scan_maps_devices_and_counts(monkeypatch):
    monkeypatch.setattr(scanner, "run_powershell", _make_runner())
    result = asyncio.run(scanner.scan(force=True))

    assert result["cached"] is False
    assert result["counts"] == {"total": 3, "ok": 1, "issues": 2}
    assert result["scannedAt"].endswith("Z")
    assert len(result["devices"]) == 3

    broken = next(d for d in result["devices"] if d["name"] == "Broken Device")
    assert broken["problemCode"] == 10
    assert broken["status"] == "issue"
    assert broken["errorText"]
    assert broken["errorHint"]
    assert broken["errorText"] == error_codes.text(10)

    error_status = next(d for d in result["devices"] if d["name"] == "Error Status Device")
    assert error_status["status"] == "issue"

    good = next(d for d in result["devices"] if d["name"] == "Good Device")
    assert good["status"] == "ok"
    assert good["problemCode"] == 0
    assert len(good["date"]) == 10


def test_scan_cache_hit_and_force_refresh(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(scanner, "run_powershell", _make_runner(calls))

    first = asyncio.run(scanner.scan())
    assert first["cached"] is False
    assert len(calls) == 2

    second = asyncio.run(scanner.scan())
    assert second["cached"] is True
    assert len(calls) == 2

    third = asyncio.run(scanner.scan(force=True))
    assert third["cached"] is False
    assert len(calls) == 4


def test_scan_timeout_is_readable(monkeypatch):
    async def _boom(script: str, *, timeout: float = 30.0) -> str:
        raise powershell.PowerShellTimeout(
            "PowerShell query timed out after 0.1s and was terminated"
        )

    monkeypatch.setattr(scanner, "run_powershell", _boom)
    with pytest.raises(scanner.ScanError) as excinfo:
        asyncio.run(scanner.scan(force=True))
    assert "timed out" in str(excinfo.value).lower()


def test_run_powershell_timeout_kills_process(monkeypatch):
    class _FakeProc:
        def __init__(self):
            self.killed = False
            self.returncode = None

        async def communicate(self):
            await asyncio.sleep(5)
            return b"", b""

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            return self.returncode

    proc = _FakeProc()

    async def _fake_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    with pytest.raises(powershell.PowerShellTimeout) as excinfo:
        asyncio.run(powershell.run_powershell("Get-Date", timeout=0.05))
    assert proc.killed is True
    assert "timed out" in str(excinfo.value).lower()


def test_system_info_cache(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(system, "run_powershell", _make_runner(calls))

    first = asyncio.run(system.system_info(force=True))
    assert first["cached"] is False
    assert first["isAdmin"] is False
    assert first["os"]["caption"] == "Microsoft Windows 11 Pro"
    assert first["cpu"]["cores"] == 8
    assert first["memory"]["usedPercent"] == 50.0
    assert first["disks"][0]["usedPercent"] == 75.0
    assert len(calls) == 1

    second = asyncio.run(system.system_info())
    assert second["cached"] is True
    assert len(calls) == 1


def test_status_endpoint(monkeypatch):
    monkeypatch.setattr(system, "run_powershell", _make_runner())
    client = _client()
    response = client.get("/api/maintenance/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["module"] == "maintenance"
    assert body["stage"] == "write"
    assert "cached" in body
    assert body["servedAt"].endswith("Z")
    assert body["os"]["caption"] == "Microsoft Windows 11 Pro"


def test_scan_endpoint_refresh(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(scanner, "run_powershell", _make_runner(calls))
    client = _client()

    response = client.get("/api/maintenance/scan?refresh=1")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["cached"] is False
    assert body["counts"] == {"total": 3, "ok": 1, "issues": 2}
    assert len(body["devices"]) == 3
    assert body["scannedAt"].endswith("Z")
    assert "servedAt" in body


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
