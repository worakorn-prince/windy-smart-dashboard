"""WebSocket hub for /ws/internet (spec §3).

Rules enforced here (spec §3.4):
- bounded outgoing queue (max 100 pending messages per client, oldest dropped),
- disconnected clients removed immediately,
- broadcasting never blocks collectors (sync enqueue + fire-and-forget tasks),
- separate channel from /ws/metrics.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("dashboard.internet_insights.services.ws_hub")

MESSAGE_TYPES = (
    "internet_status",
    "quality_sample",
    "interface_change",
    "dns_status",
    "incident_created",
    "incident_updated",
    "diagnostic_progress",
    "diagnostic_completed",
    "collector_status",
)

MAX_PENDING_PER_CLIENT = 100


def make_message(msg_type: str, **fields: Any) -> dict[str, Any]:
    """Build a WS message with the mandatory 'type' and 'ts' fields."""
    if msg_type not in MESSAGE_TYPES:
        raise ValueError(f"unknown WS message type: {msg_type}")
    return {"type": msg_type, "ts": time.time(), **fields}


class InternetWSHub:
    """Connection manager + broadcaster for the /ws/internet channel."""

    def __init__(self, max_pending: int = MAX_PENDING_PER_CLIENT):
        self._clients: dict[WebSocket, asyncio.Queue[dict[str, Any]]] = {}
        self._senders: dict[WebSocket, asyncio.Task[None]] = {}
        self.max_pending = max_pending

    # ---- connections ----

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def connect(self, ws: WebSocket) -> asyncio.Queue[dict[str, Any]]:
        """Register a client and return its bounded outgoing queue."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self.max_pending)
        self._clients[ws] = queue
        return queue

    def start_sender(self, ws: WebSocket, queue: asyncio.Queue[dict[str, Any]]) -> asyncio.Task[None]:
        """Spawn the per-client sender task (non-blocking)."""
        task = asyncio.create_task(self._sender_loop(ws, queue))
        self._senders[ws] = task
        return task

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a disconnected client immediately and cancel its sender."""
        self._clients.pop(ws, None)
        task = self._senders.pop(ws, None)
        if task is not None and not task.done():
            task.cancel()

    # ---- sending ----

    async def _sender_loop(self, ws: WebSocket, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Drain the queue to the socket; any failure drops the client."""
        while True:
            message = await queue.get()
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)
                return

    def broadcast(self, message: dict[str, Any]) -> int:
        """Enqueue a message for every client without blocking.

        Event-loop scoped: asyncio.Queue is not thread-safe, so call this
        from coroutines/tasks running in the loop that owns the client
        queues. put_nowait never blocks; when a queue is full the oldest
        message is dropped to keep latency bounded.
        """
        delivered = 0
        for ws, queue in list(self._clients.items()):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            try:
                queue.put_nowait(message)
                delivered += 1
            except Exception:
                logger.debug("dropped unreachable ws client during broadcast")
                self.disconnect(ws)
        return delivered

    # ---- typed helpers (spec §3.2) ----

    def emit(self, msg_type: str, **fields: Any) -> int:
        """Build a typed message and broadcast it."""
        return self.broadcast(make_message(msg_type, **fields))

    def emit_async(self, msg_type: str, **fields: Any) -> asyncio.Task[int]:
        """Fire-and-forget typed broadcast (spec §3.4: never block the caller).

        broadcast() itself is sync/non-blocking (put_nowait); wrapping it in a
        task just guarantees the caller's loop is never tied to delivery.
        """
        return asyncio.create_task(self._emit_coro(msg_type, **fields))

    async def _emit_coro(self, msg_type: str, **fields: Any) -> int:
        return self.emit(msg_type, **fields)


# ---- process-wide shared hub ----
# The /ws/internet handler (main.py) and the incident endpoints (router.py)
# must broadcast through the SAME hub instance, otherwise incident events
# never reach connected clients.

_shared_hub: InternetWSHub | None = None


def get_internet_ws_hub() -> InternetWSHub:
    """Return the process-wide InternetWSHub (lazily created)."""
    global _shared_hub
    if _shared_hub is None:
        _shared_hub = InternetWSHub()
    return _shared_hub
