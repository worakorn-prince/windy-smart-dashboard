from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import config
import main
import process_history


@pytest.fixture()
def ph_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "process_history.db")
    process_history.close()
    yield
    process_history.close()


@pytest.fixture()
def client():
    return TestClient(main.app)


class FakeMem:
    def __init__(self, rss: int) -> None:
        self.rss = rss


class FakeProc:
    def __init__(self, pid: int, name: str, rss: int = 50 * 1024 * 1024) -> None:
        self.pid = pid
        self._name = name
        self._rss = rss
        self._parent: FakeProc | None = None
        self._children: list[FakeProc] = []

    def name(self) -> str:
        return self._name

    def exe(self) -> str:
        return f"C:\\bin\\{self._name}.exe"

    def cmdline(self) -> list[str]:
        return [self.exe(), "--flag"]

    def username(self) -> str:
        return "DOMAIN\\user"

    def status(self) -> str:
        return "running"

    def create_time(self) -> float:
        return 1700000000.0

    def cpu_percent(self, interval=None) -> float:
        return 12.34

    def memory_info(self) -> FakeMem:
        return FakeMem(self._rss)

    def memory_percent(self) -> float:
        return 1.5

    def parent(self) -> FakeProc | None:
        return self._parent

    def children(self) -> list[FakeProc]:
        return self._children


class FakeNoSuchProcess(Exception):
    pass


class FakeAccessDenied(Exception):
    pass


class FakePsutil:
    NoSuchProcess = FakeNoSuchProcess
    AccessDenied = FakeAccessDenied

    def __init__(self, table: dict[int, FakeProc]) -> None:
        self._table = table

    def Process(self, pid: int) -> FakeProc:
        if pid not in self._table:
            raise FakeNoSuchProcess(pid)
        return self._table[pid]


def _tree() -> tuple[FakeProc, dict[int, FakeProc]]:
    root = FakeProc(100, "root")
    parent = FakeProc(50, "shell")
    a = FakeProc(101, "child-a")
    b = FakeProc(102, "grand-b")
    c = FakeProc(103, "great-c")
    d = FakeProc(104, "too-deep-d")
    root._parent = parent
    root._children = [a]
    a._children = [b]
    b._children = [c]
    c._children = [d]
    table = {p.pid: p for p in (root, parent, a, b, c, d)}
    return root, table


def _net_rows() -> list[dict]:
    return [
        {"pid": 100, "status": "LISTEN", "laddr": ["0.0.0.0", 8080], "type": 1},
        {"pid": 100, "status": "LISTEN", "laddr": ["0.0.0.0", 8080], "type": 1},
        {"pid": 100, "status": "LISTEN", "laddr": ["0.0.0.0", 5353], "type": 2},
        {"pid": 100, "status": "ESTABLISHED", "laddr": ["127.0.0.1", 50000], "type": 1},
        {"pid": 100, "status": "ESTABLISHED", "laddr": ["127.0.0.1", 50001], "type": 1},
        {"pid": 999, "status": "LISTEN", "laddr": ["0.0.0.0", 9999], "type": 1},
    ]


def _patch_process_env(monkeypatch) -> None:
    _, table = _tree()
    monkeypatch.setattr(main, "psutil", FakePsutil(table))
    monkeypatch.setattr(main, "_net_connection_rows", _net_rows)


def test_detail_shape_tree_and_ports(client, monkeypatch, ph_db):
    _patch_process_env(monkeypatch)
    r = client.get("/api/processes/100")
    assert r.status_code == 200
    body = r.json()

    assert set(body) == {
        "pid", "name", "exe", "cmdline", "username", "status", "create_time",
        "cpu_pct", "mem_mb", "mem_pct", "parent", "children", "ports",
        "connections_count",
    }
    assert body["pid"] == 100
    assert body["name"] == "root"
    assert body["exe"].endswith("root.exe")
    assert body["cmdline"] == ["C:\\bin\\root.exe", "--flag"]
    assert body["username"] == "DOMAIN\\user"
    assert body["status"] == "running"
    assert body["create_time"] == 1700000000.0
    assert body["cpu_pct"] == 12.3
    assert body["mem_mb"] == 50.0
    assert body["mem_pct"] == 1.5

    assert body["parent"] == {"pid": 50, "name": "shell"}
    # Tree is capped at three child levels (101 -> 102 -> 103).
    child = body["children"][0]
    assert child["pid"] == 101
    grand = child["children"][0]
    assert grand["pid"] == 102
    great = grand["children"][0]
    assert great["pid"] == 103
    assert great["children"] == []

    assert body["ports"] == [
        {"port": 5353, "protocol": "udp", "state": "LISTEN"},
        {"port": 8080, "protocol": "tcp", "state": "LISTEN"},
    ]
    assert body["connections_count"] == 2


def test_detail_404_for_unknown_pid(client, monkeypatch, ph_db):
    _patch_process_env(monkeypatch)
    r = client.get("/api/processes/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "process_not_found"


def test_history_record_query_roundtrip(client, ph_db):
    written = process_history.record_samples([
        {"pid": 100, "name": "root", "cpu_pct": 1.0, "mem_mb": 10.0,
         "ts": "2026-01-01T00:00:00.000000Z"},
        {"pid": 100, "name": "root", "cpu_pct": 2.0, "mem_mb": 20.0,
         "ts": "2026-01-01T00:00:10.000000Z"},
        {"pid": 200, "name": "other", "cpu_pct": 9.0, "mem_mb": 30.0,
         "ts": "2026-01-01T00:00:20.000000Z"},
    ])
    assert written == 3

    rows = process_history.get_history(100)
    assert [r["cpu_pct"] for r in rows] == [1.0, 2.0]
    assert [r["mem_mb"] for r in rows] == [10.0, 20.0]

    newest = process_history.get_history(100, limit=1)
    assert len(newest) == 1
    assert newest[0]["ts"] == "2026-01-01T00:00:10.000000Z"

    api = client.get("/api/processes/100/history", params={"limit": 60})
    assert api.status_code == 200
    assert api.json() == rows


def test_history_limit_cap_422(client, ph_db):
    assert client.get("/api/processes/100/history", params={"limit": 0}).status_code == 422
    assert client.get("/api/processes/100/history", params={"limit": 241}).status_code == 422
    assert client.get("/api/processes/100/history", params={"limit": 240}).status_code == 200


def test_prune_removes_old_rows(ph_db):
    process_history.record_samples([
        {"pid": 100, "name": "root", "cpu_pct": 1.0, "mem_mb": 10.0,
         "ts": "2000-01-01T00:00:00.000000Z"},
        {"pid": 100, "name": "root", "cpu_pct": 2.0, "mem_mb": 20.0,
         "ts": "2999-01-01T00:00:00.000000Z"},
    ])
    assert process_history.prune(days=7) == 1
    rows = process_history.get_history(100)
    assert len(rows) == 1
    assert rows[0]["cpu_pct"] == 2.0
    assert process_history.prune(days=7) == 0


def test_record_samples_best_effort_on_broken_db(monkeypatch):
    def boom():
        raise RuntimeError("no db")

    monkeypatch.setattr(process_history, "_get_conn", boom)
    assert process_history.record_samples([
        {"pid": 1, "name": "x", "cpu_pct": 0.0, "mem_mb": 0.0},
    ]) == 0
