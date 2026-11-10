"""Tests for the scheduled security audit (FEAT-422).

Covers:
  - schedule defaults + validation (interval bounds, non-numeric input)
  - maybe_run gating (disabled / due / not-yet-due) without sleeping
  - run_and_store persistence, detail shape, in-flight lock and off-loop audit
  - the REST surface: GET/PUT schedule, POST run-now (admin + CSRF), GET audits
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import config
import main
from security import audit as audit_mod
from security import persistence, scheduled

DETAIL_KEYS = {"riskscore", "risk_label", "findings_count", "critical_count",
               "duration_ms", "top_findings"}

ADMIN_HEADERS = {"X-Admin-Token": "secret"}
CSRF_HEADERS = {"X-Requested-With": "windy-dashboard"}


def _report(findings: list[dict] | None = None) -> dict:
    items = findings if findings is not None else []
    return {
        "generated_at": "2026-01-01T00:00:00",
        "duration_ms": 12.0,
        "riskscore": sum(f["weight"] for f in items),
        "risk_label": "Medium",
        "findings": items,
        "data": {},
    }


def _finding(title: str, weight: int, severity: str = "medium") -> dict:
    return {"id": title.lower().replace(" ", "_"), "category": "test", "title": title,
            "description": "", "weight": weight, "severity": severity, "data": {}}


def _ts(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


@pytest.fixture()
def audit_env(tmp_path, monkeypatch):
    """Isolate the schedule file and the history DB, then reset module state."""
    monkeypatch.setattr(scheduled, "SCHEDULE_PATH", tmp_path / "audit_schedule.json")
    monkeypatch.setattr(config, "HISTORY_DB", tmp_path / "history.db")
    persistence.close()
    scheduled.reset_state()
    yield tmp_path
    persistence.close()
    scheduled.reset_state()


@pytest.fixture()
def client():
    return TestClient(main.app)


# ---- schedule defaults + validation ---- #

def test_default_schedule_is_disabled(audit_env):
    assert scheduled.get_schedule() == {"enabled": False, "intervalHours": 24.0}


@pytest.mark.parametrize("bad_interval", [0, 0.1, 999, "x", None, True])
def test_set_schedule_rejects_bad_interval(audit_env, bad_interval):
    with pytest.raises(ValueError):
        scheduled.set_schedule({"enabled": True, "intervalHours": bad_interval})


def test_set_schedule_rejects_non_bool_enabled(audit_env):
    with pytest.raises(ValueError):
        scheduled.set_schedule({"enabled": "yes", "intervalHours": 2})


def test_set_schedule_roundtrip_and_persist(audit_env):
    saved = scheduled.set_schedule({"enabled": True, "intervalHours": 1.5})
    assert saved == {"enabled": True, "intervalHours": 1.5}
    assert scheduled.get_schedule() == saved
    raw = json.loads(scheduled.SCHEDULE_PATH.read_text(encoding="utf-8"))
    assert raw == saved

    scheduled.reset_state()
    assert scheduled.get_schedule() == saved


def test_put_schedule_invalid_returns_400(client, audit_env):
    r = client.put("/api/security/audit/schedule", json={"enabled": True, "intervalHours": 0})
    assert r.status_code == 400


# ---- maybe_run gating ---- #

def test_maybe_run_disabled_returns_none_without_auditing(audit_env, monkeypatch):
    calls: list[int] = []

    async def fake_run_audit(suspicious_override=None):
        calls.append(1)
        return _report()

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)
    assert asyncio.run(scheduled.maybe_run(1000.0)) is None
    assert calls == []
    assert scheduled.get_next_due() is None


def test_maybe_run_respects_interval(audit_env, monkeypatch):
    calls: list[int] = []

    async def fake_run_audit(suspicious_override=None):
        calls.append(1)
        return _report()

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)
    scheduled.set_schedule({"enabled": True, "intervalHours": 1.0})

    first = asyncio.run(scheduled.maybe_run(1000.0))
    assert first is not None
    assert len(calls) == 1
    assert scheduled.get_next_due() == 1000.0 + 3600.0
    assert scheduled.get_last_run() == "2026-01-01T00:00:00"

    assert asyncio.run(scheduled.maybe_run(1000.0 + 1800.0)) is None
    assert len(calls) == 1

    second = asyncio.run(scheduled.maybe_run(1000.0 + 3601.0))
    assert second is not None
    assert len(calls) == 2
    assert scheduled.get_next_due() == 1000.0 + 3601.0 + 3600.0


# ---- run_and_store ---- #

def test_run_and_store_persists_summary(audit_env, monkeypatch):
    findings = [
        _finding("Low thing", 5, "low"),
        _finding("Critical thing", 40, "critical"),
        _finding("Medium thing", 15, "medium"),
        _finding("Another low", 3, "low"),
    ]

    async def fake_run_audit(suspicious_override=None):
        return _report(findings)

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)
    persistence.record_event("port_opened", "1.2.3.4", {"port": 22}, ts="2026-01-01T00:00:01")

    summary = asyncio.run(scheduled.run_and_store(suspicious_override=["RU"]))

    assert set(summary) >= DETAIL_KEYS
    assert summary["riskscore"] == 63
    assert summary["findings_count"] == 4
    assert summary["critical_count"] == 1
    assert summary["top_findings"] == ["Critical thing", "Medium thing", "Low thing"]
    assert summary["stored"] is True

    audits = persistence.list_events(kind="scheduled_audit")
    assert len(audits) == 1
    assert audits[0]["kind"] == "scheduled_audit"
    assert audits[0]["source_ip"] == "127.0.0.1"
    assert set(audits[0]["detail"]) >= DETAIL_KEYS
    assert audits[0]["detail"]["top_findings"] == summary["top_findings"]

    assert len(persistence.list_events()) == 2


# ---- API ---- #

def test_get_schedule_endpoint(client, audit_env):
    r = client.get("/api/security/audit/schedule")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["enabled"] is False
    assert body["intervalHours"] == 24.0
    assert body["last_run"] is None
    assert body["next_due"] is None


def test_put_schedule_endpoint(client, audit_env):
    r = client.put("/api/security/audit/schedule",
                   json={"enabled": True, "intervalHours": 6})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["enabled"] is True
    assert body["intervalHours"] == 6.0
    assert scheduled.get_schedule() == {"enabled": True, "intervalHours": 6.0}


def test_run_now_endpoint(client, audit_env, monkeypatch):
    async def fake_run_audit(suspicious_override=None):
        return _report([_finding("Critical thing", 40, "critical")])

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    r = client.post("/api/security/audit/schedule/run",
                    headers={**ADMIN_HEADERS, **CSRF_HEADERS})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["findings_count"] == 1
    assert body["critical_count"] == 1
    assert len(persistence.list_events(kind="scheduled_audit")) == 1


def test_run_endpoint_requires_admin(client, audit_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    r = client.post("/api/security/audit/schedule/run", headers=CSRF_HEADERS)
    assert r.status_code == 401


def test_run_endpoint_requires_csrf_header(client, audit_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    r = client.post("/api/security/audit/schedule/run", headers=ADMIN_HEADERS)
    assert r.status_code == 403
    assert r.json()["detail"] == "missing_origin_header"


def test_audits_endpoint_filters_kind(client, audit_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    persistence.record_event("scheduled_audit", "127.0.0.1",
                             {"riskscore": 10, "risk_label": "Low"}, ts="2026-01-01T00:00:01")
    persistence.record_event("port_opened", "0.0.0.0", {"port": 8080}, ts="2026-01-01T00:00:02")

    r = client.get("/api/security/audits?limit=20", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["audits"]) == 1
    assert body["audits"][0]["kind"] == "scheduled_audit"
    assert body["audits"][0]["detail"]["riskscore"] == 10


def test_audits_endpoint_requires_admin(client, audit_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    assert client.get("/api/security/audits").status_code == 401


def test_audits_endpoint_limit_validation(client, audit_env, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    assert client.get("/api/security/audits?limit=0", headers=ADMIN_HEADERS).status_code == 422
    assert client.get("/api/security/audits?limit=500", headers=ADMIN_HEADERS).status_code == 422


# ---- concurrency + scheduling edge cases ---- #

def test_run_and_store_skips_when_in_flight(audit_env, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    async def slow_run_audit(suspicious_override=None):
        started.set()
        await asyncio.to_thread(release.wait, 5.0)
        return _report([_finding("Slow thing", 4, "low")])

    monkeypatch.setattr(audit_mod, "run_audit", slow_run_audit)

    async def scenario():
        first = asyncio.create_task(scheduled.run_and_store())
        assert await asyncio.to_thread(started.wait, 5.0)
        second = await scheduled.run_and_store()
        release.set()
        return await first, second

    first, second = asyncio.run(scenario())

    assert second == {"ok": True, "skipped": "in_flight"}
    assert first["findings_count"] == 1
    assert len(persistence.list_events(kind="scheduled_audit")) == 1


def test_run_and_store_audits_off_the_event_loop(audit_env, monkeypatch):
    main_thread = threading.get_ident()
    observed: dict[str, int] = {}

    async def fake_run_audit(suspicious_override=None):
        observed["thread"] = threading.get_ident()
        await asyncio.sleep(0.2)
        return _report()

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)

    async def scenario():
        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(5):
                await asyncio.sleep(0.01)
                ticks += 1

        task = asyncio.create_task(scheduled.run_and_store())
        await ticker()
        summary = await task
        return summary, ticks

    summary, ticks = asyncio.run(scenario())

    assert observed["thread"] != main_thread
    assert ticks == 5
    assert summary["riskscore"] == 0


def test_maybe_run_retries_soon_after_failure(audit_env, monkeypatch):
    async def boom(suspicious_override=None):
        raise RuntimeError("wmi exploded")

    monkeypatch.setattr(audit_mod, "run_audit", boom)
    scheduled.set_schedule({"enabled": True, "intervalHours": 24})

    with pytest.raises(RuntimeError):
        asyncio.run(scheduled.maybe_run(1000.0))

    assert scheduled.get_next_due() == 1000.0 + scheduled.RETRY_DELAY


def test_set_schedule_keeps_next_due_in_future(audit_env):
    last_run = (datetime.now() - timedelta(minutes=10)).isoformat()
    persistence.record_event("scheduled_audit", "127.0.0.1",
                             {"riskscore": 1}, ts=last_run)
    scheduled.reset_state()
    last_run_ts = _ts(last_run)

    scheduled.set_schedule({"enabled": True, "intervalHours": 1.0})

    due = scheduled.get_next_due()
    assert due is not None
    assert due > time.time()
    assert due == pytest.approx(last_run_ts + 3600, abs=5)


def test_restart_does_not_rerun_immediately(audit_env, monkeypatch):
    now = time.time()
    scheduled.SCHEDULE_PATH.write_text(
        json.dumps({"enabled": True, "intervalHours": 2.0}), encoding="utf-8",
    )
    persistence.record_event(
        "scheduled_audit", "127.0.0.1", {"riskscore": 3},
        ts=(datetime.now() - timedelta(seconds=60)).isoformat(),
    )

    calls: list[int] = []

    async def fake_run_audit(suspicious_override=None):
        calls.append(1)
        return _report()

    monkeypatch.setattr(audit_mod, "run_audit", fake_run_audit)
    scheduled.reset_state()

    due = scheduled.get_next_due()
    assert due is not None
    assert due >= now
    assert asyncio.run(scheduled.maybe_run(now)) is None
    assert calls == []


def test_list_events_kind_filter_is_backward_compatible(audit_env):
    persistence.record_event("scheduled_audit", "127.0.0.1", {"n": 1}, ts="2026-01-01T00:00:01")
    persistence.record_event("failed_login", "1.2.3.4", {"n": 2}, ts="2026-01-01T00:00:02")
    assert len(persistence.list_events()) == 2
    assert len(persistence.list_events(kind="failed_login")) == 1
    assert len(persistence.list_events(limit=5, kind="scheduled_audit")) == 1


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
