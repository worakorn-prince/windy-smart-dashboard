"""Tests for persisted security events (FEAT-202).

Covers:
  - persistence.record_event / list_events roundtrip on the shared history DB
  - limit handling and detail JSON round-trip
  - a broken/corrupt database must never raise (best-effort persistence)
  - GET /api/security/events admin gating (401 without token, 200 with token)
  - the WS path must survive a failing persistence layer
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

import config
import main
from security import monitor as sec_monitor
from security import persistence


@pytest.fixture()
def event_db(tmp_path, monkeypatch):
    """Point the shared history DB at a temp file and reset the cached conn."""
    db = tmp_path / "history.db"
    monkeypatch.setattr(config, "HISTORY_DB", db, raising=False)
    persistence.close()
    yield db
    persistence.close()


@pytest.fixture()
def client():
    return TestClient(main.app)


def _fake_event(**overrides) -> sec_monitor.Event:
    fields = dict(
        type="port_opened",
        timestamp="2026-01-01T00:00:00",
        title="New listening port 8080/evil.exe",
        detail={"ip": "0.0.0.0", "port": 8080, "pid": 4242, "name": "evil.exe"},
    )
    fields.update(overrides)
    return sec_monitor.Event(**fields)


# ---- persistence roundtrip ---- #

def test_record_and_list_roundtrip(event_db):
    assert persistence.record_event("port_opened", "0.0.0.0",
                                    {"port": 8080}, ts="2026-01-01T00:00:01") is True
    assert persistence.record_event("failed_login", "1.2.3.4",
                                    {"user": "admin"}, ts="2026-01-01T00:00:02") is True
    events = persistence.list_events()
    assert len(events) == 2
    newest, oldest = events
    assert newest["kind"] == "failed_login"
    assert newest["source_ip"] == "1.2.3.4"
    assert newest["ts"] == "2026-01-01T00:00:02"
    assert newest["detail"] == {"user": "admin"}
    assert oldest["kind"] == "port_opened"
    assert oldest["detail"] == {"port": 8080}


def test_list_limit_returns_newest_first(event_db):
    for i in range(5):
        persistence.record_event("outbound_connection", f"10.0.0.{i}",
                                 {"i": i}, ts=f"2026-01-01T00:00:0{i}")
    events = persistence.list_events(limit=3)
    assert len(events) == 3
    assert [e["detail"]["i"] for e in events] == [4, 3, 2]
    assert len(persistence.list_events(limit=100)) == 5


def test_detail_json_roundtrip(event_db):
    detail = {"ip": "5.6.7.8", "port": 443, "meta": {"exe": "C:\\path\\evil.exe", "flags": [1, 2]}}
    assert persistence.record_event("suspicious_outbound", "5.6.7.8", detail) is True
    events = persistence.list_events()
    assert events[0]["detail"] == detail
    assert isinstance(events[0]["detail"], dict)


def test_record_event_tolerates_unserializable_detail(event_db):
    assert persistence.record_event("defender_status", "", {"weird": {1, 2}}) is True
    events = persistence.list_events()
    assert events[0]["kind"] == "defender_status"
    assert "weird" in events[0]["detail"]


# ---- broken DB must never raise ---- #

def test_record_event_survives_unwritable_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path, raising=False)
    persistence.close()
    assert persistence.record_event("port_opened", "1.2.3.4", {"port": 1}) is False
    assert persistence.list_events() == []
    persistence.close()


def test_record_event_survives_corrupt_db(tmp_path, monkeypatch):
    db = tmp_path / "history.db"
    db.write_bytes(b"this is not a sqlite database" * 64)
    monkeypatch.setattr(config, "HISTORY_DB", db, raising=False)
    persistence.close()
    assert persistence.record_event("port_opened", "1.2.3.4", {"port": 1}) is False
    assert persistence.list_events() == []
    persistence.close()


# ---- API endpoint ---- #

def test_events_endpoint_requires_token(client, monkeypatch, event_db):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    r = client.get("/api/security/events")
    assert r.status_code == 401


def test_events_endpoint_returns_recorded_events(client, monkeypatch, event_db):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    persistence.record_event("port_opened", "0.0.0.0", {"port": 8080}, ts="2026-01-01T00:00:01")
    r = client.get("/api/security/events", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["events"][0]["kind"] == "port_opened"
    assert data["events"][0]["source_ip"] == "0.0.0.0"
    assert data["events"][0]["detail"] == {"port": 8080}


def test_events_endpoint_default_limit_50(client, monkeypatch, event_db):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    for i in range(60):
        persistence.record_event("outbound_connection", f"10.0.0.{i}",
                                 {"i": i}, ts=f"2026-01-01T00:00:{i:02d}")
    r = client.get("/api/security/events", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200
    assert r.json()["count"] == 50


def test_events_endpoint_caps_limit_at_200(client, monkeypatch, event_db):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    for i in range(5):
        persistence.record_event("outbound_connection", f"10.0.0.{i}",
                                 {"i": i}, ts=f"2026-01-01T00:00:{i:02d}")
    r = client.get("/api/security/events?limit=500", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 422
    r = client.get("/api/security/events?limit=200", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200
    assert r.json()["count"] == 5


# ---- WS path ---- #

def test_ws_path_persists_events(monkeypatch, event_db):
    captured: list[tuple[str, dict]] = []

    async def fake_broadcast(channel, message):
        captured.append((channel, message))

    monkeypatch.setattr(main.manager, "broadcast", fake_broadcast)
    evt = _fake_event(type="failed_login", title="Failed login as 'x' from 1.2.3.4",
                      detail={"ip": "1.2.3.4", "user": "x"})
    asyncio.run(main.broadcast_security_event(evt))

    assert captured and captured[0][0] == "security"
    events = persistence.list_events()
    assert len(events) == 1
    assert events[0]["kind"] == "failed_login"
    assert events[0]["source_ip"] == "1.2.3.4"
    assert events[0]["detail"]["user"] == "x"


def test_ws_path_survives_persistence_failure(monkeypatch, event_db):
    captured: list[tuple[str, dict]] = []

    async def fake_broadcast(channel, message):
        captured.append((channel, message))

    monkeypatch.setattr(main.manager, "broadcast", fake_broadcast)

    def boom(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(main.sec_persistence, "record_event", boom)
    asyncio.run(main.broadcast_security_event(_fake_event()))

    assert captured[0][1]["type"] == "security_event"
    assert captured[0][1]["event"]["type"] == "port_opened"


def test_ws_security_endpoint_persists_event(client, event_db):
    with client.websocket_connect("/ws/security") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"

        evt = _fake_event(type="suspicious_outbound", title="Outbound to suspicious country RU",
                          detail={"ip": "5.6.7.8", "country_code": "RU"})
        portal = getattr(ws, "portal", None)
        assert portal is not None, "TestClient session portal unavailable"
        portal.call(main.broadcast_security_event, evt)

        message = ws.receive_json()
        assert message["type"] == "security_event"
        assert message["event"]["type"] == "suspicious_outbound"

    events = persistence.list_events()
    assert any(e["kind"] == "suspicious_outbound" and e["source_ip"] == "5.6.7.8"
               for e in events)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
