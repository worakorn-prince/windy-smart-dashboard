r"""Retention tool for agent .jsonl logs — archive + prune.

Scan <root>/.agent/**/*.jsonl (skipping .agent/archive/**), move rows whose
timestamp is older than --days into <root>/.agent/archive/<stem>-<YYYYMMDD>.jsonl
(append mode), then rewrite the source file with the remaining rows.

Rules:
- Timestamps are read from common keys (ts / timestamp / time / created_at /
  date); epoch seconds/milliseconds or ISO-8601 strings are accepted.
- Rows that fail to parse (invalid JSON or no recognizable timestamp) are
  ALWAYS kept in the source file — data is never dropped silently.
- --dry-run reports what would happen without touching any file.
- Only .agent/** files inside the given root are touched.

Usage:
    python scripts/retention.py --root D:\proj --days 14 [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

_TS_KEYS = ("ts", "timestamp", "time", "created_at", "date")
_EPOCH_MS_THRESHOLD = 1e11


def _to_epoch(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        epoch = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            epoch = float(stripped)
        except ValueError:
            try:
                dt = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                return None
            if dt.tzinfo is None:
                epoch = dt.timestamp()
            else:
                epoch = dt.timestamp()
    else:
        return None
    if epoch > _EPOCH_MS_THRESHOLD:
        epoch /= 1000.0
    return epoch


def row_epoch(obj: Any) -> float | None:
    """Extract an epoch-seconds timestamp from a parsed .jsonl row, or None."""
    if not isinstance(obj, dict):
        return None
    for key in _TS_KEYS:
        if key in obj:
            epoch = _to_epoch(obj[key])
            if epoch is not None:
                return epoch
    return None


def collect_jsonl(agent_dir: Path) -> Iterator[Path]:
    """All .jsonl files under agent_dir except the archive folder itself."""
    for path in sorted(agent_dir.rglob("*.jsonl")):
        if "archive" in path.relative_to(agent_dir).parts:
            continue
        yield path


def process_file(path: Path, cutoff: float, archive_dir: Path,
                 dry_run: bool) -> dict[str, Any]:
    """Archive old rows of one file and rewrite it; returns a per-file summary."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"file": str(path), "total": 0, "archived": 0, "kept": 0,
                "unparseable": 0, "archive": None, "error": str(exc)}

    kept: list[str] = []
    archived: list[str] = []
    unparseable = 0
    for line in lines:
        if not line.strip():
            kept.append(line)
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            kept.append(line)
            unparseable += 1
            continue
        epoch = row_epoch(obj)
        if epoch is None:
            kept.append(line)
            unparseable += 1
        elif epoch < cutoff:
            archived.append(line)
        else:
            kept.append(line)

    summary: dict[str, Any] = {
        "file": str(path), "total": len(lines), "archived": len(archived),
        "kept": len(kept), "unparseable": unparseable, "archive": None,
        "error": None,
    }
    if not archived:
        return summary

    stamp = time.strftime("%Y%m%d")
    archive_path = archive_dir / f"{path.stem}-{stamp}.jsonl"
    summary["archive"] = str(archive_path)
    if dry_run:
        return summary

    archive_dir.mkdir(parents=True, exist_ok=True)
    with archive_path.open("a", encoding="utf-8") as fh:
        for line in archived:
            fh.write(line + "\n")

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    tmp.replace(path)
    return summary


def run(root: str | Path = ".", days: float = 30.0,
        dry_run: bool = False) -> dict[str, Any]:
    """Scan <root>/.agent and archive/prune old rows; returns a full summary."""
    root_dir = Path(root).resolve()
    agent_dir = root_dir / ".agent"
    cutoff = time.time() - max(days, 0.0) * 86400.0
    mode = "dry-run" if dry_run else "write"
    totals = {"files": 0, "archived": 0, "kept": 0, "unparseable": 0}
    results: list[dict[str, Any]] = []

    if agent_dir.is_dir():
        for path in collect_jsonl(agent_dir):
            summary = process_file(path, cutoff, agent_dir / "archive", dry_run)
            results.append(summary)
            if summary["error"] is None:
                totals["files"] += 1
                totals["archived"] += summary["archived"]
                totals["kept"] += summary["kept"]
                totals["unparseable"] += summary["unparseable"]
    return {"root": str(root_dir), "mode": mode, "days": days,
            "cutoff": cutoff, "totals": totals, "files": results}


def _print_summary(result: dict[str, Any]) -> None:
    print(f"root={result['root']} mode={result['mode']} "
          f"days={result['days']:g} cutoff_ts={result['cutoff']:.3f}")
    if not result["files"]:
        print("no .agent/*.jsonl files found (or .agent missing)")
    for item in result["files"]:
        if item["error"] is not None:
            print(f"{item['file']}: ERROR {item['error']}")
            continue
        print(f"{item['file']}: total={item['total']} old->archive="
              f"{item['archived']} kept={item['kept']} unparseable="
              f"{item['unparseable']} archive={item['archive'] or '-'}")
    totals = result["totals"]
    print(f"TOTAL files={totals['files']} archived={totals['archived']} "
          f"kept={totals['kept']} unparseable={totals['unparseable']}")


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/retention.py",
        description="เก็บถาวร+ตัด log ของ agent (.agent/**/*.jsonl) ตามอายุ")
    parser.add_argument("--root", default=".",
                        help="โฟลเดอร์โปรเจกต์ที่มี .agent (default: .)")
    parser.add_argument("--days", type=float, default=30.0,
                        help="อายุสูงสุดของแถวที่คงไว้ เป็นวัน (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="รายงานอย่างเดียว ไม่เขียนไฟล์ใด")
    args = parser.parse_args(argv)

    result = run(args.root, args.days, dry_run=args.dry_run)
    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
