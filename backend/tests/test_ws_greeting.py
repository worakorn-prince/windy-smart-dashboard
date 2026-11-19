from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def reset_full_snapshot_cache():
    main._full_snapshot_cache.clear()
    main._processes_snapshot_cache.clear()
    main._system_snapshot_cache.clear()


def test_ws_metrics_greeting_sends_light_messages_before_full_snapshot(monkeypatch):
    threaded_calls: list[object] = []
    original_to_thread = asyncio.to_thread

    async def tracking_to_thread(func, /, *args, **kwargs):
        threaded_calls.append(func)
        return await original_to_thread(func, *args, **kwargs)

    def fake_processes_snapshot(top_n=10):
        return [{"pid": 100, "name": "app.exe", "cpu": 5.7, "ram_percent": 2.5}]

    def fake_system_snapshot():
        return {"hostname": "test-host"}

    full_snapshot_calls = 0

    async def fake_full_snapshot_async():
        nonlocal full_snapshot_calls
        full_snapshot_calls += 1
        return {"snapshot": "full"}

    monkeypatch.setattr(asyncio, "to_thread", tracking_to_thread)
    monkeypatch.setattr(main.metrics, "processes_snapshot", fake_processes_snapshot)
    monkeypatch.setattr(main.metrics, "system_snapshot", fake_system_snapshot)
    monkeypatch.setattr(main.metrics, "full_snapshot_async", fake_full_snapshot_async)
    monkeypatch.setattr(main.metrics, "cpu_count", lambda: 8)

    client = TestClient(main.app)
    with client.websocket_connect("/ws/metrics") as ws:
        processes = ws.receive_json()
        system = ws.receive_json()
        full = ws.receive_json()

    assert processes["type"] == "processes"
    assert processes["cpu_count"] == 8
    assert processes["processes"][0]["pid"] == 100
    assert system["type"] == "system"
    assert system["system"]["hostname"] == "test-host"
    assert full["type"] == "metrics"
    assert full["snapshot"] == "full"
    assert fake_processes_snapshot in threaded_calls
    assert fake_system_snapshot in threaded_calls
    assert full_snapshot_calls == 1
    assert fake_full_snapshot_async not in threaded_calls


def test_new_client_receives_full_snapshot_before_live_broadcast(monkeypatch):
    class TrackingConnections(set):
        def __init__(self) -> None:
            super().__init__()
            self.added = threading.Event()

        def add(self, value) -> None:
            super().add(value)
            self.added.set()

    connections = TrackingConnections()
    broadcast_messages: list[tuple[str, dict]] = []
    threaded_calls: list[object] = []
    original_to_thread = asyncio.to_thread

    async def tracking_to_thread(func, /, *args, **kwargs):
        threaded_calls.append(func)
        return await original_to_thread(func, *args, **kwargs)

    async def fake_broadcast(channel, message):
        broadcast_messages.append((channel, message))
        for socket in list(connections):
            await socket.send_json(message)

    def fake_processes_snapshot(top_n=10):
        return [{"pid": 100, "name": "app.exe", "cpu": 5.7, "ram_percent": 2.5}]

    def fake_system_snapshot():
        return {"hostname": "test-host"}

    async def fake_full_snapshot_async():
        live_message = {"type": "metrics", "cpu": {"overall": 1.0}}
        await main.manager.broadcast("metrics", live_message)
        assert len(connections) == 0
        assert not connections.added.is_set()
        return {"snapshot": "full"}

    monkeypatch.setattr(asyncio, "to_thread", tracking_to_thread)
    monkeypatch.setattr(main.manager, "metrics", connections)
    monkeypatch.setattr(main.manager, "broadcast", fake_broadcast)
    monkeypatch.setattr(main.metrics, "processes_snapshot", fake_processes_snapshot)
    monkeypatch.setattr(main.metrics, "system_snapshot", fake_system_snapshot)
    monkeypatch.setattr(main.metrics, "full_snapshot_async", fake_full_snapshot_async)
    monkeypatch.setattr(main.metrics, "cpu_count", lambda: 8)

    client = TestClient(main.app)
    with client.websocket_connect("/ws/metrics") as ws:
        assert ws.receive_json()["type"] == "processes"
        assert ws.receive_json()["type"] == "system"
        assert ws.receive_json()["type"] == "metrics"

        assert connections.added.wait(timeout=1)
        assert len(connections) == 1
        assert broadcast_messages == [("metrics", {"type": "metrics", "cpu": {"overall": 1.0}})]
        assert fake_processes_snapshot in threaded_calls
        assert fake_system_snapshot in threaded_calls


def test_full_snapshot_single_flight_for_concurrent_clients(monkeypatch):
    call_count = 0

    async def fake_full_snapshot_async():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"snapshot": "full", "call": call_count}

    monkeypatch.setattr(main.metrics, "full_snapshot_async", fake_full_snapshot_async)

    async def get_snapshots():
        return await asyncio.gather(
            main._get_full_snapshot(30),
            main._get_full_snapshot(30),
        )

    results = asyncio.run(get_snapshots())

    assert call_count == 1
    assert results[0][0] == results[1][0]
    assert results[0][0]["snapshot"] == "full"
    assert sorted(freshly_computed for _, freshly_computed in results) == [False, True]


def test_full_snapshot_cache_hit_does_not_recompute(monkeypatch):
    call_count = 0

    async def fake_full_snapshot_async():
        nonlocal call_count
        call_count += 1
        return {"snapshot": "full", "call": call_count}

    monkeypatch.setattr(main.metrics, "full_snapshot_async", fake_full_snapshot_async)

    async def get_snapshots():
        first = await main._get_full_snapshot(30)
        second = await main._get_full_snapshot(30)
        return first, second

    first, second = asyncio.run(get_snapshots())

    assert call_count == 1
    assert first[0] == second[0]
    assert first[1] is True
    assert second[1] is False


def test_ws_metrics_handles_client_disconnect_during_full_snapshot(monkeypatch):
    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def accept(self) -> None:
            pass

        async def send_json(self, payload: dict) -> None:
            message_type = payload["type"]
            self.sent.append(message_type)
            if message_type == "metrics":
                raise RuntimeError('Cannot call "send" once a close message has been sent.')

        async def receive_text(self) -> str:
            return ""

    def fake_processes_snapshot(top_n=10):
        return [{"pid": 100, "name": "app.exe", "cpu": 5.7, "ram_percent": 2.5}]

    def fake_system_snapshot():
        return {"hostname": "test-host"}

    async def fake_full_snapshot_async():
        return {"snapshot": "full"}

    monkeypatch.setattr(main.metrics, "processes_snapshot", fake_processes_snapshot)
    monkeypatch.setattr(main.metrics, "system_snapshot", fake_system_snapshot)
    monkeypatch.setattr(main.metrics, "full_snapshot_async", fake_full_snapshot_async)
    monkeypatch.setattr(main.metrics, "cpu_count", lambda: 8)

    connections: set[object] = set()
    monkeypatch.setattr(main.manager, "metrics", connections)
    websocket = FakeWebSocket()

    asyncio.run(main.ws_metrics(websocket))

    assert websocket.sent == ["processes", "system", "metrics"]
    assert len(connections) == 0


def test_processes_snapshot_single_flight_for_concurrent_getters(monkeypatch):
    call_count = 0

    def fake_processes_snapshot(top_n=10):
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)
        return [{"pid": 100, "name": "app.exe", "top_n": top_n, "call": call_count}]

    monkeypatch.setattr(main.metrics, "processes_snapshot", fake_processes_snapshot)

    async def get_snapshots():
        return await asyncio.gather(
            main._processes_snapshot_cache.get(refresh_if_stale=True),
            main._processes_snapshot_cache.get(refresh_if_stale=True),
        )

    results = asyncio.run(get_snapshots())

    assert call_count == 1
    assert results[0][0] == results[1][0]
    assert results[0][0][0]["top_n"] == 10
    assert sorted(freshly_computed for _, freshly_computed in results) == [False, True]


def test_processes_snapshot_cache_hit_does_not_recompute(monkeypatch):
    call_count = 0

    def fake_processes_snapshot(top_n=10):
        nonlocal call_count
        call_count += 1
        return [{"pid": 100, "name": "app.exe", "call": call_count}]

    monkeypatch.setattr(main.metrics, "processes_snapshot", fake_processes_snapshot)

    async def get_snapshots():
        first = await main._processes_snapshot_cache.get(refresh_if_stale=True)
        second = await main._processes_snapshot_cache.get(refresh_if_stale=True)
        return first, second

    first, second = asyncio.run(get_snapshots())

    assert call_count == 1
    assert first[0] == second[0]
    assert first[1] is True
    assert second[1] is False


def test_system_snapshot_single_flight_and_cache_hit(monkeypatch):
    call_count = 0

    def fake_system_snapshot():
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)
        return {"hostname": "test-host", "call": call_count}

    monkeypatch.setattr(main.metrics, "system_snapshot", fake_system_snapshot)

    async def get_snapshots():
        concurrent = await asyncio.gather(
            main._system_snapshot_cache.get(refresh_if_stale=True),
            main._system_snapshot_cache.get(refresh_if_stale=True),
        )
        cached = await main._system_snapshot_cache.get(refresh_if_stale=True)
        return concurrent, cached

    concurrent, cached = asyncio.run(get_snapshots())

    assert call_count == 1
    assert concurrent[0][0] == concurrent[1][0]
    assert cached[0] == concurrent[0][0]
    assert sorted(freshly_computed for _, freshly_computed in concurrent) == [False, True]
    assert cached[1] is False


def test_refresh_if_stale_false_uses_cache_until_hard_limit(monkeypatch):
    call_count = 0
    now = 100.0

    def fake_processes_snapshot(top_n=10):
        nonlocal call_count
        call_count += 1
        return [{"pid": 100, "name": "app.exe", "call": call_count}]

    monkeypatch.setattr(main.time, "monotonic", lambda: now)
    monkeypatch.setattr(main.metrics, "processes_snapshot", fake_processes_snapshot)

    async def get_snapshots():
        first = await main._processes_snapshot_cache.get(refresh_if_stale=True)
        within_hard_limit = await main._processes_snapshot_cache.get(refresh_if_stale=False)
        return first, within_hard_limit

    first, within_hard_limit = asyncio.run(get_snapshots())
    assert call_count == 1
    assert within_hard_limit[0] == first[0]
    assert within_hard_limit[1] is False

    now += main.PROCESS_INTERVAL + 0.1

    async def get_cached_snapshot():
        return await main._processes_snapshot_cache.get(refresh_if_stale=False)

    within_hard_limit = asyncio.run(get_cached_snapshot())
    assert call_count == 1
    assert within_hard_limit[1] is False

    now += main.PROCESS_INTERVAL * 2 + 0.2

    async def get_expired_snapshot():
        return await main._processes_snapshot_cache.get(refresh_if_stale=False)

    beyond_hard_limit = asyncio.run(get_expired_snapshot())
    assert call_count == 2
    assert beyond_hard_limit[0][0]["call"] == 2
    assert beyond_hard_limit[1] is True
