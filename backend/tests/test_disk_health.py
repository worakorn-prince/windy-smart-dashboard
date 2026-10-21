from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import config
import disk_health
import main


def _iso(days_ago: float = 0.0) -> str:
    moment = datetime.now(UTC) - timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sample(mount: str, used_gb: float, total_gb: float = 100.0,
            days_ago: float = 0.0) -> dict:
    return {
        "mount": mount,
        "used_gb": used_gb,
        "total_gb": total_gb,
        "ts": _iso(days_ago),
    }


def _trend(used_values: list[float], total_gb: float | None = 100.0) -> list[dict]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    samples = []
    for index, used in enumerate(used_values):
        sample = {
            "ts": (base + timedelta(days=index)).isoformat(),
            "used_gb": used,
        }
        if total_gb is not None:
            sample["total_gb"] = total_gb
        samples.append(sample)
    return samples


@pytest.fixture()
def disk_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "disk_health.db")
    disk_health.close()
    yield
    disk_health.close()


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_record_and_query_roundtrip(disk_db):
    written = disk_health.record_samples([
        _sample("C:\\", 10.0, days_ago=2),
        _sample("C:\\", 12.0, days_ago=1),
        _sample("D:\\", 5.0, total_gb=500.0, days_ago=1),
    ])
    assert written == 3

    rows = disk_health.get_samples("C:\\")
    assert [row["used_gb"] for row in rows] == [10.0, 12.0]
    assert [row["total_gb"] for row in rows] == [100.0, 100.0]
    assert rows[0]["ts"] < rows[1]["ts"]

    other = disk_health.get_samples("D:\\")
    assert len(other) == 1
    assert other[0]["used_gb"] == 5.0
    assert disk_health.get_samples("Z:\\") == []
    assert disk_health.record_samples([]) == 0


def test_get_samples_respects_days_window(disk_db):
    disk_health.record_samples([
        {"mount": "C:\\", "used_gb": 1.0, "total_gb": 100.0,
         "ts": "2000-01-01T00:00:00.000000Z"},
        _sample("C:\\", 2.0, days_ago=0.5),
    ])
    rows = disk_health.get_samples("C:\\", days=7)
    assert len(rows) == 1
    assert rows[0]["used_gb"] == 2.0


def test_prune_removes_old_rows(disk_db):
    disk_health.record_samples([
        {"mount": "C:\\", "used_gb": 1.0, "total_gb": 100.0,
         "ts": "2000-01-01T00:00:00.000000Z"},
        _sample("C:\\", 2.0, days_ago=1),
    ])
    assert disk_health.prune(days=30) == 1
    rows = disk_health.get_samples("C:\\", days=30)
    assert [row["used_gb"] for row in rows] == [2.0]
    assert disk_health.prune(days=30) == 0


def test_record_samples_best_effort_on_broken_db(monkeypatch):
    def boom():
        raise RuntimeError("no db")

    monkeypatch.setattr(disk_health, "_get_conn", boom)
    assert disk_health.record_samples([
        {"mount": "C:\\", "used_gb": 1.0, "total_gb": 2.0},
    ]) == 0


def test_predict_rising_trend():
    result = disk_health.predict_days_to_full(_trend([10.0, 11.0, 12.0]))
    assert result["samples"] == 3
    assert result["trend_gb_per_day"] == pytest.approx(1.0)
    assert result["days_to_full"] == pytest.approx(88.0)


def test_predict_falling_trend_has_no_days():
    result = disk_health.predict_days_to_full(_trend([12.0, 11.0, 10.0]))
    assert result["samples"] == 3
    assert result["trend_gb_per_day"] == pytest.approx(-1.0)
    assert result["days_to_full"] is None


def test_predict_flat_trend_has_no_days():
    result = disk_health.predict_days_to_full(_trend([10.0, 10.0, 10.0]))
    assert result["samples"] == 3
    assert result["trend_gb_per_day"] == pytest.approx(0.0)
    assert result["days_to_full"] is None


def test_predict_requires_three_samples():
    result = disk_health.predict_days_to_full(_trend([10.0, 11.0]))
    assert result == {"days_to_full": None, "trend_gb_per_day": None, "samples": 2}
    assert disk_health.predict_days_to_full([]) == {
        "days_to_full": None, "trend_gb_per_day": None, "samples": 0,
    }


def test_predict_without_total_capacity():
    result = disk_health.predict_days_to_full(_trend([10.0, 11.0, 12.0], total_gb=None))
    assert result["trend_gb_per_day"] == pytest.approx(1.0)
    assert result["days_to_full"] is None


def _patch_powershell(monkeypatch, *, stdout: str, stderr: str = "",
                      returncode: int = 0) -> None:
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(disk_health.subprocess, "run", fake_run)


def test_smart_info_parses_array(monkeypatch):
    payload = [
        {"FriendlyName": "Disk0", "MediaType": "SSD", "HealthStatus": "Healthy",
         "OperationalStatus": "OK"},
        {"FriendlyName": "Disk1", "MediaType": "HDD", "HealthStatus": "Warning",
         "OperationalStatus": "Degraded"},
    ]
    _patch_powershell(monkeypatch, stdout=json.dumps(payload))
    info = disk_health.smart_info()
    assert info["available"] is True
    assert info["disks"] == payload


def test_smart_info_parses_single_object(monkeypatch):
    payload = {"FriendlyName": "Disk0", "MediaType": "SSD",
               "HealthStatus": "Healthy", "OperationalStatus": "OK"}
    _patch_powershell(monkeypatch, stdout=json.dumps(payload))
    info = disk_health.smart_info()
    assert info["available"] is True
    assert info["disks"] == [payload]


def test_smart_info_invalid_json_returns_unavailable(monkeypatch):
    _patch_powershell(monkeypatch, stdout="not json")
    info = disk_health.smart_info()
    assert info["available"] is False
    assert "invalid JSON" in info["error"]


def test_smart_info_nonzero_exit_returns_unavailable(monkeypatch):
    _patch_powershell(monkeypatch, stdout="", stderr="Get-PhysicalDisk failed",
                      returncode=1)
    info = disk_health.smart_info()
    assert info["available"] is False
    assert "Get-PhysicalDisk failed" in info["error"]


def test_smart_info_subprocess_error_returns_unavailable(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("powershell missing")

    monkeypatch.setattr(disk_health.subprocess, "run", boom)
    info = disk_health.smart_info()
    assert info["available"] is False
    assert "powershell missing" in info["error"]


def test_disk_usage_keeps_only_fixed_drives(monkeypatch):
    parts = [
        SimpleNamespace(mountpoint="C:\\", fstype="NTFS", opts="rw,fixed"),
        SimpleNamespace(mountpoint="D:\\", fstype="", opts="rw,fixed"),
        SimpleNamespace(mountpoint="E:\\", fstype="CDFS", opts="ro,cdrom"),
        SimpleNamespace(mountpoint="F:\\", fstype="FAT32", opts="rw,removable"),
        SimpleNamespace(mountpoint="Z:\\", fstype="NTFS", opts="rw,remote"),
        SimpleNamespace(mountpoint="G:\\", fstype="NTFS", opts="rw,fixed"),
    ]

    class FakePsutil:
        Error = Exception

        @staticmethod
        def disk_partitions(all=False):
            return parts

        @staticmethod
        def disk_usage(mountpoint):
            if mountpoint == "G:\\":
                raise OSError("denied")
            return SimpleNamespace(total=200 * 1024 ** 3, used=50 * 1024 ** 3,
                                   percent=25.0)

    monkeypatch.setattr(disk_health, "psutil", FakePsutil)
    rows = disk_health.disk_usage()
    assert rows == [{
        "mount": "C:\\",
        "total_gb": 200.0,
        "used_gb": 50.0,
        "used_pct": 25.0,
    }]


def test_endpoint_returns_disks_smart_and_predictions(client, disk_db, monkeypatch):
    base = datetime.now(UTC)
    samples = [
        {
            "mount": "C:\\",
            "used_gb": 70.0 + index,
            "total_gb": 100.0,
            "ts": (base - timedelta(days=2 - index)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        for index in range(3)
    ]
    assert disk_health.record_samples(samples) == 3

    monkeypatch.setattr(disk_health, "disk_usage", lambda: [
        {"mount": "C:\\", "total_gb": 100.0, "used_gb": 72.0, "used_pct": 72.0},
        {"mount": "D:\\", "total_gb": 500.0, "used_gb": 250.0, "used_pct": 50.0},
    ])
    monkeypatch.setattr(disk_health, "smart_info", lambda: {
        "available": True,
        "disks": [{"FriendlyName": "NVMe", "MediaType": "SSD",
                   "HealthStatus": "Healthy", "OperationalStatus": "OK"}],
    })

    response = client.get("/api/health/disk")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"disks", "smart", "predictions", "sampled_at"}
    assert [disk["mount"] for disk in body["disks"]] == ["C:\\", "D:\\"]
    assert body["smart"]["available"] is True
    assert body["smart"]["disks"][0]["HealthStatus"] == "Healthy"
    assert body["sampled_at"]

    predictions = {item["mount"]: item for item in body["predictions"]}
    assert predictions["C:\\"]["samples"] == 3
    assert predictions["C:\\"]["trend_gb_per_day"] == pytest.approx(1.0)
    assert predictions["C:\\"]["days_to_full"] == pytest.approx(28.0)
    assert predictions["D:\\"] == {
        "mount": "D:\\",
        "days_to_full": None,
        "trend_gb_per_day": None,
        "samples": 0,
    }
