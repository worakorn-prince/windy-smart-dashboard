"""On-demand network diagnostics package with strict timeouts and SSRF guards."""

from __future__ import annotations

import ipaddress
import re

HOSTNAME_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
MAX_HOSTNAME_LENGTH = 253

PROBE_TIMEOUT_CAP_MS = 10000
HTTP_TIMEOUT_CAP_MS = 30000


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _validate_ip_literal(target: str, allow_private: bool) -> bool:
    try:
        ip = ipaddress.ip_address(target)
    except ValueError:
        return False
    if not allow_private and is_blocked_ip(ip):
        raise ValueError(f"Blocked target address (private/loopback/link-local): {target}")
    return True


def _validate_hostname(target: str) -> None:
    if len(target) > MAX_HOSTNAME_LENGTH:
        raise ValueError(f"Target too long (max {MAX_HOSTNAME_LENGTH} chars)")
    labels = target.split(".")
    for label in labels:
        if not label or not HOSTNAME_LABEL_RE.match(label):
            raise ValueError(f"Invalid hostname label: {label!r}")


def validate_target(target: str, allow_private: bool = False) -> str:
    """Validate a diagnostic target (hostname or IP literal); returns the cleaned target."""
    if not isinstance(target, str):
        raise TypeError("Target must be a string")
    cleaned = target.strip()
    if not cleaned or any(ch.isspace() for ch in cleaned):
        raise ValueError("Target must not be empty or contain whitespace")
    if "://" in cleaned:
        raise ValueError(f"Target must not include a scheme prefix: {cleaned}")
    if _validate_ip_literal(cleaned, allow_private):
        return cleaned
    if ":" in cleaned:
        raise ValueError(f"Invalid target (port or scheme not allowed): {cleaned}")
    if "@" in cleaned or "%" in cleaned:
        raise ValueError(f"Invalid target characters: {cleaned}")
    _validate_hostname(cleaned)
    return cleaned.lower()


def validate_timeout_ms(timeout_ms: int, cap_ms: int) -> int:
    if timeout_ms < 100:
        raise ValueError("timeout_ms must be at least 100")
    return min(timeout_ms, cap_ms)
