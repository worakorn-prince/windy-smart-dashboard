"""Tests for the Internet Insights WebSocket hub (INET-M5, spec §3)."""

from __future__ import annotations

import asyncio

import pytest

from internet_insights.services.ws_hub import (
    MAX_PENDING_PER_CLIENT,
    MESSAGE_TYPES,
    InternetWSHub,
    make_message,
)


class FakeWebSocket:
    """Minimal WebSocket stand-in that records sent messages."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("connection closed")
        self.sent.append(payload)


def test_make_message_has_type_and_ts():
    msg = make_message("incident_created", incident_id="inc-1")
    assert msg["type"] == "incident_created"
    assert isinstance(msg["ts"], float)
    assert msg["incident_id"] == "inc-1"
    assert msg["ts"] > 0


def test_make_message_unknown_type_raises_valueerror():
    with pytest.raises(ValueError, match="unknown WS message type"):
        make_message("not_a_type")


def test_all_message_types_accepted():
    for msg_type in MESSAGE_TYPES:
        msg = make_message(msg_type)
        assert msg["type"] == msg_type
        assert "ts" in msg


def test_message_types_count():
    assert len(MESSAGE_TYPES) == 9


def test_max_pending_constant():
    assert MAX_PENDING_PER_CLIENT == 100


@pytest.mark.asyncio
async def test_connect_returns_queue_and_counts_client():
    hub = InternetWSHub()
    ws = FakeWebSocket()
    queue = hub.connect(ws)
    assert isinstance(queue, asyncio.Queue)
    assert hub.client_count == 1
    assert queue.maxsize == hub.max_pending


@pytest.mark.asyncio
async def test_disconnect_removes_client_and_cancels_sender():
    hub = InternetWSHub()
    ws = FakeWebSocket()
    queue = hub.connect(ws)
    task = hub.start_sender(ws, queue)
    hub.emit("collector_status", state="up")
    await asyncio.sleep(0.05)
    assert len(ws.sent) == 1
    hub.disconnect(ws)
    assert hub.client_count == 0
    await asyncio.sleep(0.05)
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_sender_loop_failure_disconnects_client():
    hub = InternetWSHub()
    ws = FakeWebSocket(fail=True)
    queue = hub.connect(ws)
    hub.start_sender(ws, queue)
    hub.emit("collector_status", state="up")
    await asyncio.sleep(0.05)
    assert hub.client_count == 0


@pytest.mark.asyncio
async def test_broadcast_delivers_to_all_clients():
    hub = InternetWSHub()
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()
    q1 = hub.connect(ws1)
    q2 = hub.connect(ws2)
    msg = make_message("internet_status", ok=True)
    delivered = hub.broadcast(msg)
    assert delivered == 2
    assert await q1.get() is msg
    assert await q2.get() is msg


@pytest.mark.asyncio
async def test_broadcast_zero_clients_returns_zero():
    hub = InternetWSHub()
    assert hub.broadcast(make_message("internet_status")) == 0


@pytest.mark.asyncio
async def test_broadcast_drops_oldest_when_queue_full():
    hub = InternetWSHub(max_pending=100)
    ws = FakeWebSocket()
    queue = hub.connect(ws)
    for i in range(120):
        hub.broadcast({"type": "internet_status", "seq": i})
    assert queue.qsize() <= hub.max_pending
    assert queue.qsize() == 100
    first = queue.get_nowait()
    assert first["seq"] == 20
    drained = [queue.get_nowait() for _ in range(queue.qsize())]
    assert drained[-1]["seq"] == 119


@pytest.mark.asyncio
async def test_broadcast_on_full_queue_still_has_latest():
    hub = InternetWSHub(max_pending=100)
    ws = FakeWebSocket()
    queue = hub.connect(ws)
    latest = make_message("incident_created", id="latest")
    for i in range(150):
        hub.broadcast({"type": "internet_status", "seq": i})
    hub.broadcast(latest)
    assert queue.qsize() == 100
    drained = [queue.get_nowait() for _ in range(100)]
    assert drained[-1] is latest


@pytest.mark.asyncio
async def test_emit_builds_and_broadcasts():
    hub = InternetWSHub()
    ws = FakeWebSocket()
    queue = hub.connect(ws)
    delivered = hub.emit("incident_updated", incident_id="inc-9", status="resolved")
    assert delivered == 1
    msg = queue.get_nowait()
    assert msg["type"] == "incident_updated"
    assert msg["incident_id"] == "inc-9"
    assert msg["status"] == "resolved"
    assert "ts" in msg


@pytest.mark.asyncio
async def test_emit_async_delivers_message():
    hub = InternetWSHub()
    ws = FakeWebSocket()
    queue = hub.connect(ws)
    task = hub.emit_async("dns_status", ok=True)
    delivered = await task
    assert delivered == 1
    msg = queue.get_nowait()
    assert msg["type"] == "dns_status"
    assert msg["ok"] is True


@pytest.mark.asyncio
async def test_start_sender_drains_queue_to_socket():
    hub = InternetWSHub()
    ws = FakeWebSocket()
    queue = hub.connect(ws)
    hub.start_sender(ws, queue)
    hub.emit("quality_sample", rtt_ms=12.5)
    hub.emit("quality_sample", rtt_ms=13.5)
    await asyncio.sleep(0.05)
    assert [m["rtt_ms"] for m in ws.sent] == [12.5, 13.5]
    hub.disconnect(ws)
    await asyncio.sleep(0.05)
