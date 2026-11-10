"""Tests for the editable report schedule (FEAT-404).

Covers:
  - defaults with no file and no env
  - env fallback (DASH_REPORT_INTERVAL_HOURS: 0 disables, 6 = 6h)
  - corrupt/unreadable schedule file -> env fallback without raising
  - payload validation for enabled/intervalHours/days
  - GET/PUT /api/reports/schedule (admin gate, CSRF, 400/500 mapping)
  - nextRun computed from intervalHours (also before the loop sets it)
  - _report_tick() decisions with a fake clock
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

import config
import main
import reports


@pytest.fixture()
def schedule_env(tmp_path, monkeypatch):
    """Isolate the persisted schedule file and reset scheduler state."""
    path = tmp_path / "report_schedule.json"
    monkeypatch.setattr(reports, "SCHEDULE_PATH", path)
    monkeypatch.delenv("DASH_REPORT_INTERVAL_HOURS", raising=False)
    reports.set_next_due(None)
    yield path
    reports.set_next_due(None)


@pytest.fixture()
def client():
    return TestClient(main.app)


def _auth() -> dict[str, str]:
    return {"X-Admin-Token": "secret"}


def _write_auth() -> dict[str, str]:
    return {"X-Admin-Token": "secret", "X-Requested-With": "windy-dashboard"}


def _valid_payload(**overrides) -> dict:
    payload = {"enabled": True, "intervalHours": 24, "days": 1}
    payload.update(overrides)
    return payload


def test_default_schedule_without_file_or_env(schedule_env):
    assert not schedule_env.exists()

    schedule = reports.get_schedule()

    assert schedule == {"enabled": True, "intervalHours": 24.0, "days": 1}
    assert not schedule_env.exists()


def test_env_zero_disables_schedule(schedule_env, monkeypatch):
    monkeypatch.setenv("DASH_REPORT_INTERVAL_HOURS", "0")

    schedule = reports.get_schedule()

    assert schedule["enabled"] is False
    assert schedule["days"] == 1


def test_env_interval_is_used(schedule_env, monkeypatch):
    monkeypatch.setenv("DASH_REPORT_INTERVAL_HOURS", "6")

    schedule = reports.get_schedule()

    assert schedule == {"enabled": True, "intervalHours": 6.0, "days": 1}


def test_corrupt_file_falls_back_to_defaults(schedule_env):
    schedule_env.write_text("{not json", encoding="utf-8")

    schedule = reports.get_schedule()

    assert schedule == {"enabled": True, "intervalHours": 24.0, "days": 1}


def test_corrupt_file_still_honours_env(schedule_env, monkeypatch):
    schedule_env.write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("DASH_REPORT_INTERVAL_HOURS", "6")

    assert reports.get_schedule()["intervalHours"] == 6.0


def test_unreadable_file_still_honours_env(schedule_env, monkeypatch):
    monkeypatch.setenv("DASH_REPORT_INTERVAL_HOURS", "6")

    def boom(*args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(reports.Path, "read_text", boom)

    assert reports.get_schedule()["intervalHours"] == 6.0


def test_invalid_stored_fields_fall_back_to_defaults(schedule_env):
    schedule_env.write_text(json.dumps({"enabled": "yes", "intervalHours": 5}), encoding="utf-8")

    assert reports.get_schedule() == {"enabled": True, "intervalHours": 24.0, "days": 1}


@pytest.mark.parametrize("interval", [0, 0.1, 200, "x", None, True, float("nan"), float("inf")])
def test_rejects_bad_interval(schedule_env, interval):
    with pytest.raises(ValueError):
        reports.set_schedule({"enabled": True, "intervalHours": interval, "days": 1})


@pytest.mark.parametrize("days", [2, 0, 30, "7", True, 1.5, None])
def test_rejects_bad_days(schedule_env, days):
    with pytest.raises(ValueError):
        reports.set_schedule({"enabled": True, "intervalHours": 24, "days": days})


@pytest.mark.parametrize("enabled", ["yes", 1, 0, None])
def test_rejects_bad_enabled(schedule_env, enabled):
    with pytest.raises(ValueError):
        reports.set_schedule({"enabled": enabled, "intervalHours": 24, "days": 1})


def test_set_schedule_persists_normalized_values(schedule_env):
    schedule = reports.set_schedule({"enabled": True, "intervalHours": 6, "days": 7})

    assert schedule == {"enabled": True, "intervalHours": 6.0, "days": 7}
    stored = json.loads(schedule_env.read_text(encoding="utf-8"))
    assert stored == {"enabled": True, "intervalHours": 6.0, "days": 7}
    assert reports.get_schedule() == schedule


def test_set_schedule_rejects_non_object(schedule_env):
    with pytest.raises(ValueError):
        reports.set_schedule(["nope"])


def test_set_schedule_write_failure_raises_schedule_write_error(schedule_env, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(reports.Path, "write_text", boom)

    with pytest.raises(reports.ScheduleWriteError):
        reports.set_schedule(_valid_payload())


def test_schedule_endpoints_require_admin(client, schedule_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    assert client.get("/api/reports/schedule").status_code == 401
    assert client.put("/api/reports/schedule", json=_valid_payload()).status_code == 401


def test_put_schedule_requires_csrf_header(client, schedule_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    missing = client.put("/api/reports/schedule", json=_valid_payload(), headers=_auth())
    wrong = client.put(
        "/api/reports/schedule",
        json=_valid_payload(),
        headers={**_auth(), "X-Requested-With": "nope"},
    )

    assert missing.status_code == 403
    assert missing.json()["detail"] == "missing_origin_header"
    assert wrong.status_code == 403
    assert not schedule_env.exists()


@pytest.mark.parametrize("payload", [
    {"enabled": True, "intervalHours": 0, "days": 1},
    {"enabled": True, "intervalHours": 200, "days": 1},
    {"enabled": True, "intervalHours": "x", "days": 1},
    {"enabled": True, "intervalHours": 24, "days": 2},
    {"enabled": "yes", "intervalHours": 24, "days": 1},
])
def test_put_schedule_rejects_bad_payload(client, schedule_env, monkeypatch, payload):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    r = client.put("/api/reports/schedule", json=payload, headers=_write_auth())

    assert r.status_code == 400
    assert not schedule_env.exists()


def test_put_schedule_write_failure_is_500(client, schedule_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(reports.Path, "write_text", boom)

    r = client.put("/api/reports/schedule", json=_valid_payload(), headers=_write_auth())

    assert r.status_code == 500
    assert r.json()["detail"] == "schedule_not_persisted"


def test_put_schedule_persists_and_get_returns_it(client, schedule_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")

    r = client.put(
        "/api/reports/schedule",
        json={"enabled": True, "intervalHours": 6, "days": 7},
        headers=_write_auth(),
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["enabled"] is True
    assert body["intervalHours"] == 6.0
    assert body["days"] == 7

    fetched = client.get("/api/reports/schedule", headers=_auth())
    assert fetched.status_code == 200
    payload = fetched.json()
    assert payload["ok"] is True
    assert payload["enabled"] is True
    assert payload["intervalHours"] == 6.0
    assert payload["days"] == 7


def test_put_schedule_sets_next_run_from_interval(client, schedule_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    before = time.time()

    body = client.put(
        "/api/reports/schedule",
        json={"enabled": True, "intervalHours": 6, "days": 1},
        headers=_write_auth(),
    ).json()

    assert isinstance(body["nextRun"], (int, float))
    expected = before + 6 * 3600.0
    assert expected - 5 <= body["nextRun"] <= time.time() + 6 * 3600.0 + 5
    assert reports.get_next_due() == body["nextRun"]


def test_put_schedule_disabled_clears_next_run(client, schedule_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    reports.set_next_due(time.time() + 3600)

    body = client.put(
        "/api/reports/schedule",
        json={"enabled": False, "intervalHours": 24, "days": 1},
        headers=_write_auth(),
    ).json()

    assert body["enabled"] is False
    assert body["nextRun"] is None
    assert reports.get_next_due() is None


def test_get_schedule_computes_next_run_when_state_is_empty(client, schedule_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    reports.set_next_due(None)
    before = time.time()

    body = client.get("/api/reports/schedule", headers=_auth()).json()

    assert body["enabled"] is True
    assert isinstance(body["nextRun"], (int, float))
    assert body["nextRun"] > before
    assert body["nextRun"] >= before + body["intervalHours"] * 3600.0 - 5
    assert reports.get_next_due() is None


def _run_tick(monkeypatch, now, schedule, due, generate_raises=False):
    """Run one scheduler tick with faked schedule/state side effects."""
    calls = {"generate": [], "prune": [], "next_due": []}
    monkeypatch.setattr(reports, "get_schedule", lambda: dict(schedule))
    monkeypatch.setattr(reports, "get_next_due", lambda: due)
    monkeypatch.setattr(reports, "set_next_due", calls["next_due"].append)
    monkeypatch.setattr(reports, "prune_reports", lambda keep=reports.DEFAULT_KEEP:
                        calls["prune"].append(keep))

    def fake_generate(days=1):
        calls["generate"].append(days)
        if generate_raises:
            raise RuntimeError("generation failed")
        return "report.html"

    monkeypatch.setattr(reports, "generate_report", fake_generate)

    asyncio.run(main._report_tick(now))
    return calls


def test_tick_disabled_clears_next_due_without_generating(schedule_env, monkeypatch):
    calls = _run_tick(
        monkeypatch,
        now=1_000.0,
        schedule={"enabled": False, "intervalHours": 24.0, "days": 1},
        due=1_000.0,
    )

    assert calls["next_due"] == [None]
    assert calls["generate"] == []
    assert calls["prune"] == []


def test_tick_sets_first_due_without_generating(schedule_env, monkeypatch):
    calls = _run_tick(
        monkeypatch,
        now=1_000.0,
        schedule={"enabled": True, "intervalHours": 6.0, "days": 1},
        due=None,
    )

    assert calls["next_due"] == [1_000.0 + 6 * 3600.0]
    assert calls["generate"] == []


def test_tick_waits_when_not_due(schedule_env, monkeypatch):
    calls = _run_tick(
        monkeypatch,
        now=1_000.0,
        schedule={"enabled": True, "intervalHours": 6.0, "days": 1},
        due=2_000.0,
    )

    assert calls["next_due"] == []
    assert calls["generate"] == []


def test_tick_generates_when_due(schedule_env, monkeypatch):
    calls = _run_tick(
        monkeypatch,
        now=10_000.0,
        schedule={"enabled": True, "intervalHours": 6.0, "days": 7},
        due=9_000.0,
    )

    assert calls["generate"] == [7]
    assert calls["prune"] == [reports.DEFAULT_KEEP]
    assert calls["next_due"] == [10_000.0 + 6 * 3600.0]


def test_tick_generation_failure_retries_in_300s(schedule_env, monkeypatch):
    calls = _run_tick(
        monkeypatch,
        now=10_000.0,
        schedule={"enabled": True, "intervalHours": 6.0, "days": 1},
        due=9_000.0,
        generate_raises=True,
    )

    assert calls["generate"] == [1]
    assert calls["next_due"] == [10_000.0 + 300.0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
