"""Bounded diagnostic session manager with cancellation and redacted export."""

from __future__ import annotations

import asyncio
import csv
import io
import ipaddress
import json
import logging
import re
import socket
import time
from datetime import UTC, datetime
from typing import Any

import psutil

from ..adapters.ping_adapter import PingAdapter
from ..config import InternetInsightsConfig, get_config
from ..diagnostics import validate_target
from ..diagnostics.http import redact_url
from ..diagnostics.tcp import tcp_connect
from ..storage.repositories import (
    DiagnosticResult,
    DiagnosticResultRepository,
    DiagnosticSession,
    DiagnosticSessionRepository,
    TcpStatsRepository,
    generate_session_id,
)

logger = logging.getLogger("dashboard.internet_insights.services.session_manager")

SESSION_PROFILES: dict[str, float] = {"quick": 30.0, "standard": 60.0, "deep": 120.0}
DEFAULT_PROFILE = "standard"
SPEEDTEST_TIMEOUT_SEC = 30.0
MAX_CUSTOM_TARGETS = 5
MAX_EXPORT_STRING_LENGTH = 4096
SENSITIVE_KEYS = {"authorization", "cookie", "proxy-authorization", "password", "secret", "token"}
SENSITIVE_HEADER_RE = re.compile(
    r"(?i)\b(authorization|cookie|proxy-authorization)\s*:\s*[^\n,\"'}]+"
)


class SessionLimitError(Exception):
    """Raised when the concurrent session limit is reached."""


def _redact_text(text: str) -> str:
    redacted = SENSITIVE_HEADER_RE.sub(lambda m: f"{m.group(1)}: [REDACTED]", text)
    redacted = redact_url(redacted)
    if len(redacted) > MAX_EXPORT_STRING_LENGTH:
        return redacted[:MAX_EXPORT_STRING_LENGTH] + "…[TRUNCATED]"
    return redacted


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else _redact_value(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


class SessionManager:
    """Runs bounded diagnostic sessions with step-level persistence and cancellation."""

    def __init__(
        self,
        config: InternetInsightsConfig | None = None,
        session_repo: DiagnosticSessionRepository | None = None,
        result_repo: DiagnosticResultRepository | None = None,
        tcp_stats_repo: TcpStatsRepository | None = None,
        ping_adapter: PingAdapter | None = None,
        metrics_adapter: Any | None = None,
        profile_durations: dict[str, float] | None = None,
        speedtest_factory: Any | None = None,
    ):
        self.config = config or get_config()
        self.session_repo = session_repo or DiagnosticSessionRepository()
        self.result_repo = result_repo or DiagnosticResultRepository()
        self.tcp_stats_repo = tcp_stats_repo or TcpStatsRepository()
        self.ping_adapter = ping_adapter
        self.metrics_adapter = metrics_adapter
        self.profile_durations = dict(SESSION_PROFILES)
        if profile_durations:
            self.profile_durations.update(profile_durations)
        self.speedtest_factory = speedtest_factory
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    def _get_ping_adapter(self) -> PingAdapter:
        if self.ping_adapter is None:
            self.ping_adapter = PingAdapter()
        return self.ping_adapter

    def _get_metrics_adapter(self) -> Any:
        if self.metrics_adapter is None:
            from ..adapters.metrics_adapter import MetricsAdapter
            self.metrics_adapter = MetricsAdapter()
        return self.metrics_adapter

    def _get_speedtest(self) -> Any:
        if self.speedtest_factory is not None:
            return self.speedtest_factory()
        from ..adapters.speedtest_adapter import SpeedtestAdapter
        return SpeedtestAdapter()

    def duration_for_profile(self, profile: str) -> float:
        """Effective session duration in seconds (profile duration capped by config)."""
        if profile not in self.profile_durations:
            raise ValueError(f"Unknown profile: {profile}. Must be one of {sorted(SESSION_PROFILES)}")
        return min(self.profile_durations[profile], float(self.config.max_session_duration_sec))

    def is_running(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    async def start_session(
        self,
        profile: str = DEFAULT_PROFILE,
        include_speedtest: bool = False,
        custom_targets: list[str] | None = None,
    ) -> dict:
        """Create a session row and schedule the bounded workflow task."""
        duration_sec = self.duration_for_profile(profile)
        cap = max(1, self.config.diagnostic_concurrency)
        running = sum(1 for task in self._tasks.values() if not task.done())
        if running >= cap:
            raise SessionLimitError(f"Maximum concurrent diagnostic sessions reached ({running}/{cap})")

        session_id = generate_session_id()
        config_payload = {
            "profile": profile,
            "duration_sec": duration_sec,
            "include_speedtest": bool(include_speedtest),
            "custom_targets": [str(t) for t in (custom_targets or [])][:MAX_CUSTOM_TARGETS],
        }
        session = DiagnosticSession(
            id=session_id,
            started_at=time.time(),
            completed_at=None,
            status="running",
            target=None,
            diagnostic_type="full_session",
            config_json=json.dumps(config_payload),
            summary_json=None,
            error=None,
        )
        await asyncio.to_thread(self.session_repo.create, session)

        cancel_event = asyncio.Event()
        self._cancel_events[session_id] = cancel_event
        task = asyncio.create_task(
            self._run(session_id, profile, duration_sec, include_speedtest, config_payload["custom_targets"], cancel_event),
            name=f"diagnostic-session-{session_id}",
        )
        self._tasks[session_id] = task
        return {
            "id": session_id,
            "started_at": session.started_at,
            "status": "running",
            "profile": profile,
            "config": config_payload,
        }

    async def cancel(self, session_id: str) -> bool:
        """Request cancellation; stops at the next step boundary. False when not running."""
        session = await asyncio.to_thread(self.session_repo.get, session_id)
        if session is None or session.status != "running":
            return False
        event = self._cancel_events.get(session_id)
        if event is not None:
            event.set()
            return True
        session.status = "cancelled"
        session.completed_at = time.time()
        await asyncio.to_thread(self.session_repo.update, session)
        return True

    def get_session(self, session_id: str) -> dict | None:
        session = self.session_repo.get(session_id)
        if session is None:
            return None
        return self._session_to_dict(session)

    def get_results(self, session_id: str) -> list[dict]:
        return [self._result_to_dict(row) for row in self.result_repo.get_by_session(session_id)]

    def export_session(self, session_id: str, fmt: str) -> tuple[str, str, str]:
        """Export a session as (filename, media_type, content) with redaction applied."""
        if fmt not in ("json", "csv", "md"):
            raise ValueError(f"Unsupported export format: {fmt}. Must be json|csv|md")
        session = self.session_repo.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        session_dict = _redact_value(self._session_to_dict(session))
        results = [_redact_value(self._result_to_dict(row)) for row in self.result_repo.get_by_session(session_id)]
        if fmt == "json":
            content = json.dumps({"session": session_dict, "results": results}, ensure_ascii=False, indent=2)
            media_type = "application/json"
        elif fmt == "csv":
            content = self._export_csv(results)
            media_type = "text/csv"
        else:
            content = self._export_markdown(session_dict, results)
            media_type = "text/markdown"
        return f"diagnostic-session-{session_id}.{fmt}", media_type, content

    def _session_to_dict(self, session: DiagnosticSession) -> dict:
        return {
            "id": session.id,
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "status": session.status,
            "target": session.target,
            "diagnostic_type": session.diagnostic_type,
            "config": self._parse_json(session.config_json),
            "summary": self._parse_json(session.summary_json),
            "error": session.error,
        }

    def _result_to_dict(self, row: DiagnosticResult) -> dict:
        return {
            "id": row.id,
            "ts": row.ts,
            "sequence": row.sequence,
            "result_type": row.result_type,
            "payload": self._parse_json(row.payload_json),
        }

    @staticmethod
    def _parse_json(raw: str | None) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_gateways(snapshot: dict) -> list[str]:
        gateways: list[str] = []
        for adapter in snapshot.get("adapters", []) or []:
            for gw in adapter.get("gateway", []) or []:
                if gw and gw not in gateways:
                    gateways.append(str(gw))
        return gateways

    @staticmethod
    def _parse_custom_target(raw: str) -> tuple[str, int]:
        cleaned = str(raw).strip()
        try:
            ipaddress.ip_address(cleaned)
            return validate_target(cleaned), 443
        except ValueError:
            pass
        host, sep, port_part = cleaned.rpartition(":")
        if sep and host and port_part.isdigit():
            return validate_target(host), int(port_part)
        return validate_target(cleaned), 443

    def _count_connections_by_state(self) -> dict[str, int]:
        counters: dict[str, int] = {}
        for conn in psutil.net_connections(kind="inet"):
            counters[conn.status] = counters.get(conn.status, 0) + 1
        return counters

    async def _run(
        self,
        session_id: str,
        profile: str,
        duration_sec: float,
        include_speedtest: bool,
        custom_targets: list[str],
        cancel_event: asyncio.Event,
    ) -> None:
        start_monotonic = time.monotonic()
        sequence = 0
        steps_meta: list[dict] = []
        summary: dict[str, Any] = {"profile": profile, "steps": steps_meta, "findings": []}
        status = "completed"
        error: str | None = None

        def remaining() -> float:
            return duration_sec - (time.monotonic() - start_monotonic)

        def budget(step_timeout: float) -> float:
            return max(0.05, min(step_timeout, remaining()))

        async def run_step(step_name: str, coro_factory: Any, step_timeout: float, result_type: str = "probe", clamp: bool = True) -> dict:
            nonlocal sequence
            payload: dict[str, Any] = {"step": step_name}
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(coro_factory(), timeout=(budget(step_timeout) if clamp else step_timeout))
                if isinstance(result, dict):
                    payload.update(result)
                else:
                    payload["data"] = result
                payload.setdefault("status", "success")
            except TimeoutError:
                payload["status"] = "timeout"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                payload["status"] = "error"
                payload["error_code"] = type(exc).__name__
                payload["error"] = str(exc)[:200]
            payload["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
            sequence += 1
            row = DiagnosticResult(
                id=0,
                session_id=session_id,
                ts=time.time(),
                sequence=sequence,
                result_type=result_type,
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            )
            try:
                await asyncio.to_thread(self.result_repo.insert_batch, [row])
            except Exception:
                logger.exception("Failed to persist result for step %s", step_name)
            steps_meta.append({
                "step": step_name,
                "status": payload.get("status"),
                "duration_ms": payload["duration_ms"],
            })
            return payload

        try:
            # Step 1: adapter/config snapshot (single metrics_adapter network snapshot call)
            snapshot = await run_step(
                "adapter_snapshot",
                lambda: asyncio.to_thread(self._get_metrics_adapter().get_network_snapshot),
                5.0,
            )
            gateways = self._extract_gateways(snapshot) if snapshot.get("status") == "success" else []
            probe_timeout = self.config.probe_timeout_ms / 1000
            if cancel_event.is_set():
                status = "cancelled"
                return

            # Step 2: gateway ping x3
            if gateways:
                gateway = gateways[0]
                ping_adapter = self._get_ping_adapter()

                async def gateway_probes() -> dict:
                    probes = []
                    for index in range(3):
                        rtt = await ping_adapter.ping(gateway, timeout=probe_timeout)
                        probes.append({"probe_index": index, "rtt_ms": rtt, "status": "success" if rtt is not None else "timeout"})
                    return {"gateway": gateway, "probes": probes}

                gw_payload = await run_step("gateway_probes", gateway_probes, 10.0)
                failures = sum(1 for p in gw_payload.get("probes", []) if p.get("status") != "success")
                if failures:
                    summary["findings"].append(f"Gateway probe failures: {failures}/3")
            else:
                await run_step("gateway_probes", self._unavailable("gateway address unknown"), 1.0)
            if cancel_event.is_set():
                status = "cancelled"
                return

            # Step 3: endpoint probes primary/secondary x3 each
            ping_adapter = self._get_ping_adapter()

            async def endpoint_probes() -> dict:
                probes = []
                for target_id, host in (("primary", self.config.primary_target), ("secondary", self.config.secondary_target)):
                    for index in range(3):
                        rtt = await ping_adapter.ping(host, timeout=probe_timeout)
                        probes.append({
                            "target_id": target_id,
                            "probe_index": index,
                            "rtt_ms": rtt,
                            "status": "success" if rtt is not None else "timeout",
                        })
                return {"probes": probes}

            ep_payload = await run_step("endpoint_probes", endpoint_probes, 15.0)
            endpoint_failures = sum(1 for p in ep_payload.get("probes", []) if p.get("status") != "success")
            if endpoint_failures >= 3:
                summary["findings"].append(f"Endpoint probe failures: {endpoint_failures}/6")
            if cancel_event.is_set():
                status = "cancelled"
                return

            # Step 4: DNS probe via system resolver getaddrinfo
            dns_host = self.config.dns_test_hostnames[0] if self.config.dns_test_hostnames else "example.com"

            async def dns_probe() -> dict:
                start = time.monotonic()
                try:
                    infos = await asyncio.to_thread(
                        socket.getaddrinfo, dns_host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM,
                    )
                except socket.gaierror as exc:
                    return {"hostname": dns_host, "status": "dns_failure", "error": str(exc)}
                return {
                    "hostname": dns_host,
                    "status": "success",
                    "answer_count": len(infos),
                    "resolve_ms": round((time.monotonic() - start) * 1000, 1),
                }

            dns_payload = await run_step("dns_probe", dns_probe, 10.0)
            if dns_payload.get("status") != "success":
                summary["findings"].append(f"DNS probe failed for {dns_host}")
            elif (dns_payload.get("resolve_ms") or 0) > self.config.dns_degradation_threshold_ms:
                summary["findings"].append(f"DNS resolution slow: {dns_payload['resolve_ms']}ms")
            if cancel_event.is_set():
                status = "cancelled"
                return

            # Step 5: TCP stats snapshot (read-only)
            async def tcp_stats() -> dict:
                sample = await asyncio.to_thread(self.tcp_stats_repo.get_latest)
                if sample is None:
                    return {"status": "unavailable"}
                return {
                    "status": "success",
                    "current_established": sample.current_established,
                    "segments_sent": sample.segments_sent,
                    "segments_retransmitted": sample.segments_retransmitted,
                    "source": sample.source,
                }

            await run_step("tcp_stats", tcp_stats, 5.0)
            if cancel_event.is_set():
                status = "cancelled"
                return

            # Step 6: connection snapshot (count by state only, no process details)
            conn_payload = await run_step(
                "connection_snapshot",
                lambda: asyncio.to_thread(self._count_connections_by_state),
                5.0,
            )
            if conn_payload.get("status") != "success":
                summary["findings"].append("Connection snapshot unavailable")
            if cancel_event.is_set():
                status = "cancelled"
                return

            # Step 7: optional custom diagnostics (tcp_connect only)
            for raw_target in custom_targets[:MAX_CUSTOM_TARGETS]:
                if cancel_event.is_set():
                    status = "cancelled"
                    return

                async def custom_probe(raw=raw_target) -> dict:
                    host, port = self._parse_custom_target(raw)
                    result = await tcp_connect(host, port, timeout_ms=self.config.probe_timeout_ms)
                    return {"custom_target": raw, **result}

                custom_payload = await run_step("custom_target", custom_probe, 10.0, result_type="tcp_connect")
                if custom_payload.get("status") != "success":
                    summary["findings"].append(f"Custom target failed: {raw_target}")

            # Step 8: correlate → summary
            status_counts: dict[str, int] = {}
            for meta in steps_meta:
                state = str(meta.get("status"))
                status_counts[state] = status_counts.get(state, 0) + 1
            worst_step = max(steps_meta, key=lambda meta: meta["duration_ms"]) if steps_meta else None
            summary["counts"] = {
                "steps_total": len(steps_meta),
                **{f"steps_{state}": count for state, count in sorted(status_counts.items())},
            }
            summary["worst_step"] = worst_step

            # Step 9: report → summary_json
            summary["report"] = {
                "generated_at": time.time(),
                "profile": profile,
                "duration_budget_sec": duration_sec,
                "findings_count": len(summary["findings"]),
            }
            await run_step(
                "report",
                self._immediate({"status": "success", "findings_count": len(summary["findings"])}),
                1.0,
            )

            # Speed test: explicit opt-in only, after report, own 30s budget, isolated failures
            if include_speedtest:
                await run_step("speedtest", lambda: asyncio.to_thread(self._get_speedtest().run), SPEEDTEST_TIMEOUT_SEC)
        except asyncio.CancelledError:
            status = "cancelled"
        except Exception as exc:
            logger.exception("Diagnostic session %s failed", session_id)
            status = "failed"
            error = str(exc)[:500]
        finally:
            if status == "completed" and remaining() <= 0 and len(steps_meta) > 0:
                summary["findings"].append("Session time budget exhausted before all steps completed")
            summary["status"] = status
            try:
                session = await asyncio.to_thread(self.session_repo.get, session_id)
                if session is not None:
                    session.status = status
                    session.completed_at = time.time()
                    session.summary_json = json.dumps(summary, ensure_ascii=False, default=str)
                    session.error = error
                    await asyncio.to_thread(self.session_repo.update, session)
            except Exception:
                logger.exception("Failed to finalize session %s", session_id)
            self._tasks.pop(session_id, None)
            self._cancel_events.pop(session_id, None)

    @staticmethod
    def _unavailable(reason: str) -> Any:
        async def _payload() -> dict:
            return {"status": "unavailable", "reason": reason}
        return _payload

    @staticmethod
    def _immediate(payload: dict) -> Any:
        async def _payload() -> dict:
            return payload
        return _payload

    @staticmethod
    def _export_csv(results: list[dict]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["sequence", "ts", "result_type", "payload"])
        for row in results:
            writer.writerow([
                row.get("sequence"),
                datetime.fromtimestamp(row["ts"], tz=UTC).isoformat() if row.get("ts") is not None else "",
                row.get("result_type"),
                json.dumps(row.get("payload"), ensure_ascii=False, default=str),
            ])
        return buffer.getvalue()

    @staticmethod
    def _export_markdown(session: dict, results: list[dict]) -> str:
        lines = ["# Diagnostic Session Report", ""]
        lines.append(f"- **Session ID**: {session.get('id')}")
        lines.append(f"- **Status**: {session.get('status')}")
        lines.append(f"- **Type**: {session.get('diagnostic_type')}")
        started_at = session.get("started_at")
        if started_at is not None:
            lines.append(f"- **Started At**: {datetime.fromtimestamp(started_at, tz=UTC).isoformat()}")
        completed_at = session.get("completed_at")
        if completed_at is not None:
            lines.append(f"- **Completed At**: {datetime.fromtimestamp(completed_at, tz=UTC).isoformat()}")
        summary = session.get("summary") or {}
        findings = summary.get("findings") or []
        lines.append("")
        lines.append("## Findings")
        if findings:
            lines.extend(f"- {finding}" for finding in findings)
        else:
            lines.append("- No issues detected")
        lines.append("")
        lines.append("## Results")
        lines.append("")
        lines.append("| # | Time | Type | Step | Status |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in results:
            payload = row.get("payload") or {}
            ts = row.get("ts")
            ts_text = datetime.fromtimestamp(ts, tz=UTC).isoformat(timespec="seconds") if ts is not None else ""
            lines.append(
                f"| {row.get('sequence')} | {ts_text} | {row.get('result_type')} | "
                f"{payload.get('step', '-')} | {payload.get('status', '-')} |"
            )
        if session.get("error"):
            lines.append("")
            lines.append(f"**Error**: {session['error']}")
        lines.append("")
        return "\n".join(lines)


_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
