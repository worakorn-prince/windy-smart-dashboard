"""Tests for notification channels: generic webhook + LINE Notify."""
import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

import alerts
import config
import main

ADMIN_TOKEN = "secret"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}
NOTIFY_HEADERS = {**ADMIN_HEADERS, "X-Requested-With": "windy-dashboard"}


@pytest.fixture(autouse=True)
def _isolated_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(alerts, "RULES_PATH", tmp_path / "alert_rules.json")
    monkeypatch.setattr(alerts, "_rules", None)
    monkeypatch.setattr(config, "ADMIN_TOKEN", ADMIN_TOKEN)

    async def _noop_toast(title: str, message: str) -> None:
        return None

    monkeypatch.setattr(alerts, "send_toast", _noop_toast)
    alerts.reset_state()
    yield
    alerts.reset_state()


@pytest.fixture()
def client():
    return TestClient(main.app)


def _start_stub(redirect_to: str | None = None) -> tuple[ThreadingHTTPServer, list[dict]]:
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            received.append({
                "path": self.path,
                "headers": dict(self.headers),
                "body": body.decode("utf-8"),
            })
            if redirect_to:
                self.send_response(302)
                self.send_header("Location", redirect_to)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, received


def _stop(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.server_close()


@pytest.fixture()
def stub():
    server, received = _start_stub()
    yield server, received
    _stop(server)


def _stub_url(server: ThreadingHTTPServer, path: str = "/hook") -> str:
    return f"http://127.0.0.1:{server.server_address[1]}{path}"


def _channels(**overrides: object) -> dict:
    channels = {
        "toast": False,
        "sound": False,
        "webhook": {"enabled": False, "url": ""},
        "line": {"enabled": False, "token": "", "target": ""},
    }
    channels.update(overrides)
    return channels


def _payload(channels: dict | None = None) -> dict:
    return {
        "rules": [{"id": "cpu_temp", "metric": "cpu_temp", "op": ">=",
                   "threshold": 80, "enabled": True}],
        "channels": channels if channels is not None else _channels(),
    }


def _alert(**extra: object) -> dict:
    alert = {"id": "cpu_temp", "title": "CPU temperature high",
             "message": "CPU temperature high: 95°C (limit 80°C)",
             "value": 95.0, "threshold": 80.0, "ts": 1.0}
    alert.update(extra)
    return alert


# ---- schema ---- #

def test_default_channels_have_webhook_and_line_disabled():
    channels = alerts.get_channels()
    assert channels["toast"] is True
    assert channels["sound"] is False
    assert channels["webhook"] == {"enabled": False, "url": ""}
    assert channels["line"] == {"enabled": False, "token": "", "target": ""}


def test_legacy_channels_file_loads_and_gets_defaults():
    alerts.RULES_PATH.write_text(json.dumps({
        "rules": [{"id": "cpu_temp", "metric": "cpu_temp", "op": ">=",
                   "threshold": 80, "enabled": True}],
        "channels": {"toast": False, "sound": True},
    }), encoding="utf-8")
    rules = alerts.load_rules()
    assert rules["channels"]["toast"] is False
    assert rules["channels"]["sound"] is True
    assert rules["channels"]["webhook"] == {"enabled": False, "url": ""}
    assert rules["channels"]["line"] == {"enabled": False, "token": "", "target": ""}


def test_unknown_channel_keys_are_ignored():
    out = alerts._validate_rules_payload(_payload(_channels(
        slack={"enabled": True})))
    assert "slack" not in out["channels"]


# ---- webhook URL validation (SSRF) ---- #

def test_put_webhook_ftp_url_400(client):
    r = client.put("/api/alerts/rules", json=_payload(_channels(
        webhook={"enabled": True, "url": "ftp://x"})))
    assert r.status_code == 400


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/x",
    "http://169.254.1.5/x",
    "http://[fe80::1]/x",
    "http://metadata.google.internal/x",
    "http://metadata/x",
    "not-a-url",
])
def test_put_webhook_blocked_targets_400(client, url):
    r = client.put("/api/alerts/rules", json=_payload(_channels(
        webhook={"enabled": True, "url": url})))
    assert r.status_code == 400


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:9/hook",
    "http://localhost:8123/api/webhook/test",
    "http://192.168.1.10/hook",
])
def test_put_webhook_loopback_and_lan_allowed(client, url):
    r = client.put("/api/alerts/rules", json=_payload(_channels(
        webhook={"enabled": True, "url": url})))
    assert r.status_code == 200
    assert r.json()["channels"]["webhook"]["url"] == url


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(webhook={"enabled": "yes", "url": ""}),
    lambda c: c.update(webhook={"enabled": False, "url": 5}),
    lambda c: c.update(webhook={"enabled": False, "url": "http://" + "a" * 2048}),
    lambda c: c.update(line={"enabled": "yes"}),
    lambda c: c.update(line={"enabled": False, "token": "t" * 201}),
    lambda c: c.update(line={"enabled": False, "token": "", "target": 3}),
])
def test_validate_rejects_bad_channel_shapes(mutate):
    channels = _channels()
    mutate(channels)
    with pytest.raises(ValueError):
        alerts._validate_rules_payload(_payload(channels))


# ---- LINE token redaction ---- #

def test_get_rules_never_returns_line_token(client):
    r = client.put("/api/alerts/rules", json=_payload(_channels(
        line={"enabled": True, "token": "super-secret", "target": "grp"})))
    assert r.status_code == 200
    body = r.json()
    assert body["channels"]["line"]["token"] == ""
    assert body["channels"]["line"]["token_set"] is True
    assert body["channels"]["line"]["target"] == "grp"

    get_body = client.get("/api/alerts/rules").json()
    assert get_body["channels"]["line"]["token"] == ""
    assert get_body["channels"]["line"]["token_set"] is True
    assert alerts.get_rules()["channels"]["line"]["token"] == "super-secret"


def test_put_without_token_key_keeps_existing_token(client):
    client.put("/api/alerts/rules", json=_payload(_channels(
        line={"enabled": True, "token": "super-secret", "target": "grp"})))
    client.put("/api/alerts/rules", json=_payload(_channels(
        line={"enabled": True, "target": "grp2"})))
    line = alerts.get_rules()["channels"]["line"]
    assert line["token"] == "super-secret"
    assert line["target"] == "grp2"


def test_put_with_empty_token_clears_it(client):
    client.put("/api/alerts/rules", json=_payload(_channels(
        line={"enabled": True, "token": "super-secret"})))
    client.put("/api/alerts/rules", json=_payload(_channels(
        line={"enabled": True, "token": ""})))
    assert alerts.get_rules()["channels"]["line"]["token"] == ""


# ---- senders ---- #

def test_send_webhook_posts_contract_json(stub):
    server, received = stub
    assert asyncio.run(alerts.send_webhook(_stub_url(server), alerts._webhook_payload(
        _alert(severity="warning", regressions=["cpu_temp +10%"], source="compare"))))
    assert len(received) == 1
    assert received[0]["path"] == "/hook"
    assert received[0]["headers"]["Content-Type"] == "application/json"
    body = json.loads(received[0]["body"])
    assert body["id"] == "cpu_temp"
    assert body["title"] == "CPU temperature high"
    assert body["message"].startswith("CPU temperature high")
    assert body["value"] == 95.0
    assert body["threshold"] == 80.0
    assert body["ts"] == 1.0
    assert body["severity"] == "warning"
    assert body["regressions"] == ["cpu_temp +10%"]
    assert body["source"] == "compare"


def test_send_webhook_does_not_follow_redirects():
    target_server, target_received = _start_stub()
    redirect_server, redirect_received = _start_stub(redirect_to=_stub_url(target_server))
    try:
        assert asyncio.run(alerts.send_webhook(
            _stub_url(redirect_server), _alert())) is False
        assert len(redirect_received) == 1
        assert target_received == []
    finally:
        _stop(redirect_server)
        _stop(target_server)


def test_send_webhook_closed_port_returns_false():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert asyncio.run(alerts.send_webhook(f"http://127.0.0.1:{port}/hook", _alert())) is False


def test_send_webhook_blocks_metadata_target_without_request(stub):
    server, received = stub
    url = _stub_url(server).replace("127.0.0.1", "169.254.169.254")
    assert asyncio.run(alerts.send_webhook(url, _alert())) is False
    assert received == []


def test_send_line_without_token_returns_false():
    assert asyncio.run(alerts.send_line("", "hello")) is False


# ---- dispatch ---- #

def test_dispatch_skips_disabled_webhook(stub):
    server, received = stub
    alerts.set_rules(_payload(_channels(webhook={"enabled": False,
                                                "url": _stub_url(server)})))
    result = asyncio.run(alerts.dispatch(_alert()))
    assert "webhook" not in result
    assert "line" not in result
    assert received == []


def test_dispatch_sends_enabled_webhook(stub):
    server, received = stub
    alerts.set_rules(_payload(_channels(webhook={"enabled": True,
                                                "url": _stub_url(server)})))
    result = asyncio.run(alerts.dispatch(_alert()))
    assert result == {"webhook": True}
    assert len(received) == 1
    assert json.loads(received[0]["body"])["title"] == "CPU temperature high"


def test_dispatch_never_raises_when_webhook_unreachable():
    alerts.set_rules(_payload(_channels(webhook={"enabled": True,
                                                "url": "http://127.0.0.1:9/hook"})))
    assert asyncio.run(alerts.dispatch(_alert())) == {"webhook": False}


# ---- API endpoints ---- #

def test_alert_endpoints_require_admin(client):
    assert client.post("/api/alerts/test", json={}).status_code == 401
    assert client.post("/api/alerts/notify", json={"title": "t"},
                       headers={"X-Requested-With": "windy-dashboard"}).status_code == 401


def test_notify_rejects_missing_or_wrong_requested_with(client):
    assert client.post("/api/alerts/notify", json={"title": "t", "message": "m"},
                       headers=ADMIN_HEADERS).status_code == 403
    assert client.post("/api/alerts/notify", json={"title": "t", "message": "m"},
                       headers={**ADMIN_HEADERS,
                                "X-Requested-With": "nope"}).status_code == 403


def test_notify_with_header_ok(client):
    r = client.post("/api/alerts/notify",
                    json={"title": "t", "message": "m", "severity": "warning",
                          "source": "compare", "regressions": ["x"]},
                    headers=NOTIFY_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_notify_truncates_title_and_message(client, stub):
    server, received = stub
    alerts.set_rules(_payload(_channels(webhook={"enabled": True,
                                                "url": _stub_url(server)})))
    resp = client.post("/api/alerts/notify",
                       json={"title": "T" * 500, "message": "M" * 3000},
                       headers=NOTIFY_HEADERS)
    assert resp.status_code == 200
    assert len(received) == 1
    body = json.loads(received[0]["body"])
    assert len(body["title"]) == 200
    assert len(body["message"]) == 1000


def test_notify_dispatches_webhook_for_real(client, stub):
    server, received = stub
    alerts.set_rules(_payload(_channels(webhook={"enabled": True,
                                                "url": _stub_url(server)})))
    resp = client.post("/api/alerts/notify",
                       json={"title": "Compare alert", "message": "3 regressions",
                             "source": "compare", "regressions": ["a", "b"]},
                       headers=NOTIFY_HEADERS)
    assert resp.status_code == 200
    assert len(received) == 1
    body = json.loads(received[0]["body"])
    assert body["id"] == "external"
    assert body["title"] == "Compare alert"
    assert body["source"] == "compare"
    assert body["regressions"] == ["a", "b"]


def test_alert_test_endpoint_returns_channels(client):
    r = client.post("/api/alerts/test", json={"title": "T", "message": "M"},
                    headers=ADMIN_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["channels"], dict)
    assert body["channels"]["toast"] is True


def test_alert_test_endpoint_body_optional(client):
    r = client.post("/api/alerts/test", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert "channels" in r.json()
