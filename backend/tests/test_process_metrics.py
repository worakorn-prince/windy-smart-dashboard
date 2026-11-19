from __future__ import annotations

import main
import metrics


class FakeMemoryInfo:
    def __init__(self, rss: int) -> None:
        self.rss = rss


class FakeProcess:
    def __init__(self, info: dict) -> None:
        self.info = info


class FakePsutil:
    def __init__(self, processes: list[FakeProcess]) -> None:
        self._processes = processes

    def process_iter(self, attrs):
        return iter(self._processes)


def test_processes_snapshot_excludes_idle_and_normalizes_cpu(monkeypatch):
    processes = [
        FakeProcess({
            "pid": 0,
            "name": "System Idle Process",
            "username": "SYSTEM",
            "cpu_percent": 731.2,
            "memory_percent": 0.00005,
        }),
        FakeProcess({
            "pid": 99,
            "name": "idle",
            "username": "SYSTEM",
            "cpu_percent": 600.0,
            "memory_percent": 0.1,
        }),
        FakeProcess({
            "pid": 100,
            "name": "app.exe",
            "username": "user",
            "cpu_percent": 45.4,
            "memory_percent": 12.34,
        }),
    ]
    monkeypatch.setattr(metrics.psutil, "process_iter", lambda attrs: iter(processes))
    monkeypatch.setattr(metrics, "cpu_count", lambda: 8)

    result = metrics.processes_snapshot()

    assert result == [{
        "pid": 100,
        "name": "app.exe",
        "user": "user",
        "cpu": 5.7,
        "ram_percent": 12.34,
    }]
    assert all(row["pid"] != 0 for row in result)
    assert all(row["name"].lower() != "system idle process" for row in result)


def test_collect_process_samples_excludes_idle_and_normalizes_cpu(monkeypatch):
    processes = [
        FakeProcess({
            "pid": 0,
            "name": "System Idle Process",
            "cpu_percent": 800.0,
            "memory_info": FakeMemoryInfo(900 * 1024 * 1024),
        }),
        FakeProcess({
            "pid": 100,
            "name": "app.exe",
            "cpu_percent": 45.4,
            "memory_info": FakeMemoryInfo(256 * 1024 * 1024),
        }),
    ]
    monkeypatch.setattr(main, "psutil", FakePsutil(processes))
    monkeypatch.setattr(main.metrics, "cpu_count", lambda: 8)

    result = main._collect_process_samples()

    assert result == [{
        "pid": 100,
        "name": "app.exe",
        "cpu_pct": 5.7,
        "mem_mb": 256.0,
    }]


def test_cpu_count_falls_back_to_one(monkeypatch):
    monkeypatch.setattr(metrics.psutil, "cpu_count", lambda: None)
    assert metrics.cpu_count() == 1

    def raise_error():
        raise RuntimeError("unavailable")

    monkeypatch.setattr(metrics.psutil, "cpu_count", raise_error)
    assert metrics.cpu_count() == 1


def test_is_idle_process_recognizes_pid_and_reserved_names():
    assert metrics.is_idle_process(0) is True
    assert metrics.is_idle_process(0, "anything") is True
    assert metrics.is_idle_process(100, "System Idle Process") is True
    assert metrics.is_idle_process(100, " idle ") is True
    assert metrics.is_idle_process(100, "app.exe") is False
