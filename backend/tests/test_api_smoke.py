import sys

import pytest
from fastapi.testclient import TestClient

import history
import main
import sensors_lhm
from security import actions


@pytest.fixture()
def client():
    return TestClient(main.app)


def test_history_valid_range(client, monkeypatch):
    monkeypatch.setattr(history, "query_range", lambda rng="1h": {"range": rng, "bucket_sec": 10, "count": 1, "points": []})
    r = client.get("/api/history", params={"range": "1h"})
    assert r.status_code == 200
    assert r.json()["range"] == "1h"


def test_history_invalid_range_422(client):
    r = client.get("/api/history", params={"range": "bogus"})
    assert r.status_code == 422


def test_sensors_status(client, monkeypatch):
    monkeypatch.setattr(sensors_lhm, "get_status", lambda: {"state": "ok", "available": True, "elevated": False, "reason": "ok", "message": "ok"})
    r = client.get("/api/sensors/status")
    assert r.status_code == 200
    assert r.json()["lhm_available"] is True


def test_blocked_rules(client, monkeypatch):
    async def fake_list():
        return {"ok": True, "rules": []}

    monkeypatch.setattr(actions, "list_block_rules", fake_list)
    r = client.get("/api/security/blocked")
    assert r.status_code == 200
    assert r.json()["ok"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
