"""API tests for Internet Insights developer diagnostic lab endpoints (mocked backends)."""

from __future__ import annotations

import importlib
import socket
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from internet_insights.router import router
from internet_insights.services.session_manager import SessionLimitError

ROUTER_MODULE = importlib.import_module("internet_insights.router")

SESSION_DICT = {
    "id": "sess-1",
    "started_at": 1000.0,
    "completed_at": None,
    "status": "running",
    "target": None,
    "diagnostic_type": "full_session",
    "config": {"profile": "quick"},
    "summary": None,
    "error": None,
}


@pytest.fixture
def fake_manager(monkeypatch) -> MagicMock:
    manager = MagicMock(name="session_manager")
    monkeypatch.setattr(ROUTER_MODULE, "_get_session_manager", lambda: manager)
    return manager


@pytest.fixture
def client(fake_manager) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestSessionEndpoints:
    def test_start_session_returns_202(self, client, fake_manager):
        fake_manager.start_session = AsyncMock(return_value={
            "id": "sess-1",
            "started_at": 1000.0,
            "status": "running",
            "profile": "quick",
            "config": {"profile": "quick", "duration_sec": 0.5, "include_speedtest": False, "custom_targets": []},
        })
        resp = client.post("/api/internet/sessions", json={"profile": "quick"})
        assert resp.status_code == 202
        body = resp.json()
        assert body["id"] == "sess-1"
        assert body["profile"] == "quick"
        assert "config" in body

    def test_start_session_limit_returns_409(self, client, fake_manager):
        fake_manager.start_session = AsyncMock(side_effect=SessionLimitError("Maximum concurrent diagnostic sessions reached (2/2)"))
        resp = client.post("/api/internet/sessions", json={})
        assert resp.status_code == 409
        assert "Maximum concurrent" in resp.json()["detail"]

    def test_get_session_returns_dict(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT, status="completed")
        resp = client.get("/api/internet/sessions/sess-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "sess-1"
        assert body["diagnostic_type"] == "full_session"
        assert body["source"] == "service"

    def test_get_session_unknown_returns_404(self, client, fake_manager):
        fake_manager.get_session.return_value = None
        assert client.get("/api/internet/sessions/missing").status_code == 404

    def test_get_results_returns_list(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT)
        fake_manager.get_results.return_value = [
            {"id": 1, "ts": 1001.0, "sequence": 1, "result_type": "probe", "payload": {"step": "adapter_snapshot", "status": "success"}},
        ]
        resp = client.get("/api/internet/sessions/sess-1/results")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["results"], list)
        assert len(body["results"]) == 1

    def test_get_results_unknown_returns_404(self, client, fake_manager):
        fake_manager.get_session.return_value = None
        assert client.get("/api/internet/sessions/missing/results").status_code == 404

    def test_cancel_running_returns_200(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT)
        fake_manager.cancel = AsyncMock(return_value=True)
        resp = client.post("/api/internet/sessions/sess-1/cancel")
        assert resp.status_code == 200
        assert resp.json() == {"id": "sess-1", "status": "cancelling"}

    def test_cancel_not_running_returns_409(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT, status="completed")
        resp = client.post("/api/internet/sessions/sess-1/cancel")
        assert resp.status_code == 409

    def test_cancel_no_longer_running_returns_409(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT)
        fake_manager.cancel = AsyncMock(return_value=False)
        assert client.post("/api/internet/sessions/sess-1/cancel").status_code == 409

    def test_cancel_unknown_returns_404(self, client, fake_manager):
        fake_manager.get_session.return_value = None
        assert client.post("/api/internet/sessions/missing/cancel").status_code == 404


class TestSessionExportEndpoint:
    def test_export_json(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT)
        fake_manager.export_session.return_value = ("diagnostic-session-sess-1.json", "application/json", '{"session": {}}')
        resp = client.get("/api/internet/sessions/sess-1/export", params={"format": "json"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert "attachment" in resp.headers["content-disposition"]
        assert "diagnostic-session-sess-1.json" in resp.headers["content-disposition"]

    def test_export_csv(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT)
        fake_manager.export_session.return_value = ("diagnostic-session-sess-1.csv", "text/csv", "sequence,ts,result_type,payload\r\n")
        resp = client.get("/api/internet/sessions/sess-1/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "diagnostic-session-sess-1.csv" in resp.headers["content-disposition"]

    def test_export_md(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT)
        fake_manager.export_session.return_value = ("diagnostic-session-sess-1.md", "text/markdown", "# Diagnostic Session Report")
        resp = client.get("/api/internet/sessions/sess-1/export", params={"format": "md"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")
        assert "diagnostic-session-sess-1.md" in resp.headers["content-disposition"]

    def test_export_invalid_format_returns_422(self, client, fake_manager):
        fake_manager.get_session.return_value = dict(SESSION_DICT)
        resp = client.get("/api/internet/sessions/sess-1/export", params={"format": "xml"})
        assert resp.status_code in (422, 400)

    def test_export_unknown_session_returns_404(self, client, fake_manager):
        fake_manager.get_session.return_value = None
        assert client.get("/api/internet/sessions/missing/export", params={"format": "json"}).status_code == 404


class TestDiagnosticEndpoints:
    def test_tcp_invalid_target_returns_422(self, client):
        resp = client.post("/api/internet/diagnostics/tcp", json={"target": "https://example.com"})
        assert resp.status_code == 422

    def test_tcp_valid_target_with_mock_returns_200(self, client, monkeypatch):
        tcp_mock = AsyncMock(return_value={"target": "example.com", "port": 443, "duration_ms": 1.5, "status": "success", "error_code": None})
        monkeypatch.setattr("internet_insights.diagnostics.tcp.tcp_connect", tcp_mock)
        resp = client.post("/api/internet/diagnostics/tcp", json={"target": "example.com", "port": 443})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert tcp_mock.await_count == 1

    def test_http_private_url_returns_422(self, client, monkeypatch):
        def _resolver(host, port=None, family=0, type=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", _resolver)
        resp = client.post("/api/internet/diagnostics/http", json={"url": "http://localhost:8080/admin"})
        assert resp.status_code == 422

    def test_mtu_with_mock_returns_200(self, client, monkeypatch):
        mtu_mock = AsyncMock(return_value={"target": "example.com", "test_size": 1500, "path_mtu": 1400, "status": "success", "probes": []})
        monkeypatch.setattr("internet_insights.diagnostics.mtu.mtu_discovery", mtu_mock)
        resp = client.post("/api/internet/diagnostics/mtu", json={"target": "example.com"})
        assert resp.status_code == 200
        assert resp.json()["path_mtu"] == 1400

    def test_ping_with_mock_adapter_returns_200(self, client, monkeypatch):
        adapter = MagicMock()
        adapter.ping = AsyncMock(return_value=12.5)
        monkeypatch.setattr(ROUTER_MODULE, "_get_ping_adapter", lambda: adapter)
        resp = client.post("/api/internet/diagnostics/ping", json={"target": "1.1.1.1", "count": 3, "interval_ms": 0})
        assert resp.status_code == 200
        body = resp.json()
        assert body["received"] == 3
        assert body["sent"] == 3
        assert body["loss_pct"] == 0.0
        assert body["rtt"]["min"] == 12.5

    def test_dns_with_mock_resolver_returns_200(self, client, monkeypatch):
        def _resolver(host, port=None, family=0, type=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(socket, "getaddrinfo", _resolver)
        resp = client.post("/api/internet/diagnostics/dns", json={"hostname": "example.com", "record_type": "A"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["hostname"] == "example.com"
        assert body["answer_count"] == 1
        assert body["duration_ms"] is not None
