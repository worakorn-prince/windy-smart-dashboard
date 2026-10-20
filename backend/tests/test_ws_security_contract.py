"""Contract tests for the security WS channel, admin-token actions and export errors.

Covers HARDEN-101:
  (a) WS contract — events fed into the security monitor must reach the WS
      channel as the canonical envelope {"type": "security_event", "event": {...}}.
  (b) Admin token — the backend must enforce X-Admin-Token on every action
      endpoint, and our frontend client (stores/security.ts) must attach it.
  (c) Export endpoint — malformed reports must yield 400, never 500.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
import exporters
import main
from security import actions
from security import monitor as sec_monitor

FRONTEND_STORE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "stores" / "security.ts"

ACTION_ENDPOINTS = ["/api/security/kill", "/api/security/block", "/api/security/unblock"]


def _fake_event(**overrides) -> sec_monitor.Event:
    fields = dict(
        type="port_opened",
        timestamp="2026-01-01T00:00:00",
        title="New listening port 8080/evil.exe",
        detail={"ip": "0.0.0.0", "port": 8080, "pid": 4242, "name": "evil.exe"},
    )
    fields.update(overrides)
    return sec_monitor.Event(**fields)


def _valid_report() -> dict:
    return {
        "generated_at": "2026-01-01T00:00:00",
        "duration_ms": 12,
        "riskscore": 0,
        "risk_label": "Low",
        "findings": [],
        "data": {"suspicious_countries": []},
    }


@pytest.fixture()
def client():
    return TestClient(main.app)


# ---- (a) WS contract ---- #

def test_security_event_payload_is_canonical():
    payload = main.security_event_payload(_fake_event())
    assert payload["type"] == "security_event"
    evt = payload["event"]
    assert evt["type"] == "port_opened"
    assert evt["title"] == "New listening port 8080/evil.exe"
    assert evt["detail"]["port"] == 8080
    assert evt["timestamp"] == "2026-01-01T00:00:00"


def test_monitor_routes_events_through_canonical_payload(monkeypatch):
    captured: list[tuple[str, dict]] = []

    async def fake_broadcast(channel, message):
        captured.append((channel, message))

    monkeypatch.setattr(main.manager, "broadcast", fake_broadcast)
    mon = sec_monitor.SecurityMonitor(on_event=main.broadcast_security_event)
    asyncio.run(mon._emit(_fake_event(type="failed_login", title="Failed login as 'x' from 1.2.3.4")))

    assert len(captured) == 1, "monitor did not deliver the event to on_event"
    channel, message = captured[0]
    assert channel == "security"
    assert message["type"] == "security_event"
    assert message["event"]["type"] == "failed_login"
    assert message["event"]["title"] == "Failed login as 'x' from 1.2.3.4"


def test_ws_security_endpoint_delivers_canonical_event(client):
    with client.websocket_connect("/ws/security") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"

        evt = _fake_event(type="suspicious_outbound", title="Outbound to suspicious country RU")
        portal = getattr(ws, "portal", None)
        assert portal is not None, "TestClient session portal unavailable"
        # Broadcast inside the app's own event loop — never asyncio.run across loops.
        portal.call(main.broadcast_security_event, evt)

        message = ws.receive_json()
        assert message["type"] == "security_event"
        assert message["event"]["type"] == "suspicious_outbound"
        assert message["event"]["title"] == "Outbound to suspicious country RU"


# ---- (b) admin token ---- #

def test_action_endpoints_reject_missing_token(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    for endpoint in ACTION_ENDPOINTS:
        r = client.post(endpoint, json={})
        assert r.status_code == 401, f"{endpoint} did not enforce the admin token"


def test_action_endpoints_accept_correct_token(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    async def fake_kill(pid, force=False):
        return {"ok": True, "pid": pid}

    async def fake_block(ip):
        return {"ok": True, "ip": ip}

    async def fake_unblock(rule):
        return {"ok": True, "rule": rule}

    monkeypatch.setattr(actions, "kill_process", fake_kill)
    monkeypatch.setattr(actions, "block_ip", fake_block)
    monkeypatch.setattr(actions, "unblock_ip", fake_unblock)

    headers = {"X-Admin-Token": "secret"}
    r = client.post("/api/security/kill", json={"pid": 1}, headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.post("/api/security/block", json={"ip": "1.2.3.4"}, headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.post("/api/security/unblock", json={"rule_name": "r1"}, headers=headers)
    assert r.status_code == 200 and r.json()["ok"] is True


def _store_function_body(src: str, name: str) -> str:
    m = re.search(rf"async function {name}\([^)]*\) \{{(.*?)\n  \}}", src, re.DOTALL)
    assert m, f"function {name} not found in stores/security.ts"
    return m.group(1)


def test_frontend_store_attaches_admin_token_on_all_actions():
    src = FRONTEND_STORE.read_text(encoding="utf-8")
    assert "X-Admin-Token" in src, "store must send the X-Admin-Token header"
    for name in ("killProcess", "blockIp", "unblockRule"):
        body = _store_function_body(src, name)
        assert "authHeaders()" in body, f"{name} must attach admin-token headers"


def test_frontend_store_keeps_admin_token_in_session_storage():
    src = FRONTEND_STORE.read_text(encoding="utf-8")
    assert "sessionStorage" in src, "admin token must be kept in sessionStorage"
    assert "localStorage" not in src, "admin token must never touch localStorage"


# ---- (c) export error handling ---- #

def test_export_unknown_format_returns_400(client):
    r = client.post("/api/security/export",
                    json={"fmt": "bogus", "report": _valid_report()})
    assert r.status_code == 400
    assert r.json()["ok"] is False
    assert "bogus" in r.json()["reason"]


def test_export_fmt_wrong_type_returns_400(client):
    r = client.post("/api/security/export",
                    json={"fmt": ["pdf"], "report": _valid_report()})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_export_missing_finding_keys_returns_400(client):
    report = _valid_report()
    report["findings"] = [{"category": "ports"}]
    r = client.post("/api/security/export", json={"fmt": "html", "report": report})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_export_wrong_finding_type_returns_400(client):
    report = _valid_report()
    report["findings"] = "not-a-list"
    r = client.post("/api/security/export", json={"fmt": "html", "report": report})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_export_nonstring_generated_at_returns_400(client):
    report = _valid_report()
    report["generated_at"] = 123
    r = client.post("/api/security/export", json={"fmt": "json", "report": report})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_export_valid_json_returns_200(client, tmp_path, monkeypatch):
    monkeypatch.setattr(exporters, "AUDIT_DIR", tmp_path, raising=False)
    r = client.post("/api/security/export",
                    json={"fmt": "json", "report": _valid_report()})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    assert "attachment" in r.headers.get("content-disposition", "")


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
