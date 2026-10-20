import pytest
from fastapi.testclient import TestClient

import config
import main
from maintenance import history as action_log


@pytest.fixture(autouse=True)
def _isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "history.db")
    yield


def _client():
    try:
        return TestClient(main.app, base_url="http://testserver", client=("127.0.0.1", 51000))
    except TypeError:
        return TestClient(main.app)


def _get(path: str):
    return _client().get(f"/api/maintenance{path}")


def test_history_endpoint_returns_rows_and_meta():
    action_log.record("wu-scan", ok=True, duration_ms=12, detail={"updateCount": 0})
    action_log.record("clean", target="windows-temp", ok=False, duration_ms=7, error="boom")

    response = _get("/history?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["count"] == 2
    assert len(body["rows"]) == 2
    assert "servedAt" in body
    assert body["rows"][0]["action"] == "clean"


@pytest.mark.parametrize("limit", [9999, 0, -5])
def test_history_endpoint_clamps_limit(limit):
    action_log.record("wu-scan", ok=True, duration_ms=1)

    response = _get(f"/history?limit={limit}")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["rows"][0]["action"] == "wu-scan"
