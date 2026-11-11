"""Tests for OpenAPI metadata and the /api/version endpoint (INFRA-402).

Covers:
  - GET /openapi.json exposes title/version metadata
  - required API paths are present in the schema
  - GET /api/version returns the full version payload matching info.version
  - the SPA catch-all route never leaks into the schema
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main

REQUIRED_PATHS = [
    "/api/system",
    "/api/history",
    "/api/alerts/rules",
    "/api/reports",
    "/api/security/events",
    "/api/maintenance/status",
]


@pytest.fixture()
def client():
    return TestClient(main.app)


@pytest.fixture()
def schema(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    return r.json()


def test_openapi_metadata(schema):
    info = schema["info"]

    assert "Windy" in info["title"]
    assert info["version"] == "0.6.1"
    assert info.get("description")


@pytest.mark.parametrize("path", REQUIRED_PATHS)
def test_openapi_contains_required_paths(schema, path):
    assert path in schema["paths"]


def test_openapi_hides_spa_catch_all(schema):
    assert "/{full_path}" not in schema["paths"]
    assert not [p for p in schema["paths"] if "full_path" in p]


def test_version_endpoint(client, schema):
    r = client.get("/api/version")

    assert r.status_code == 200
    payload = r.json()
    assert payload["name"] == "windy-smart-dashboard"
    assert payload["version"] == "0.6.1"
    assert payload["version"] == schema["info"]["version"]
    assert isinstance(payload["python"], str) and payload["python"]
    assert isinstance(payload["platform"], str) and payload["platform"]
    assert isinstance(payload["port"], int)


def test_app_version_constant_matches_schema(schema):
    assert schema["info"]["version"] == main.APP_VERSION


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
