"""Tests for viewer API endpoints."""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import config
import main
import viewer_api

REQUIRED_PATHS = [
    "/api/viewer/single",
    "/api/viewer/all",
    "/api/viewer/status",
    "/api/viewer/rebuild",
]


@pytest.fixture(autouse=True)
def set_admin_token():
    """Set a test admin token for all tests."""
    original = config.ADMIN_TOKEN
    config.ADMIN_TOKEN = "test-token"
    os.environ["DASH_ADMIN_TOKEN"] = "test-token"
    yield
    config.ADMIN_TOKEN = original
    if original:
        os.environ["DASH_ADMIN_TOKEN"] = original
    else:
        os.environ.pop("DASH_ADMIN_TOKEN", None)


@pytest.fixture()
def client():
    return TestClient(main.app)


@pytest.fixture()
def schema(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def test_openapi_contains_viewer_paths(schema):
    for path in REQUIRED_PATHS:
        assert path in schema["paths"]


def test_get_single_no_data_returns_404(client, tmp_path):
    with patch.object(viewer_api, "DATA_PATH", tmp_path / "missing.json"):
        r = client.get("/api/viewer/single")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "NO_DATA"


def test_get_all_no_data_returns_404(client, tmp_path):
    with patch.object(viewer_api, "ALL_PATH", tmp_path / "missing.json"):
        r = client.get("/api/viewer/all")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "NO_DATA"


def test_get_single_with_data(client, tmp_path):
    test_data = {
        "generated_at": "2026-10-21T13:26:56.390808+00:00",
        "kpis": {
            "total_tasks": 42,
            "done": 30,
            "failed": 5,
            "cancelled": 2,
            "success_rate": 0.71,
            "total_tool_calls": 100,
            "recoveries": 3,
            "review_fails": 1,
            "tokens_total": 5000,
            "open_alerts": 2,
        },
        "per_task": [],
        "timeline": [],
        "recent_activity": [],
        "alerts": [],
    }
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(test_data), encoding="utf-8")

    with patch.object(viewer_api, "DATA_PATH", data_file):
        r = client.get("/api/viewer/single")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["kpis"]["total_tasks"] == 42


def test_get_all_with_data(client, tmp_path):
    test_data = {
        "generated_at": "2026-10-21T13:26:56.390808+00:00",
        "kpis": {
            "total_tasks": 100,
            "done": 80,
            "failed": 10,
            "cancelled": 5,
            "success_rate": 0.8,
            "total_tool_calls": 200,
            "recoveries": 5,
            "review_fails": 2,
            "tokens_total": 10000,
            "open_alerts": 3,
        },
        "per_task": [],
        "timeline": [],
        "recent_activity": [],
        "alerts": [],
    }
    data_file = tmp_path / "all-projects.json"
    data_file.write_text(json.dumps(test_data), encoding="utf-8")

    with patch.object(viewer_api, "ALL_PATH", data_file):
        r = client.get("/api/viewer/all")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["kpis"]["total_tasks"] == 100


def test_status_endpoint(client, tmp_path):
    single_file = tmp_path / "data.json"
    all_file = tmp_path / "all-projects.json"
    single_file.write_text(json.dumps({"kpis": {"total_tasks": 1}}), encoding="utf-8")

    with patch.object(viewer_api, "DATA_PATH", single_file), patch.object(
        viewer_api, "ALL_PATH", all_file
    ):
        r = client.get("/api/viewer/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["single"]["exists"] is True
    assert body["all"]["exists"] is False


def test_rebuild_success(client):
    def mock_run_script(script: str, timeout: float = 180.0):
        return {"script": script, "code": 0, "stdout_tail": "ok", "stderr_tail": ""}

    with patch.object(viewer_api, "_run_script", side_effect=mock_run_script):
        r = client.post(
            "/api/viewer/rebuild",
            json={"aggregate": False},
            headers={"x-admin-token": "test-token", "x-requested-with": "windy-dashboard"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "durationMs" in body
    assert "outputs" in body
    assert len(body["outputs"]) == 1


def test_rebuild_with_aggregate(client):
    def mock_run_script(script: str, timeout: float = 180.0):
        return {"script": script, "code": 0, "stdout_tail": "ok", "stderr_tail": ""}

    with patch.object(viewer_api, "_run_script", side_effect=mock_run_script):
        r = client.post(
            "/api/viewer/rebuild",
            json={"aggregate": True},
            headers={"x-admin-token": "test-token", "x-requested-with": "windy-dashboard"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["outputs"]) == 2


def test_rebuild_script_failure(client):
    def mock_run_script(script: str, timeout: float = 180.0):
        return {"script": script, "code": 1, "stdout_tail": "", "stderr_tail": "error"}

    with patch.object(viewer_api, "_run_script", side_effect=mock_run_script):
        r = client.post(
            "/api/viewer/rebuild",
            json={"aggregate": False},
            headers={"x-admin-token": "test-token", "x-requested-with": "windy-dashboard"},
        )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail["code"] == "REBUILD_FAILED"


def test_rebuild_missing_csrf_header(client):
    r = client.post(
        "/api/viewer/rebuild",
        json={"aggregate": False},
        headers={"x-admin-token": "test-token"},
    )
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail == "missing_origin_header"


def test_rebuild_missing_admin_token(client):
    r = client.post(
        "/api/viewer/rebuild",
        json={"aggregate": False},
        headers={"x-requested-with": "windy-dashboard"},
    )
    assert r.status_code == 401


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
