"""Scheduled HTML reports built from real history data.

Generates one self-contained HTML file (inline CSS, no external assets) per
report. Data sources are read-only and every section is best-effort: a missing
or broken database simply renders "no data" instead of failing the whole
report. All dynamic values are escaped with :func:`html.escape`.
"""
from __future__ import annotations

import html
import json
import logging
import re
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger("dashboard.reports")

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
REPORT_NAME_RE = re.compile(r"^report-\d{8}-\d{6}-d(1|7)\.html$")
ALLOWED_DAYS = (1, 7)
DEFAULT_KEEP = 30

_EVENT_LIMIT = 100
_PROCESS_LIMIT = 10
_DETAIL_PREVIEW = 300


def _esc(value: Any) -> str:
    """Escape any value for safe HTML text/attribute embedding."""
    return html.escape("" if value is None else str(value), quote=True)


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num(value: Any, digits: int = 1) -> str:
    number = _float_or_none(value)
    if number is None:
        return "no data"
    return f"{number:,.{digits}f}"


def _gb(value: Any) -> str:
    number = _float_or_none(value)
    if number is None:
        return "no data"
    return f"{number:,.1f} GB"


def _cutoff_iso(days: int) -> str:
    moment = datetime.now(UTC) - timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _read_query(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    """Run a read-only query against the history DB with its own connection."""
    path = Path(config.HISTORY_DB)
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error:
        logger.warning("report DB unavailable", exc_info=True)
        return []
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        logger.warning("report query failed", exc_info=True)
        return []
    finally:
        conn.close()


def _history_summary(days: int) -> dict[str, Any]:
    """Average/max CPU, memory and disk usage over the last ``days`` days."""
    cutoff = time.time() - days * 86400.0
    rows = _read_query(
        "SELECT COUNT(*) AS n, AVG(cpu_pct) AS cpu_avg, MAX(cpu_pct) AS cpu_max, "
        "AVG(ram_pct) AS mem_avg, MAX(ram_pct) AS mem_max "
        "FROM samples WHERE ts >= ?",
        (cutoff,),
    )
    row = rows[0] if rows else None

    disk_rows = _read_query(
        "SELECT AVG(CASE WHEN total_gb > 0 THEN used_gb * 100.0 / total_gb END) AS disk_avg, "
        "MAX(CASE WHEN total_gb > 0 THEN used_gb * 100.0 / total_gb END) AS disk_max "
        "FROM disk_samples WHERE ts >= ?",
        (_cutoff_iso(days),),
    )
    disk_row = disk_rows[0] if disk_rows else None

    return {
        "samples": int(row["n"] or 0) if row else 0,
        "cpu": {
            "avg": _float_or_none(row["cpu_avg"]) if row else None,
            "max": _float_or_none(row["cpu_max"]) if row else None,
        },
        "mem": {
            "avg": _float_or_none(row["mem_avg"]) if row else None,
            "max": _float_or_none(row["mem_max"]) if row else None,
        },
        "disk": {
            "avg": _float_or_none(disk_row["disk_avg"]) if disk_row else None,
            "max": _float_or_none(disk_row["disk_max"]) if disk_row else None,
        },
    }


def _security_events() -> list[dict[str, Any]]:
    """Persisted security events (newest first); [] when unavailable."""
    try:
        from security import persistence

        events = persistence.list_events(limit=_EVENT_LIMIT)
    except Exception:
        logger.warning("security events unavailable for report", exc_info=True)
        return []
    return events if isinstance(events, list) else []


def _disk_health(days: int) -> list[dict[str, Any]]:
    """Latest per-mount usage plus the days-to-full forecast."""
    try:
        import disk_health
    except Exception:
        logger.warning("disk health unavailable for report", exc_info=True)
        return []
    try:
        disks = disk_health.disk_usage()
    except Exception:
        logger.warning("disk usage snapshot failed for report", exc_info=True)
        return []
    rows: list[dict[str, Any]] = []
    for disk in disks or []:
        if not isinstance(disk, dict):
            continue
        mount = disk.get("mount")
        try:
            forecast = disk_health.predict_days_to_full(disk_health.get_samples(mount))
        except Exception:
            logger.warning("disk forecast failed for %s", mount, exc_info=True)
            forecast = {"days_to_full": None, "trend_gb_per_day": None, "samples": 0}
        rows.append({**disk, "forecast": forecast})
    return rows


def _top_processes() -> list[dict[str, Any]]:
    """Top processes from the newest process_samples batch."""
    rows = _read_query(
        "SELECT name, pid, cpu_pct, mem_mb FROM process_samples "
        "WHERE ts = (SELECT MAX(ts) FROM process_samples) "
        "ORDER BY cpu_pct DESC, mem_mb DESC LIMIT ?",
        (_PROCESS_LIMIT,),
    )
    return [dict(row) for row in rows]


def _detail_text(detail: Any) -> str:
    if not detail:
        return ""
    try:
        text = json.dumps(detail, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(detail)
    return text[:_DETAIL_PREVIEW]


def _summary_html(summary: dict[str, Any]) -> str:
    if summary["samples"] <= 0:
        return '<p class="muted">no data</p>'
    rows = "".join(
        f'<tr><th scope="row">{_esc(label)}</th>'
        f"<td>{_num(values['avg'])}</td><td>{_num(values['max'])}</td></tr>"
        for label, values in (
            ("CPU (%)", summary["cpu"]),
            ("Memory (%)", summary["mem"]),
            ("Disk usage (%)", summary["disk"]),
        )
    )
    sample_count = _esc(f"{summary['samples']:,}")
    return (
        f'<p class="muted">จำนวน samples: {sample_count} · '
        f"ช่วง {_esc(summary['days'])} วัน</p>"
        '<table><thead><tr><th scope="col">Metric</th><th scope="col">Avg</th>'
        f'<th scope="col">Max</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _events_html(events: list[dict[str, Any]]) -> str:
    if not events:
        return '<p class="muted">no data</p>'
    rows = "".join(
        f"<tr><td>{_esc(event.get('ts'))}</td><td>{_esc(event.get('kind'))}</td>"
        f"<td>{_esc(event.get('source_ip'))}</td>"
        f'<td class="detail">{_esc(_detail_text(event.get("detail")))}</td></tr>'
        for event in events
    )
    return (
        f'<p class="muted">ทั้งหมด {_esc(len(events))} เหตุการณ์ (ล่าสุดก่อน)</p>'
        '<table><thead><tr><th scope="col">เวลา</th><th scope="col">ชนิด</th>'
        '<th scope="col">Source IP</th><th scope="col">รายละเอียด</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


def _disks_html(disks: list[dict[str, Any]]) -> str:
    if not disks:
        return '<p class="muted">no data</p>'
    rows = []
    for disk in disks:
        forecast = disk.get("forecast") or {}
        days_to_full = forecast.get("days_to_full")
        prediction = "no prediction" if days_to_full is None else f"เต็มใน ~{_num(days_to_full)} วัน"
        rows.append(
            f"<tr><td>{_esc(disk.get('mount'))}</td>"
            f"<td>{_esc(_gb(disk.get('used_gb')))} / {_esc(_gb(disk.get('total_gb')))}</td>"
            f"<td>{_num(disk.get('used_pct'))}</td>"
            f"<td>{_esc(prediction)}</td></tr>"
        )
    return (
        '<table><thead><tr><th scope="col">Mount</th><th scope="col">Used / Total</th>'
        '<th scope="col">Used %</th><th scope="col">คาดการณ์</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _processes_html(processes: list[dict[str, Any]]) -> str:
    if not processes:
        return '<p class="muted">no data</p>'
    rows = "".join(
        f"<tr><td>{_esc(proc.get('name'))}</td><td>{_esc(proc.get('pid'))}</td>"
        f"<td>{_num(proc.get('cpu_pct'))}</td><td>{_num(proc.get('mem_mb'), 2)}</td></tr>"
        for proc in processes
    )
    return (
        '<table><thead><tr><th scope="col">Process</th><th scope="col">PID</th>'
        '<th scope="col">CPU %</th><th scope="col">Memory (MB)</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
    )


_STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 24px;
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  background: #0e1218;
  color: #e6edf3;
}
main { max-width: 1100px; margin: 0 auto; }
header { max-width: 1100px; margin: 0 auto 22px; }
h1 { margin: 0 0 6px; font-size: 22px; }
h2 { margin: 0 0 10px; font-size: 15px; color: #9fb0c3; text-transform: uppercase;
     letter-spacing: 0.04em; }
section {
  margin-bottom: 18px;
  padding: 16px;
  background: #151b24;
  border: 1px solid #263140;
  border-radius: 10px;
}
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th, td { padding: 6px 8px; border-bottom: 1px solid #263140; text-align: left;
         vertical-align: top; }
thead th { color: #9fb0c3; font-size: 11.5px; text-transform: uppercase; }
tbody tr:last-child td { border-bottom: none; }
td.detail { word-break: break-word; color: #b9c7d6; }
.muted { color: #8494a7; margin: 0 0 8px; }
.meta { font-size: 12px; color: #8494a7; }
footer { max-width: 1100px; margin: 22px auto 0; color: #6f8095; font-size: 11.5px; }
"""


def _render(
    days: int,
    generated_at: str,
    summary: dict[str, Any],
    events: list[dict[str, Any]],
    disks: list[dict[str, Any]],
    processes: list[dict[str, Any]],
) -> str:
    summary["days"] = days
    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard report — {_esc(f"d{days}")}</title>
<style>{_STYLE}</style>
</head>
<body>
<header>
  <h1>Windy Smart Dashboard — รายงานสรุป</h1>
  <p class="meta">ช่วงข้อมูล {days} วัน · สร้างเมื่อ {_esc(generated_at)} (UTC) · ไฟล์เดียว ไม่มี external asset</p>
</header>
<main>
  <section>
    <h2>สรุปภาพรวมระบบ</h2>
    {_summary_html(summary)}
  </section>
  <section>
    <h2>เหตุการณ์ความปลอดภัย</h2>
    {_events_html(events)}
  </section>
  <section>
    <h2>สุขภาพดิสก์</h2>
    {_disks_html(disks)}
  </section>
  <section>
    <h2>โปรเซสล่าสุด (Top {_PROCESS_LIMIT})</h2>
    {_processes_html(processes)}
  </section>
</main>
<footer>Generated by Windy Smart Dashboard · โฟลเดอร์ปลายทาง reports/ · เก็บสูงสุด 30 ไฟล์</footer>
</body>
</html>
"""


def generate_report(days: int = 1) -> Path:
    """Build a self-contained HTML report and return the written path."""
    if days not in ALLOWED_DAYS:
        raise ValueError("days must be 1 or 7")

    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    summary = _history_summary(days)
    events = _security_events()
    disks = _disk_health(days)
    processes = _top_processes()

    directory = Path(REPORTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"report-{datetime.now().strftime('%Y%m%d-%H%M%S')}-d{days}.html"
    path = directory / name
    path.write_text(
        _render(days, generated_at, summary, events, disks, processes),
        encoding="utf-8",
    )
    return path


def list_reports() -> list[dict[str, Any]]:
    """Return report metadata, newest first."""
    directory = Path(REPORTS_DIR)
    if not directory.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for entry in directory.iterdir():
        if not entry.is_file() or not REPORT_NAME_RE.match(entry.name):
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        items.append({"name": entry.name, "size": stat.st_size, "mtime": stat.st_mtime})
    items.sort(key=lambda item: (item["mtime"], item["name"]), reverse=True)
    return items


def prune_reports(keep: int = DEFAULT_KEEP) -> int:
    """Delete the oldest reports beyond ``keep``; return the number removed."""
    try:
        keep_count = max(int(keep), 0)
    except (TypeError, ValueError):
        keep_count = DEFAULT_KEEP
    removed = 0
    for item in list_reports()[keep_count:]:
        try:
            (Path(REPORTS_DIR) / item["name"]).unlink()
        except OSError:
            logger.warning("report prune failed for %s", item["name"], exc_info=True)
            continue
        removed += 1
    return removed
