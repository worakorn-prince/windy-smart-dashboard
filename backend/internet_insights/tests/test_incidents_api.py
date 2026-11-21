"""API tests for Internet Insights incident endpoints (INET-M5, mocked manager)."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from internet_insights.router import router
from internet_insights.services.incident_manager import InvalidIncidentTransitionError

ROUTER_MODULE = importlib.import_module("internet_insights.router")

INCIDENT_KEYS = {
    "id", "started_at", "ended_at", "category", "severity", "status",
    "title", "summary", "confidence", "analyzer_version",
}

METADATA_KEYS = {"generated_at", "data_window", "source", "status", "errors", "coverage"}


def _incident(**overrides) -> SimpleNamespace:
    base = {
        "id": "inc-1",
        "started_at": 1_000.0,
        "ended_at": None,
        "category": "latency",
        "severity": "warning",
        "status": "active",
        "title": "Latency incident",
        "summary": "Median latency doubled",
        "confidence": 0.75,
        "analyzer_version": "1.0.0",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _evidence(**overrides) -> SimpleNamespace:
    base = {
        "id": 1,
        "incident_id": "inc-1",
        "evidence_type": "quality_sample",
        "observed_at": 1_001.0,
        "payload_json": '{"rtt_ms": 90.0}',
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def fake_manager(monkeypatch) -> MagicMock:
    manager = MagicMock(name="incident_manager")
    monkeypatch.setattr(ROUTER_MODULE, "_get_incident_manager", lambda: manager)
    return manager


@pytest.fixture
def fake_hub(monkeypatch) -> MagicMock:
    hub = MagicMock(name="incident_ws_hub")
    monkeypatch.setattr(ROUTER_MODULE, "_get_incident_ws_hub", lambda: hub)
    return hub


@pytest.fixture
def client(fake_manager) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestListIncidents:
    def test_list_returns_200_with_metadata_and_incidents(self, client, fake_manager):
        fake_manager.list_incidents.return_value = [_incident(), _incident(id="inc-2", status="resolved", ended_at=2_000.0)]
        resp = client.get("/api/internet/incidents")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) >= METADATA_KEYS
        assert body["source"] == "service"
        assert body["status"] == "ok"
        assert body["errors"] == []
        assert body["coverage"] == 1.0
        assert "generated_at" in body and "data_window" in body
        assert body["count"] == 2
        assert len(body["incidents"]) == 2
        assert set(body["incidents"][0]) >= INCIDENT_KEYS
        assert body["incidents"][0]["id"] == "inc-1"

    def test_list_empty_returns_empty_list(self, client, fake_manager):
        fake_manager.list_incidents.return_value = []
        resp = client.get("/api/internet/incidents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["incidents"] == []
        assert body["count"] == 0

    def test_filters_passed_to_manager(self, client, fake_manager):
        fake_manager.list_incidents.return_value = []
        resp = client.get(
            "/api/internet/incidents",
            params={"status": "active", "category": "latency", "since": 900.0, "limit": 10},
        )
        assert resp.status_code == 200
        kwargs = fake_manager.list_incidents.call_args.kwargs
        assert kwargs["status"] == "active"
        assert kwargs["category"] == "latency"
        assert kwargs["since"] == 900.0
        assert kwargs["limit"] == 10

    def test_limit_zero_returns_422(self, client, fake_manager):
        fake_manager.list_incidents.return_value = []
        resp = client.get("/api/internet/incidents", params={"limit": 0})
        assert resp.status_code == 422

    def test_limit_over_200_returns_422(self, client, fake_manager):
        fake_manager.list_incidents.return_value = []
        resp = client.get("/api/internet/incidents", params={"limit": 201})
        assert resp.status_code == 422


class TestGetIncident:
    def test_get_returns_incident_with_evidence(self, client, fake_manager):
        fake_manager.get.return_value = _incident()
        fake_manager.evidence_for.return_value = [
            _evidence(),
            _evidence(id=2, evidence_type="rule_evaluation", observed_at=1_002.0, payload_json='{"rule_id": "x"}'),
        ]
        resp = client.get("/api/internet/incidents/inc-1")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) >= INCIDENT_KEYS
        assert body["id"] == "inc-1"
        assert len(body["evidence"]) == 2
        ev = body["evidence"][0]
        assert ev["evidence_type"] == "quality_sample"
        assert ev["observed_at"] == 1_001.0
        assert ev["payload"] == {"rtt_ms": 90.0}

    def test_get_404_when_unknown(self, client, fake_manager):
        fake_manager.get.return_value = None
        resp = client.get("/api/internet/incidents/inc-missing")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Incident not found: inc-missing"

    def test_get_malformed_payload_json_falls_back_to_raw(self, client, fake_manager):
        fake_manager.get.return_value = _incident()
        fake_manager.evidence_for.return_value = [_evidence(payload_json="not-json{")]
        resp = client.get("/api/internet/incidents/inc-1")
        assert resp.status_code == 200
        assert resp.json()["evidence"][0]["payload"] == {"raw": "not-json{"}


class TestResolveIncident:
    def test_resolve_returns_200_and_emits_ws(self, client, fake_manager, fake_hub):
        resolved = _incident(status="resolved", ended_at=2_000.0)
        fake_manager.get.return_value = _incident()
        fake_manager.resolve_incident.return_value = resolved
        resp = client.post("/api/internet/incidents/inc-1/resolve")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "resolved"
        assert body["ended_at"] == 2_000.0
        fake_manager.resolve_incident.assert_called_once_with("inc-1")
        fake_hub.emit.assert_called_once()
        args, _kwargs = fake_hub.emit.call_args
        assert args[0] == "incident_updated"

    def test_resolve_invalid_transition_returns_409(self, client, fake_manager, fake_hub):
        fake_manager.get.return_value = _incident(status="resolved")
        fake_manager.resolve_incident.side_effect = InvalidIncidentTransitionError(
            "cannot resolve an incident that is already resolved"
        )
        resp = client.post("/api/internet/incidents/inc-1/resolve")
        assert resp.status_code == 409
        assert "cannot resolve" in resp.json()["detail"]

    def test_resolve_unknown_returns_404(self, client, fake_manager, fake_hub):
        fake_manager.get.return_value = None
        resp = client.post("/api/internet/incidents/inc-missing/resolve")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Incident not found: inc-missing"
        fake_manager.resolve_incident.assert_not_called()
