"""Security guards for the maintenance module: host allowlist + CSRF check."""
from __future__ import annotations

import os

from fastapi import HTTPException, Request

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}

TEST_HOST = "testserver"
TEST_MODE_ENV = "DASH_TEST_MODE"

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "windy-dashboard"
CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

HOST_FORBIDDEN_DETAIL = "forbidden: host"
CSRF_FORBIDDEN_DETAIL = "forbidden: csrf"


def split_host(value: str | None) -> str:
    """Strip the port from a Host header value (supports `[::1]:8000`)."""
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith("["):
        end = raw.find("]")
        return raw[1:end] if end != -1 else raw
    if raw.count(":") == 1:
        return raw.split(":", 1)[0]
    return raw


def _allowed_hosts() -> set[str]:
    """Production allowlist plus `testserver` only while `DASH_TEST_MODE=1`.

    The env is read per call so importing order never decides the policy.
    """
    hosts = set(ALLOWED_HOSTS)
    if (os.environ.get(TEST_MODE_ENV) or "").strip() == "1":
        hosts.add(TEST_HOST)
    return hosts


def require_allowed_host(request: Request) -> None:
    if split_host(request.headers.get("host")) not in _allowed_hosts():
        raise HTTPException(status_code=403, detail=HOST_FORBIDDEN_DETAIL)


def require_csrf(request: Request) -> None:
    if request.method.upper() in CSRF_METHODS:
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(status_code=403, detail=CSRF_FORBIDDEN_DETAIL)
