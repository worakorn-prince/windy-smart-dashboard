"""Windy Smart Dashboard — FastAPI backend.

Endpoints:
  WS  /ws/metrics        — system metrics push (1Hz)
  WS  /ws/security       — live security events

  GET /                  — serve frontend build (production)
  GET /api/system         — initial system info
  POST /api/speedtest     — run Internet speed test
  GET /api/security/suspicious      — current suspicious countries
  PUT /api/security/suspicious      — override (persisted to cache)
  POST /api/security/audit           — run an on-demand audit
  POST /api/security/kill            — kill process by pid
  POST /api/security/block           — block outbound IP
  POST /api/security/unblock        — delete a block rule
  GET /api/security/blocked          — list block rules
  POST /api/security/export          — {fmt: pdf|html|json} -> returns file
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

import config
import history
import metrics
import speedtest_worker
from alerts import evaluate as evaluate_alerts, send_toast
from config import (
    FRONTEND_DIST,
    HOST,
    METRICS_INTERVAL,
    PING_TARGET,
    PROCESS_INTERVAL,
    UPTIME_INTERVAL,
)
from security import actions
from security import audit as audit_mod
from security import monitor as sec_monitor

# ---- logging ---- #
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dashboard")


# ---- State ---- #
class ConnectionManager:
    """Track active WebSocket subscribers per channel."""
    def __init__(self) -> None:
        self.metrics: set[WebSocket] = set()
        self.security: set[WebSocket] = set()

    async def broadcast(self, channel: str, message: dict[str, Any]) -> None:
        sockets = getattr(self, channel)
        dead = []
        for ws in list(sockets):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for d in dead:
            sockets.discard(d)


manager = ConnectionManager()
sec_mon: sec_monitor.SecurityMonitor | None = None
suspicious_countries_state: list[str] = list(config.DEFAULT_SUSPICIOUS_COUNTRIES)


def load_suspicious() -> None:
    global suspicious_countries_state
    p = config.CACHE_DIR / "suspicious.json"
    if p.exists():
        with contextlib.suppress(OSError, json.JSONDecodeError):
            suspicious_countries_state = json.loads(p.read_text(encoding="utf-8"))


def save_suspicious() -> None:
    p = config.CACHE_DIR / "suspicious.json"
    p.write_text(json.dumps(suspicious_countries_state), encoding="utf-8")


load_suspicious()


# ---- FastAPI app ---- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    global sec_mon
    logger.info("Dashboard starting on http://%s:%d", HOST, config.PORT)

    async def _sec_emit(evt) -> None:
        await manager.broadcast("security", {"type": "security_event", **evt.to_dict()})

    sec_mon = sec_monitor.SecurityMonitor(on_event=_sec_emit, suspicious=list(suspicious_countries_state))
    await sec_mon.start()

    metrics_task = asyncio.create_task(_metrics_loop())
    process_task = asyncio.create_task(_process_loop())
    uptime_task = asyncio.create_task(_uptime_loop())
    history_task = asyncio.create_task(_history_loop())
    try:
        yield
    finally:
        if sec_mon:
            await sec_mon.stop()
        for t in (metrics_task, process_task, uptime_task, history_task):
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t


app = FastAPI(title="Windy Smart Dashboard", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{config.PORT}", "http://127.0.0.1:5173",
                   "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Background pushers ---- #

async def _metrics_loop() -> None:
    """Push full metrics snapshot every METRICS_INTERVAL seconds.

    full_snapshot() performs blocking subprocess/WMI calls, so it runs in a
    worker thread to keep the event loop (and thus WebSocket broadcasts)
    responsive.
    """
    last_ping = 0.0
    last_ping_v = 0.0
    ping_period = 5.0
    while True:
        try:
            snap = await asyncio.to_thread(metrics.full_snapshot)
            # Ping latency (best-effort, low frequency to avoid noise).
            now = asyncio.get_event_loop().time()
            if now - last_ping > ping_period:
                last_ping = now
                ping = await _quick_ping(PING_TARGET)
                if ping is not None:
                    last_ping_v = ping
            snap["ping"] = {"target": PING_TARGET, "latency_ms": last_ping_v}
            await manager.broadcast("metrics", {"type": "metrics", **snap})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("metrics loop error")
        await asyncio.sleep(METRICS_INTERVAL)


async def _process_loop() -> None:
    """Push top-N processes every PROCESS_INTERVAL seconds."""
    while True:
        try:
            procs = metrics.processes_snapshot(top_n=10)
            await manager.broadcast("metrics", {"type": "processes", "processes": procs,
                                                "ts": datetime.now().isoformat()})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("process loop error")
        await asyncio.sleep(PROCESS_INTERVAL)


async def _uptime_loop() -> None:
    """Push uptime refresh every UPTIME_INTERVAL seconds."""
    while True:
        try:
            await manager.broadcast("metrics",
                                     {"type": "system", "system": metrics.system_snapshot()})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("uptime loop error")
        await asyncio.sleep(UPTIME_INTERVAL)


async def _history_loop() -> None:
    """Persist one metrics sample every HISTORY_SAMPLE_INTERVAL seconds."""
    while True:
        try:
            sample = await asyncio.to_thread(history.record_sample)
            fired = await asyncio.to_thread(evaluate_alerts, sample)
            for a in fired:
                await manager.broadcast("metrics", {"type": "alert", **a})
                await send_toast(a["title"], a["message"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("history loop error")
        await asyncio.sleep(config.HISTORY_SAMPLE_INTERVAL)


async def _quick_ping(host: str, timeout: float = 1.0) -> float | None:
    """Quick latency probe using asyncio TCP connect latency (no raw ICMP)."""
    import socket
    loop = asyncio.get_event_loop()
    start = loop.time()
    try:
        addr = socket.gethostbyname(host)
    except socket.gaierror:
        return None
    fut = asyncio.open_connection(addr, 80)
    try:
        _reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return round((loop.time() - start) * 1000, 1)
    except (TimeoutError, ConnectionRefusedError, OSError):
        # A refused/failed TCP connect still yields a latency estimate.
        return round((loop.time() - start) * 1000, 1)


# ---- REST ---- #

@app.get("/api/system")
async def get_system() -> dict[str, Any]:
    return {"system": metrics.system_snapshot(), "cpu": metrics.cpu_snapshot(),
            "ram": metrics.ram_snapshot(), "gpu": metrics.gpu_snapshot()}


@app.get("/api/history")
async def api_history(rng: str = Query(default="1h", alias="range")) -> dict[str, Any]:
    """Bucketed metrics history. range: 1h | 6h | 24h."""
    return await asyncio.to_thread(history.query_range, rng)


@app.post("/api/speedtest")
async def api_speedtest() -> dict[str, Any]:
    """Trigger a speed test; result returned synchronously and broadcast to /ws/metrics."""
    result = await speedtest_worker.run_speedtest_async()
    await manager.broadcast("metrics", {"type": "speedtest_result", **result})
    return result


@app.get("/api/security/suspicious")
async def get_suspicious() -> dict[str, Any]:
    return {"countries": suspicious_countries_state,
            "default": config.DEFAULT_SUSPICIOUS_COUNTRIES}


@app.put("/api/security/suspicious")
async def put_suspicious(payload: dict[str, Any]) -> dict[str, Any]:
    global suspicious_countries_state
    countries = payload.get("countries")
    if not isinstance(countries, list):
        return {"ok": False, "reason": "countries must be a list"}
    cleaned = [str(c).upper().strip()[:2] for c in countries if isinstance(c, str) and c.strip()]
    suspicious_countries_state = cleaned
    save_suspicious()
    if sec_mon is not None:
        sec_mon.suspicious = cleaned
    return {"ok": True, "countries": cleaned}


@app.post("/api/security/audit")
async def api_audit() -> dict[str, Any]:
    """Run an audit synchronously and return the full report."""
    report = await audit_mod.run_audit(suspicious_override=list(suspicious_countries_state))
    return report


@app.post("/api/security/kill")
async def api_kill(payload: dict[str, Any]) -> dict[str, Any]:
    pid = payload.get("pid")
    force = bool(payload.get("force", False))
    if not isinstance(pid, int):
        return {"ok": False, "reason": "invalid_pid"}
    return await actions.kill_process(pid, force=force)


@app.post("/api/security/block")
async def api_block(payload: dict[str, Any]) -> dict[str, Any]:
    ip = (payload.get("ip") or "").strip()
    if not ip:
        return {"ok": False, "reason": "invalid_ip"}
    return await actions.block_ip(ip)


@app.post("/api/security/unblock")
async def api_unblock(payload: dict[str, Any]) -> dict[str, Any]:
    rule = payload.get("rule_name")
    if not rule:
        return {"ok": False, "reason": "missing_rule_name"}
    return await actions.unblock_ip(rule)


@app.get("/api/security/blocked")
async def api_blocked() -> dict[str, Any]:
    return await actions.list_block_rules()


@app.post("/api/security/export")
async def api_export(payload: dict[str, Any]) -> Response:
    fmt = (payload.get("fmt") or "json").lower()
    report_payload = payload.get("report")
    if not isinstance(report_payload, dict):
        return Response(json.dumps({"ok": False, "reason": "missing report"}),
                        status_code=400, media_type="application/json")
    from exporters import save
    try:
        path = save(report_payload, fmt)
    except ValueError as exc:
        return Response(json.dumps({"ok": False, "reason": str(exc)}),
                        status_code=400, media_type="application/json")
    data = Path(path).read_bytes()
    media_types = {
        "pdf": "application/pdf",
        "html": "text/html",
        "json": "application/json",
    }
    return Response(data, media_type=media_types.get(fmt, "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="{Path(path).name}"'})


# ---- WebSockets ---- #

@app.websocket("/ws/metrics")
async def ws_metrics(ws: WebSocket) -> None:
    await ws.accept()
    manager.metrics.add(ws)
    try:
        # Greet the new client with the initial snapshot.
        await ws.send_json({"type": "metrics",
                            **metrics.full_snapshot(),
                            "ping": {"latency_ms": 0, "target": PING_TARGET}})
        await ws.send_json({"type": "system", "system": metrics.system_snapshot()})
        await ws.send_json({"type": "processes",
                            "processes": metrics.processes_snapshot(),
                            "ts": datetime.now().isoformat()})
        # Keep the socket open until disconnect.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.metrics.discard(ws)


@app.websocket("/ws/security")
async def ws_security(ws: WebSocket) -> None:
    await ws.accept()
    manager.security.add(ws)
    try:
        await ws.send_json({"type": "hello", "ts": datetime.now().isoformat(),
                            "suspicious_countries": suspicious_countries_state})
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.security.discard(ws)


# ---- Serving frontend (production) ---- #

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")


    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> Response:
        # API routes already matched above; SPA fallback.
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse("Frontend not built. Run `cd frontend; npm run build`.", status_code=404)
else:
    logger.warning("Frontend dist not found at %s. The dashboard UI will not be available. "
                   "Build the frontend with `cd frontend; npm install; npm run build`.",
                   FRONTEND_DIST)


# ---- Entry point ---- #
def main() -> None:
    uvicorn.run("main:app", host=HOST, port=config.PORT, reload=False, log_level="info")


if __name__ == "__main__":
    main()
