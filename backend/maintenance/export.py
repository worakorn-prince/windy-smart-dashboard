"""CSV/JSON export builders (no files are written to disk).

CSV layout matches `updater/lib/export.js`: BOM prefix, CRLF line endings and
the same eight columns. Building the payload in memory avoids any path
traversal surface.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

KINDS: tuple[str, ...] = ("devices", "history")
FORMATS: tuple[str, ...] = ("csv", "json")

DEVICE_HEADER: tuple[str, ...] = (
    "device",
    "driverName",
    "version",
    "date",
    "status",
    "deviceId",
    "errorCode",
    "errorText",
)

HISTORY_HEADER: tuple[str, ...] = (
    "ts",
    "action",
    "target",
    "ok",
    "durationMs",
    "detail",
    "error",
)

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
JSON_MEDIA_TYPE = "application/json"

_INJECTION_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def _neutralize(text: str) -> str:
    """Prefix a single quote when a cell could be read as a spreadsheet formula."""
    if text.startswith(_INJECTION_PREFIXES):
        return "'" + text
    return text


def _csv_cell(value: Any) -> str:
    text = _neutralize("" if value is None else str(value))
    if any(ch in text for ch in (",", '"', "\r", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


def _csv(header: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(_csv_cell(row.get(key)) for key in header))
    return "\uFEFF" + "\r\n".join(lines)


def _device_row(device: dict[str, Any]) -> dict[str, Any]:
    name = device.get("device")
    if name is None:
        name = device.get("name")
    error_code = device.get("errorCode")
    if error_code is None:
        error_code = device.get("problemCode")
    return {
        "device": name,
        "driverName": device.get("driverName"),
        "version": device.get("version"),
        "date": device.get("date"),
        "status": device.get("status"),
        "deviceId": device.get("deviceId"),
        "errorCode": error_code,
        "errorText": device.get("errorText"),
    }


def build_csv(devices: list[dict[str, Any]]) -> str:
    """Device CSV with BOM + CRLF, identical to the desktop updater."""
    rows = [_device_row(device) for device in (devices or []) if isinstance(device, dict)]
    return _csv(DEVICE_HEADER, rows)


def _filename(kind: str, fmt: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"maintenance-{kind}-{stamp}.{fmt}"


def build_payload(
    kind: str,
    devices: list[dict[str, Any]] | None = None,
    history_rows: list[dict[str, Any]] | None = None,
    format: str = "json",
) -> tuple[str, str, str]:
    """Return `(body, media_type, filename)` for a download response."""
    safe_kind = str(kind or "").strip().lower()
    safe_format = str(format or "").strip().lower()
    if safe_kind not in KINDS:
        raise ValueError(f"unsupported export kind: {kind!r}")
    if safe_format not in FORMATS:
        raise ValueError(f"unsupported export format: {format!r}")

    if safe_kind == "devices":
        items = [device for device in (devices or []) if isinstance(device, dict)]
        rows = [_device_row(device) for device in items]
        header = DEVICE_HEADER
    else:
        rows = [row for row in (history_rows or []) if isinstance(row, dict)]
        header = HISTORY_HEADER

    if safe_format == "csv":
        body = _csv(header, rows)
        media_type = CSV_MEDIA_TYPE
    else:
        body = json.dumps(rows, ensure_ascii=False, default=str)
        media_type = JSON_MEDIA_TYPE

    return body, media_type, _filename(safe_kind, safe_format)
