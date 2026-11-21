"""Wiring tests for backend/main.py internet-insights integration (INET-M6-A).

1. Module isolation: re-executing main.py with a broken internet_insights
   router must still produce a working app (guard catches, siblings intact).
2. WS regression: /ws/metrics and /ws/security greet exactly as before the
   incident-loop integration (greeting contract must not regress).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("DASH_TEST_MODE", "1")

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402  (requires sys.path setup above)


class _FakeCache:
    def __init__(self, value):
        self.value = value

    async def get(self, refresh_if_stale: bool = False):
        return self.value, True


class TestModuleIsolation:
    def test_main_imports_without_internet_router(self, caplog, monkeypatch):
        import fastapi

        existing_paths = set(main.app.openapi()["paths"].keys())
        assert any("/api/internet" in p for p in existing_paths)

        broken_router = main.internet_insights_router
        original = fastapi.FastAPI.include_router

        def failing_include(self, router, *args, **kwargs):
            if router is broken_router:
                raise RuntimeError("simulated internet_insights failure")
            return original(self, router, *args, **kwargs)

        monkeypatch.setattr(fastapi.FastAPI, "include_router", failing_include)

        spec = importlib.util.spec_from_file_location("main_no_internet", main.__file__)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        with caplog.at_level(logging.ERROR):
            spec.loader.exec_module(mod)

        paths = set(mod.app.openapi()["paths"].keys())
        assert not any("/api/internet" in p for p in paths)
        assert any(p == "/api/system" for p in paths)

        assert any(
            "internet_insights router not registered" in rec.getMessage()
            for rec in caplog.records
        )

    def test_incident_loop_is_wired_into_lifespan(self):
        import inspect

        assert hasattr(main, "_incident_loop")
        lifespan_src = inspect.getsource(main.lifespan)
        assert "incident_task" in lifespan_src


class TestWsRegression:
    def test_ws_metrics_greeting_contract(self, monkeypatch):
        monkeypatch.setattr(
            main, "_processes_snapshot_cache", _FakeCache([{"pid": 100, "name": "app.exe"}])
        )
        monkeypatch.setattr(main, "_system_snapshot_cache", _FakeCache({"hostname": "test-host"}))
        monkeypatch.setattr(main, "_full_snapshot_cache", _FakeCache({"cpu_pct": 7.5}))
        monkeypatch.setattr(main.metrics, "cpu_count", lambda: 8)

        client = TestClient(main.app)
        with client.websocket_connect("/ws/metrics") as ws:
            processes = ws.receive_json()
            system = ws.receive_json()
            metrics_msg = ws.receive_json()

        assert processes["type"] == "processes"
        assert processes["cpu_count"] == 8
        assert processes["processes"][0]["pid"] == 100
        assert system["type"] == "system"
        assert system["system"]["hostname"] == "test-host"
        assert metrics_msg["type"] == "metrics"
        assert metrics_msg["cpu_pct"] == 7.5
        assert "ping" in metrics_msg

    def test_ws_security_hello_contract(self):
        client = TestClient(main.app)
        with client.websocket_connect("/ws/security") as ws:
            hello = ws.receive_json()

        assert hello["type"] == "hello"
        assert "ts" in hello
        assert isinstance(hello["suspicious_countries"], list)

    def test_ws_internet_greeting_contract(self):
        client = TestClient(main.app)
        with client.websocket_connect("/ws/internet") as ws:
            greeting = ws.receive_json()

        assert greeting["type"] == "internet_status"
        assert greeting["state"] == "connected"
        assert "ts" in greeting
