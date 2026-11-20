"""Tests for the bounded diagnostic session manager."""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from internet_insights.config import InternetInsightsConfig
from internet_insights.services import session_manager as session_manager_module
from internet_insights.services.session_manager import (
    SessionLimitError,
    SessionManager,
    get_session_manager,
)
from internet_insights.storage.database import InternetInsightsDB
from internet_insights.storage.repositories import (
    DiagnosticResult,
    DiagnosticResultRepository,
    DiagnosticSession,
    DiagnosticSessionRepository,
    TcpStatsRepository,
)

FAST_PROFILES = {"quick": 0.5, "standard": 0.5, "deep": 0.5}


@pytest.fixture
def temp_db(tmp_path: Path) -> InternetInsightsDB:
    db = InternetInsightsDB(tmp_path / "test_session_manager.db")
    yield db
    db.close()


@pytest.fixture
def repos(temp_db: InternetInsightsDB):
    return (
        DiagnosticSessionRepository(temp_db),
        DiagnosticResultRepository(temp_db),
        TcpStatsRepository(temp_db),
    )


@pytest.fixture
def fake_dns(monkeypatch):
    def _fake_getaddrinfo(host, port=None, family=0, type=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)


def _fake_ping_adapter(rtt: float | None = 12.5, delay: float = 0.0):
    adapter = MagicMock()

    async def _ping(target, timeout=None):
        if delay:
            await asyncio.sleep(delay)
        return rtt

    adapter.ping = _ping
    return adapter


def _fake_metrics_adapter(gateway: str = "192.0.2.1") -> MagicMock:
    adapter = MagicMock()
    adapter.get_network_snapshot.return_value = {
        "adapters": [{"name": "eth0", "gateway": [gateway], "dns": ["1.1.1.1"]}],
    }
    return adapter


def _fake_speedtest_factory(calls: list[float] | None = None):
    class _FakeSpeedtest:
        def run(self) -> dict:
            if calls is not None:
                calls.append(time.time())
            return {"status": "success", "download_mbps": 100.0, "upload_mbps": 50.0}

    return _FakeSpeedtest


def _make_manager(
    repos,
    *,
    config: InternetInsightsConfig | None = None,
    profile_durations: dict[str, float] | None = None,
    ping_adapter=None,
    speedtest_factory=None,
) -> SessionManager:
    session_repo, result_repo, tcp_stats_repo = repos
    return SessionManager(
        config=config or InternetInsightsConfig(),
        session_repo=session_repo,
        result_repo=result_repo,
        tcp_stats_repo=tcp_stats_repo,
        ping_adapter=ping_adapter or _fake_ping_adapter(),
        metrics_adapter=_fake_metrics_adapter(),
        profile_durations=profile_durations or dict(FAST_PROFILES),
        speedtest_factory=speedtest_factory,
    )


async def _wait_for_terminal(manager: SessionManager, session_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = manager.get_session(session_id)
        if last is not None and last["status"] != "running":
            return last
        await asyncio.sleep(0.05)
    raise AssertionError(f"Session {session_id} did not reach a terminal state (last={last})")


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_happy_path_quick_completes(self, repos, fake_dns):
        manager = _make_manager(repos)
        info = await manager.start_session(profile="quick")
        assert info["status"] == "running"
        assert info["profile"] == "quick"
        session = await _wait_for_terminal(manager, info["id"])
        assert session["status"] == "completed"
        assert session["completed_at"] is not None
        summary = session["summary"]
        assert isinstance(summary, dict)
        assert summary["profile"] == "quick"
        step_names = {step["step"] for step in summary["steps"]}
        assert {"adapter_snapshot", "gateway_probes", "endpoint_probes", "report"} <= step_names

    @pytest.mark.asyncio
    async def test_results_rows_persisted_and_parseable(self, repos, fake_dns):
        manager = _make_manager(repos)
        info = await manager.start_session(profile="quick")
        session_id = info["id"]
        await _wait_for_terminal(manager, session_id)
        results = manager.get_results(session_id)
        assert len(results) > 0
        sequences = [row["sequence"] for row in results]
        assert sequences == sorted(sequences)
        for row in results:
            assert isinstance(row["payload"], dict)
            assert "step" in row["payload"]
        raw_summary = json.loads(manager.session_repo.get(session_id).summary_json)
        assert raw_summary["status"] == "completed"

    @pytest.mark.asyncio
    async def test_session_duration_bounded_by_profile(self, repos, fake_dns):
        manager = _make_manager(repos, profile_durations={"quick": 1.0}, ping_adapter=_fake_ping_adapter(delay=0.3))
        info = await manager.start_session(profile="quick")
        session = await _wait_for_terminal(manager, info["id"])
        assert session["status"] == "completed"
        elapsed = session["completed_at"] - session["started_at"]
        assert elapsed < 1.0 + 1.5

    @pytest.mark.asyncio
    async def test_cancel_mid_run(self, repos, fake_dns):
        manager = _make_manager(repos, profile_durations={"standard": 5.0}, ping_adapter=_fake_ping_adapter(delay=0.3))
        info = await manager.start_session(profile="standard")
        session_id = info["id"]
        await asyncio.sleep(0.1)
        assert await manager.cancel(session_id) is True
        session = await _wait_for_terminal(manager, session_id)
        assert session["status"] == "cancelled"
        assert session["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_unknown_session_returns_false(self, repos):
        manager = _make_manager(repos)
        assert await manager.cancel("no-such-session") is False

    @pytest.mark.asyncio
    async def test_session_limit_raises(self, repos, fake_dns):
        manager = _make_manager(repos, config=InternetInsightsConfig(diagnostic_concurrency=1))
        blocker = asyncio.create_task(asyncio.sleep(30))
        manager._tasks["phantom-session"] = blocker
        try:
            with pytest.raises(SessionLimitError):
                await manager.start_session(profile="quick")
        finally:
            blocker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await blocker

    @pytest.mark.asyncio
    async def test_unknown_profile_rejected(self, repos):
        manager = _make_manager(repos)
        with pytest.raises(ValueError):
            await manager.start_session(profile="ultra")

    @pytest.mark.asyncio
    async def test_custom_targets_step_uses_tcp_connect(self, repos, fake_dns, monkeypatch):
        tcp_mock = AsyncMock(return_value={"status": "success", "target": "example.com", "port": 443, "duration_ms": 1.0, "error_code": None})
        monkeypatch.setattr(session_manager_module, "tcp_connect", tcp_mock)
        manager = _make_manager(repos)
        info = await manager.start_session(profile="quick", custom_targets=["example.com:443", "1.1.1.1"])
        await _wait_for_terminal(manager, info["id"])
        tcp_rows = [row for row in manager.get_results(info["id"]) if row["result_type"] == "tcp_connect"]
        assert len(tcp_rows) == 2
        assert tcp_rows[0]["payload"]["custom_target"] == "example.com:443"
        assert tcp_rows[0]["payload"]["status"] == "success"
        assert tcp_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_speedtest_runs_only_when_opted_in(self, repos, fake_dns):
        calls: list[float] = []
        manager = _make_manager(repos, speedtest_factory=_fake_speedtest_factory(calls))
        first = await manager.start_session(profile="quick")
        await _wait_for_terminal(manager, first["id"])
        assert calls == []
        second = await manager.start_session(profile="quick", include_speedtest=True)
        await _wait_for_terminal(manager, second["id"])
        assert len(calls) == 1


class TestSessionExport:
    @pytest.fixture
    def seeded(self, repos) -> tuple[SessionManager, str]:
        session_repo, result_repo, _ = repos
        manager = _make_manager(repos)
        session_id = "sess-export-test"
        now = time.time()
        session_repo.create(DiagnosticSession(
            id=session_id,
            started_at=now - 10,
            completed_at=now,
            status="completed",
            target=None,
            diagnostic_type="full_session",
            config_json=json.dumps({"profile": "quick"}),
            summary_json=json.dumps({"profile": "quick", "findings": ["Gateway probe failures: 1/3"]}),
            error=None,
        ))
        result_repo.insert_batch([
            DiagnosticResult(
                id=0,
                session_id=session_id,
                ts=now - 5,
                sequence=1,
                result_type="probe",
                payload_json=json.dumps({
                    "step": "gateway_probes",
                    "headers": "Authorization: Bearer abc123",
                    "url": "https://user:secret@example.com/x",
                }),
            )
        ])
        return manager, session_id

    @pytest.mark.parametrize("fmt", ["json", "csv", "md"])
    def test_export_redacts_secrets(self, seeded, fmt: str):
        manager, session_id = seeded
        _, _, content = manager.export_session(session_id, fmt)
        assert "abc123" not in content
        assert "secret" not in content

    @pytest.mark.parametrize("fmt", ["json", "csv"])
    def test_export_marks_redaction(self, seeded, fmt: str):
        manager, session_id = seeded
        _, _, content = manager.export_session(session_id, fmt)
        assert "[REDACTED]" in content

    def test_export_json_parseable(self, seeded):
        manager, session_id = seeded
        filename, media_type, content = manager.export_session(session_id, "json")
        assert media_type == "application/json"
        assert filename == f"diagnostic-session-{session_id}.json"
        data = json.loads(content)
        assert data["session"]["id"] == session_id
        assert len(data["results"]) == 1

    def test_export_csv_has_header_and_rows(self, seeded):
        manager, session_id = seeded
        _, media_type, content = manager.export_session(session_id, "csv")
        assert media_type == "text/csv"
        lines = [line for line in content.splitlines() if line]
        assert lines[0] == "sequence,ts,result_type,payload"
        assert len(lines) == 2

    def test_export_md_has_heading(self, seeded):
        manager, session_id = seeded
        _, media_type, content = manager.export_session(session_id, "md")
        assert media_type == "text/markdown"
        assert content.startswith("# Diagnostic Session Report")
        assert "## Results" in content

    def test_export_unknown_format_raises(self, seeded):
        manager, session_id = seeded
        with pytest.raises(ValueError):
            manager.export_session(session_id, "xml")

    def test_export_unknown_session_raises(self, seeded):
        manager, _ = seeded
        with pytest.raises(ValueError):
            manager.export_session("no-such-session", "json")


class TestSessionManagerSingleton:
    def test_get_session_manager_returns_singleton(self, temp_db, monkeypatch):
        monkeypatch.setattr("internet_insights.storage.database._db", temp_db)
        manager = get_session_manager()
        assert manager is get_session_manager()
        assert isinstance(manager, SessionManager)
