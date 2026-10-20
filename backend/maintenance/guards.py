"""Security guards for the maintenance module: host allowlist + CSRF check."""
from __future__ import annotations

from fastapi import HTTPException, Request

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}

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


def require_allowed_host(request: Request) -> None:
    if split_host(request.headers.get("host")) not in ALLOWED_HOSTS:
        raise HTTPException(status_code=403, detail=HOST_FORBIDDEN_DETAIL)


def require_csrf(request: Request) -> None:
    if request.method.upper() in CSRF_METHODS:
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(status_code=403, detail=CSRF_FORBIDDEN_DETAIL)
