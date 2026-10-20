import contextlib
import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import config
import history

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
try:
    import retention
finally:
    with contextlib.suppress(ValueError):
        if str(SCRIPTS_DIR) in sys.path:
            sys.path.remove(str(SCRIPTS_DIR))


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "h.db")
    history._conn = None
    history._last_prune_day = None
    yield
    if history._conn is not None:
        history._conn.close()
        history._conn = None
    history._last_prune_day = None


def _seed(conn, start_ts, count, step=10):
    for i in range(count):
        conn.execute(
            "INSERT OR REPLACE INTO samples "
            "(ts, cpu_pct, ram_pct, swap_pct, cpu_temp, gpu_temp, disk_temp_max, "
            "cpu_power_w, gpu_power_w, net_sent_bps, net_recv_bps, "
            "disk_read_bps, disk_write_bps) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (start_ts + i * step, 50, 40, 5, 60, 55, 35, 1200, 30,
             1000, 2000, 300000, 400000),
        )
    conn.commit()


def test_prune_deletes_only_old_rows(tmp_db):
    conn = history._get_conn()
    now = time.time()
    _seed(conn, now - 40 * 86400, count=10)
    _seed(conn, now - 5 * 86400, count=6)
    total_before = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert total_before == 16

    deleted = history.prune(30)
    assert deleted == 10
    remaining = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert remaining == 6
    min_ts = conn.execute("SELECT MIN(ts) FROM samples").fetchone()[0]
    assert min_ts >= now - 30 * 86400


def test_prune_negative_days_treated_as_zero(tmp_db):
    conn = history._get_conn()
    _seed(conn, time.time() - 100, count=5)
    deleted = history.prune(-1)
    assert deleted == 5
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0


def test_prune_no_rows_returns_zero(tmp_db):
    history._get_conn()
    assert history.prune(30) == 0


def test_retention_days_from_env(monkeypatch):
    monkeypatch.setenv("DASH_HISTORY_DAYS", "7")
    assert history._retention_days() == 7.0
    monkeypatch.setenv("DASH_HISTORY_DAYS", "bogus")
    assert history._retention_days() == 30.0
    monkeypatch.setenv("DASH_HISTORY_DAYS", "-5")
    assert history._retention_days() == 0.0
    monkeypatch.delenv("DASH_HISTORY_DAYS", raising=False)
    assert history._retention_days() == 30.0


def test_auto_prune_triggers_once_per_day(tmp_db, monkeypatch):
    conn = history._get_conn()
    now = time.time()
    _seed(conn, now - 40 * 86400, count=4)
    history._last_prune_day = None

    assert history._maybe_auto_prune(now_ts=now) == 4
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0

    _seed(conn, now - 40 * 86400, count=3)
    assert history._maybe_auto_prune(now_ts=now + 60) == 0
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 3

    next_day = ((now // 86400) + 1) * 86400 + 60
    assert history._maybe_auto_prune(now_ts=next_day) == 3
    assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0


def test_auto_prune_uses_env_days(tmp_db, monkeypatch):
    conn = history._get_conn()
    now = time.time()
    _seed(conn, now - 10 * 86400, count=2)
    _seed(conn, now - 3600, count=2)
    monkeypatch.setenv("DASH_HISTORY_DAYS", "7")
    history._last_prune_day = None

    assert history._maybe_auto_prune(now_ts=now) == 2
    remaining = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert remaining == 2


def _iso(ts: float) -> str:
    tz = timezone(timedelta(hours=7))
    return datetime.fromtimestamp(ts, tz=tz).isoformat()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def agent_tree(tmp_path):
    root = tmp_path / "proj"
    log = root / ".agent" / "logs" / "tool-calls.jsonl"
    now = time.time()
    rows = [
        json.dumps({"event": "old_call", "ts": _iso(now - 40 * 86400)},
                   ensure_ascii=False),
        json.dumps({"event": "old_call2", "ts": _iso(now - 35 * 86400)},
                   ensure_ascii=False),
        json.dumps({"event": "bad_row_no_ts", "detail": "x"}, ensure_ascii=False),
        "this is not json {",
        json.dumps({"event": "new_call", "ts": _iso(now - 86400)},
                   ensure_ascii=False),
    ]
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return {"root": root, "log": log, "now": now}


def test_retention_dry_run_leaves_files_untouched(agent_tree):
    log = agent_tree["log"]
    before = _hash(log)
    result = retention.run(agent_tree["root"], days=30, dry_run=True)

    assert result["mode"] == "dry-run"
    assert result["totals"]["archived"] == 2
    assert result["totals"]["unparseable"] == 2
    assert result["files"][0]["archive"] is not None
    assert _hash(log) == before
    assert not (agent_tree["root"] / ".agent" / "archive").exists()


def test_retention_archives_old_rows_and_rewrites(agent_tree):
    root, log = agent_tree["root"], agent_tree["log"]
    result = retention.run(root, days=30, dry_run=False)

    assert result["mode"] == "write"
    assert result["totals"]["archived"] == 2

    stamp = time.strftime("%Y%m%d")
    archive = root / ".agent" / "archive" / f"tool-calls-{stamp}.jsonl"
    assert archive.is_file()
    archived = [json.loads(line) for line in archive.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    assert [r["event"] for r in archived] == ["old_call", "old_call2"]

    kept_lines = log.read_text(encoding="utf-8").splitlines()
    events = []
    bad = 0
    for line in kept_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        events.append(obj.get("event") or obj.get("detail"))
    assert bad == 1
    assert events == ["bad_row_no_ts", "new_call"]


def test_retention_accepts_epoch_and_ms_timestamps(tmp_path):
    log = tmp_path / ".agent" / "events.jsonl"
    now = time.time()
    rows = [
        json.dumps({"event": "epoch_old", "ts": int(now - 60 * 86400)}),
        json.dumps({"event": "ms_old", "ts": int((now - 50 * 86400) * 1000)}),
        json.dumps({"event": "epoch_new", "ts": int(now - 3600)}),
    ]
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")

    result = retention.run(tmp_path, days=30, dry_run=False)
    assert result["totals"]["archived"] == 2
    kept = log.read_text(encoding="utf-8")
    assert "epoch_new" in kept
    assert "epoch_old" not in kept
    assert "ms_old" not in kept


def test_retention_skips_archive_dir(tmp_path):
    agent = tmp_path / ".agent"
    archive = agent / "archive" / f"old-{time.strftime('%Y%m%d')}.jsonl"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(json.dumps({"ts": 0}) + "\n", encoding="utf-8")

    collected = list(retention.collect_jsonl(agent))
    assert collected == []
    assert archive.is_file()


def test_retention_cli_dry_run_flag(capsys, agent_tree):
    code = retention._main(["--root", str(agent_tree["root"]),
                            "--days", "30", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "mode=dry-run" in out
    assert "tool-calls.jsonl" in out
    assert "archived=2" in out
