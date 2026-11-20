"""Repository classes for Internet Insights tables."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from .database import InternetInsightsDB, get_db

logger = logging.getLogger("dashboard.internet_insights.storage.repositories")


@dataclass
class QualitySample:
    ts: float
    target_id: str
    probe_type: str
    rtt_ms: float | None
    status: str
    error_code: str | None
    timeout_ms: int | None
    interface_id: str | None


@dataclass
class InterfaceSample:
    ts: float
    interface_id: str
    bytes_sent: int
    bytes_recv: int
    send_bps: float
    recv_bps: float
    packets_sent: int
    packets_recv: int
    errors_in: int
    errors_out: int
    discards_in: int
    discards_out: int
    link_status: str | None


@dataclass
class TcpStatsSample:
    ts: float
    active_opens: int
    passive_opens: int
    failed_attempts: int
    established_resets: int
    current_established: int
    segments_sent: int
    segments_received: int
    segments_retransmitted: int
    source: str


@dataclass
class DnsProbeSample:
    ts: float
    resolver: str
    hostname: str
    record_type: str
    duration_ms: float | None
    status: str
    answer_count: int
    error_code: str | None
    probe_method: str


@dataclass
class RouteSample:
    ts: float
    destination: str
    prefix_length: int
    next_hop: str | None
    interface_index: int
    metric: int
    protocol: int
    age: int
    origin: int
    is_default: int


@dataclass
class TracerouteSample:
    ts: float
    destination: str
    hop: int
    address: str | None
    rtt_ms: float | None
    status: str


@dataclass
class DiagnosticSession:
    id: str
    started_at: float
    completed_at: float | None
    status: str
    target: str | None
    diagnostic_type: str
    config_json: str
    summary_json: str | None
    error: str | None


@dataclass
class DiagnosticResult:
    id: int
    session_id: str
    ts: float
    sequence: int
    result_type: str
    payload_json: str


@dataclass
class Incident:
    id: str
    started_at: float
    ended_at: float | None
    category: str
    severity: str
    status: str
    title: str
    summary: str | None
    confidence: float
    analyzer_version: str


@dataclass
class IncidentEvidence:
    id: int
    incident_id: str
    evidence_type: str
    observed_at: float
    payload_json: str


class QualitySampleRepository:
    """Repository for internet_quality_samples table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert(self, sample: QualitySample) -> int:
        """Insert a single quality sample."""
        cursor = self.db.execute(
            """
            INSERT INTO internet_quality_samples
            (ts, target_id, probe_type, rtt_ms, status, error_code, timeout_ms, interface_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample.ts,
                sample.target_id,
                sample.probe_type,
                sample.rtt_ms,
                sample.status,
                sample.error_code,
                sample.timeout_ms,
                sample.interface_id,
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def insert_batch(self, samples: list[QualitySample]) -> int:
        """Insert multiple quality samples."""
        if not samples:
            return 0
        params = [
            (
                s.ts,
                s.target_id,
                s.probe_type,
                s.rtt_ms,
                s.status,
                s.error_code,
                s.timeout_ms,
                s.interface_id,
            )
            for s in samples
        ]
        self.db.executemany(
            """
            INSERT INTO internet_quality_samples
            (ts, target_id, probe_type, rtt_ms, status, error_code, timeout_ms, interface_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        self.db.commit()
        return len(samples)

    def query_range(self, target_id: str, since: float, until: float | None = None, limit: int = 1000) -> list[QualitySample]:
        """Query samples for a target within time range."""
        if until is None:
            until = time.time()
        rows = self.db.fetchall(
            """
            SELECT ts, target_id, probe_type, rtt_ms, status, error_code, timeout_ms, interface_id
            FROM internet_quality_samples
            WHERE target_id = ? AND ts >= ? AND ts <= ?
            ORDER BY ts DESC LIMIT ?
            """,
            (target_id, since, until, limit),
        )
        return [
            QualitySample(
                ts=r[0],
                target_id=r[1],
                probe_type=r[2],
                rtt_ms=r[3],
                status=r[4],
                error_code=r[5],
                timeout_ms=r[6],
                interface_id=r[7],
            )
            for r in rows
        ]

    def get_latest(self, target_id: str, probe_type: str | None = None) -> QualitySample | None:
        """Get the latest sample for a target."""
        if probe_type:
            row = self.db.fetchone(
                """
                SELECT ts, target_id, probe_type, rtt_ms, status, error_code, timeout_ms, interface_id
                FROM internet_quality_samples
                WHERE target_id = ? AND probe_type = ?
                ORDER BY ts DESC LIMIT 1
                """,
                (target_id, probe_type),
            )
        else:
            row = self.db.fetchone(
                """
                SELECT ts, target_id, probe_type, rtt_ms, status, error_code, timeout_ms, interface_id
                FROM internet_quality_samples
                WHERE target_id = ?
                ORDER BY ts DESC LIMIT 1
                """,
                (target_id,),
            )
        if not row:
            return None
        return QualitySample(
            ts=row[0],
            target_id=row[1],
            probe_type=row[2],
            rtt_ms=row[3],
            status=row[4],
            error_code=row[5],
            timeout_ms=row[6],
            interface_id=row[7],
        )

    def prune(self, cutoff_ts: float) -> int:
        """Delete samples older than cutoff."""
        cursor = self.db.execute(
            "DELETE FROM internet_quality_samples WHERE ts < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class InterfaceSampleRepository:
    """Repository for internet_interface_samples table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert(self, sample: InterfaceSample) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO internet_interface_samples
            (ts, interface_id, bytes_sent, bytes_recv, send_bps, recv_bps,
             packets_sent, packets_recv, errors_in, errors_out, discards_in, discards_out, link_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample.ts,
                sample.interface_id,
                sample.bytes_sent,
                sample.bytes_recv,
                sample.send_bps,
                sample.recv_bps,
                sample.packets_sent,
                sample.packets_recv,
                sample.errors_in,
                sample.errors_out,
                sample.discards_in,
                sample.discards_out,
                sample.link_status,
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def insert_batch(self, samples: list[InterfaceSample]) -> int:
        if not samples:
            return 0
        params = [
            (
                s.ts,
                s.interface_id,
                s.bytes_sent,
                s.bytes_recv,
                s.send_bps,
                s.recv_bps,
                s.packets_sent,
                s.packets_recv,
                s.errors_in,
                s.errors_out,
                s.discards_in,
                s.discards_out,
                s.link_status,
            )
            for s in samples
        ]
        self.db.executemany(
            """
            INSERT INTO internet_interface_samples
            (ts, interface_id, bytes_sent, bytes_recv, send_bps, recv_bps,
             packets_sent, packets_recv, errors_in, errors_out, discards_in, discards_out, link_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        self.db.commit()
        return len(samples)

    def query_range(self, interface_id: str, since: float, until: float | None = None, limit: int = 1000) -> list[InterfaceSample]:
        if until is None:
            until = time.time()
        rows = self.db.fetchall(
            """
            SELECT ts, interface_id, bytes_sent, bytes_recv, send_bps, recv_bps,
                   packets_sent, packets_recv, errors_in, errors_out, discards_in, discards_out, link_status
            FROM internet_interface_samples
            WHERE interface_id = ? AND ts >= ? AND ts <= ?
            ORDER BY ts DESC LIMIT ?
            """,
            (interface_id, since, until, limit),
        )
        return [
            InterfaceSample(
                ts=r[0],
                interface_id=r[1],
                bytes_sent=r[2],
                bytes_recv=r[3],
                send_bps=r[4],
                recv_bps=r[5],
                packets_sent=r[6],
                packets_recv=r[7],
                errors_in=r[8],
                errors_out=r[9],
                discards_in=r[10],
                discards_out=r[11],
                link_status=r[12],
            )
            for r in rows
        ]

    def get_latest(self, interface_id: str) -> InterfaceSample | None:
        row = self.db.fetchone(
            """
            SELECT ts, interface_id, bytes_sent, bytes_recv, send_bps, recv_bps,
                   packets_sent, packets_recv, errors_in, errors_out, discards_in, discards_out, link_status
            FROM internet_interface_samples
            WHERE interface_id = ?
            ORDER BY ts DESC LIMIT 1
            """,
            (interface_id,),
        )
        if not row:
            return None
        return InterfaceSample(
            ts=row[0],
            interface_id=row[1],
            bytes_sent=row[2],
            bytes_recv=row[3],
            send_bps=row[4],
            recv_bps=row[5],
            packets_sent=row[6],
            packets_recv=row[7],
            errors_in=row[8],
            errors_out=row[9],
            discards_in=row[10],
            discards_out=row[11],
            link_status=row[12],
        )

    def get_all_latest(self) -> list[InterfaceSample]:
        """Get latest sample for each interface."""
        rows = self.db.fetchall(
            """
            SELECT ts, interface_id, bytes_sent, bytes_recv, send_bps, recv_bps,
                   packets_sent, packets_recv, errors_in, errors_out, discards_in, discards_out, link_status
            FROM internet_interface_samples
            WHERE ts IN (
                SELECT MAX(ts) FROM internet_interface_samples GROUP BY interface_id
            )
            ORDER BY interface_id
            """,
        )
        return [
            InterfaceSample(
                ts=r[0],
                interface_id=r[1],
                bytes_sent=r[2],
                bytes_recv=r[3],
                send_bps=r[4],
                recv_bps=r[5],
                packets_sent=r[6],
                packets_recv=r[7],
                errors_in=r[8],
                errors_out=r[9],
                discards_in=r[10],
                discards_out=r[11],
                link_status=r[12],
            )
            for r in rows
        ]

    def prune(self, cutoff_ts: float) -> int:
        cursor = self.db.execute(
            "DELETE FROM internet_interface_samples WHERE ts < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class TcpStatsRepository:
    """Repository for internet_tcp_stats_samples table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert(self, sample: TcpStatsSample) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO internet_tcp_stats_samples
            (ts, active_opens, passive_opens, failed_attempts, established_resets,
             current_established, segments_sent, segments_received, segments_retransmitted, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample.ts,
                sample.active_opens,
                sample.passive_opens,
                sample.failed_attempts,
                sample.established_resets,
                sample.current_established,
                sample.segments_sent,
                sample.segments_received,
                sample.segments_retransmitted,
                sample.source,
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def query_range(self, since: float, until: float | None = None, limit: int = 1000) -> list[TcpStatsSample]:
        if until is None:
            until = time.time()
        rows = self.db.fetchall(
            """
            SELECT ts, active_opens, passive_opens, failed_attempts, established_resets,
                   current_established, segments_sent, segments_received, segments_retransmitted, source
            FROM internet_tcp_stats_samples
            WHERE ts >= ? AND ts <= ?
            ORDER BY ts DESC LIMIT ?
            """,
            (since, until, limit),
        )
        return [
            TcpStatsSample(
                ts=r[0],
                active_opens=r[1],
                passive_opens=r[2],
                failed_attempts=r[3],
                established_resets=r[4],
                current_established=r[5],
                segments_sent=r[6],
                segments_received=r[7],
                segments_retransmitted=r[8],
                source=r[9],
            )
            for r in rows
        ]

    def get_latest(self) -> TcpStatsSample | None:
        row = self.db.fetchone(
            """
            SELECT ts, active_opens, passive_opens, failed_attempts, established_resets,
                   current_established, segments_sent, segments_received, segments_retransmitted, source
            FROM internet_tcp_stats_samples
            ORDER BY ts DESC LIMIT 1
            """,
        )
        if not row:
            return None
        return TcpStatsSample(
            ts=row[0],
            active_opens=row[1],
            passive_opens=row[2],
            failed_attempts=row[3],
            established_resets=row[4],
            current_established=row[5],
            segments_sent=row[6],
            segments_received=row[7],
            segments_retransmitted=row[8],
            source=row[9],
        )

    def prune(self, cutoff_ts: float) -> int:
        cursor = self.db.execute(
            "DELETE FROM internet_tcp_stats_samples WHERE ts < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class DnsProbeRepository:
    """Repository for internet_dns_probe_samples table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert(self, sample: DnsProbeSample) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO internet_dns_probe_samples
            (ts, resolver, hostname, record_type, duration_ms, status, answer_count, error_code, probe_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample.ts,
                sample.resolver,
                sample.hostname,
                sample.record_type,
                sample.duration_ms,
                sample.status,
                sample.answer_count,
                sample.error_code,
                sample.probe_method,
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def insert_batch(self, samples: list[DnsProbeSample]) -> int:
        if not samples:
            return 0
        params = [
            (
                s.ts,
                s.resolver,
                s.hostname,
                s.record_type,
                s.duration_ms,
                s.status,
                s.answer_count,
                s.error_code,
                s.probe_method,
            )
            for s in samples
        ]
        self.db.executemany(
            """
            INSERT INTO internet_dns_probe_samples
            (ts, resolver, hostname, record_type, duration_ms, status, answer_count, error_code, probe_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        self.db.commit()
        return len(samples)

    def query_range(self, resolver: str, since: float, until: float | None = None, limit: int = 1000) -> list[DnsProbeSample]:
        if until is None:
            until = time.time()
        rows = self.db.fetchall(
            """
            SELECT ts, resolver, hostname, record_type, duration_ms, status, answer_count, error_code, probe_method
            FROM internet_dns_probe_samples
            WHERE resolver = ? AND ts >= ? AND ts <= ?
            ORDER BY ts DESC LIMIT ?
            """,
            (resolver, since, until, limit),
        )
        return [
            DnsProbeSample(
                ts=r[0],
                resolver=r[1],
                hostname=r[2],
                record_type=r[3],
                duration_ms=r[4],
                status=r[5],
                answer_count=r[6],
                error_code=r[7],
                probe_method=r[8],
            )
            for r in rows
        ]

    def prune(self, cutoff_ts: float) -> int:
        cursor = self.db.execute(
            "DELETE FROM internet_dns_probe_samples WHERE ts < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class RouteSampleRepository:
    """Repository for internet_route_samples table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert(self, sample: RouteSample) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO internet_route_samples
            (ts, destination, prefix_length, next_hop, interface_index, metric, protocol, age, origin, is_default)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample.ts,
                sample.destination,
                sample.prefix_length,
                sample.next_hop,
                sample.interface_index,
                sample.metric,
                sample.protocol,
                sample.age,
                sample.origin,
                sample.is_default,
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def insert_batch(self, samples: list[RouteSample]) -> int:
        if not samples:
            return 0
        params = [
            (
                s.ts,
                s.destination,
                s.prefix_length,
                s.next_hop,
                s.interface_index,
                s.metric,
                s.protocol,
                s.age,
                s.origin,
                s.is_default,
            )
            for s in samples
        ]
        self.db.executemany(
            """
            INSERT INTO internet_route_samples
            (ts, destination, prefix_length, next_hop, interface_index, metric, protocol, age, origin, is_default)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        self.db.commit()
        return len(samples)

    def query_range(self, since: float, until: float | None = None, limit: int = 1000) -> list[RouteSample]:
        if until is None:
            until = time.time()
        rows = self.db.fetchall(
            """
            SELECT ts, destination, prefix_length, next_hop, interface_index, metric, protocol, age, origin, is_default
            FROM internet_route_samples
            WHERE ts >= ? AND ts <= ?
            ORDER BY ts DESC LIMIT ?
            """,
            (since, until, limit),
        )
        return [
            RouteSample(
                ts=r[0],
                destination=r[1],
                prefix_length=r[2],
                next_hop=r[3],
                interface_index=r[4],
                metric=r[5],
                protocol=r[6],
                age=r[7],
                origin=r[8],
                is_default=r[9],
            )
            for r in rows
        ]

    def get_latest_snapshot(self) -> list[RouteSample]:
        """Get the most recent route snapshot (all routes from latest timestamp)."""
        rows = self.db.fetchall(
            """
            SELECT ts, destination, prefix_length, next_hop, interface_index, metric, protocol, age, origin, is_default
            FROM internet_route_samples
            WHERE ts = (SELECT MAX(ts) FROM internet_route_samples)
            ORDER BY is_default DESC, metric ASC
            """,
        )
        return [
            RouteSample(
                ts=r[0],
                destination=r[1],
                prefix_length=r[2],
                next_hop=r[3],
                interface_index=r[4],
                metric=r[5],
                protocol=r[6],
                age=r[7],
                origin=r[8],
                is_default=r[9],
            )
            for r in rows
        ]

    def prune(self, cutoff_ts: float) -> int:
        cursor = self.db.execute(
            "DELETE FROM internet_route_samples WHERE ts < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class TracerouteSampleRepository:
    """Repository for internet_traceroute_samples table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert(self, sample: TracerouteSample) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO internet_traceroute_samples
            (ts, destination, hop, address, rtt_ms, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                sample.ts,
                sample.destination,
                sample.hop,
                sample.address,
                sample.rtt_ms,
                sample.status,
            ),
        )
        self.db.commit()
        return cursor.lastrowid

    def insert_batch(self, samples: list[TracerouteSample]) -> int:
        if not samples:
            return 0
        params = [
            (
                s.ts,
                s.destination,
                s.hop,
                s.address,
                s.rtt_ms,
                s.status,
            )
            for s in samples
        ]
        self.db.executemany(
            """
            INSERT INTO internet_traceroute_samples
            (ts, destination, hop, address, rtt_ms, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        self.db.commit()
        return len(samples)

    def query_range(self, destination: str, since: float, until: float | None = None, limit: int = 1000) -> list[TracerouteSample]:
        if until is None:
            until = time.time()
        rows = self.db.fetchall(
            """
            SELECT ts, destination, hop, address, rtt_ms, status
            FROM internet_traceroute_samples
            WHERE destination = ? AND ts >= ? AND ts <= ?
            ORDER BY ts DESC, hop ASC LIMIT ?
            """,
            (destination, since, until, limit),
        )
        return [
            TracerouteSample(
                ts=r[0],
                destination=r[1],
                hop=r[2],
                address=r[3],
                rtt_ms=r[4],
                status=r[5],
            )
            for r in rows
        ]

    def get_latest_traceroute(self, destination: str) -> list[TracerouteSample]:
        """Get the most recent traceroute for a destination."""
        rows = self.db.fetchall(
            """
            SELECT ts, destination, hop, address, rtt_ms, status
            FROM internet_traceroute_samples
            WHERE destination = ? AND ts = (SELECT MAX(ts) FROM internet_traceroute_samples WHERE destination = ?)
            ORDER BY hop ASC
            """,
            (destination, destination),
        )
        return [
            TracerouteSample(
                ts=r[0],
                destination=r[1],
                hop=r[2],
                address=r[3],
                rtt_ms=r[4],
                status=r[5],
            )
            for r in rows
        ]

    def prune(self, cutoff_ts: float) -> int:
        cursor = self.db.execute(
            "DELETE FROM internet_traceroute_samples WHERE ts < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class DiagnosticSessionRepository:
    """Repository for internet_diagnostic_sessions table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def create(self, session: DiagnosticSession) -> str:
        self.db.execute(
            """
            INSERT INTO internet_diagnostic_sessions
            (id, started_at, completed_at, status, target, diagnostic_type, config_json, summary_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.started_at,
                session.completed_at,
                session.status,
                session.target,
                session.diagnostic_type,
                session.config_json,
                session.summary_json,
                session.error,
            ),
        )
        self.db.commit()
        return session.id

    def update(self, session: DiagnosticSession) -> None:
        self.db.execute(
            """
            UPDATE internet_diagnostic_sessions
            SET completed_at = ?, status = ?, summary_json = ?, error = ?
            WHERE id = ?
            """,
            (
                session.completed_at,
                session.status,
                session.summary_json,
                session.error,
                session.id,
            ),
        )
        self.db.commit()

    def get(self, session_id: str) -> DiagnosticSession | None:
        row = self.db.fetchone(
            """
            SELECT id, started_at, completed_at, status, target, diagnostic_type, config_json, summary_json, error
            FROM internet_diagnostic_sessions
            WHERE id = ?
            """,
            (session_id,),
        )
        if not row:
            return None
        return DiagnosticSession(
            id=row[0],
            started_at=row[1],
            completed_at=row[2],
            status=row[3],
            target=row[4],
            diagnostic_type=row[5],
            config_json=row[6],
            summary_json=row[7],
            error=row[8],
        )

    def list_sessions(self, status: str | None = None, limit: int = 50) -> list[DiagnosticSession]:
        if status:
            rows = self.db.fetchall(
                """
                SELECT id, started_at, completed_at, status, target, diagnostic_type, config_json, summary_json, error
                FROM internet_diagnostic_sessions
                WHERE status = ?
                ORDER BY started_at DESC LIMIT ?
                """,
                (status, limit),
            )
        else:
            rows = self.db.fetchall(
                """
                SELECT id, started_at, completed_at, status, target, diagnostic_type, config_json, summary_json, error
                FROM internet_diagnostic_sessions
                ORDER BY started_at DESC LIMIT ?
                """,
                (limit,),
            )
        return [
            DiagnosticSession(
                id=r[0],
                started_at=r[1],
                completed_at=r[2],
                status=r[3],
                target=r[4],
                diagnostic_type=r[5],
                config_json=r[6],
                summary_json=r[7],
                error=r[8],
            )
            for r in rows
        ]

    def prune(self, cutoff_ts: float) -> int:
        cursor = self.db.execute(
            "DELETE FROM internet_diagnostic_sessions WHERE started_at < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class DiagnosticResultRepository:
    """Repository for internet_diagnostic_results table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert_batch(self, results: list[DiagnosticResult]) -> int:
        if not results:
            return 0
        params = [
            (r.session_id, r.ts, r.sequence, r.result_type, r.payload_json)
            for r in results
        ]
        self.db.executemany(
            """
            INSERT INTO internet_diagnostic_results
            (session_id, ts, sequence, result_type, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            params,
        )
        self.db.commit()
        return len(results)

    def get_by_session(self, session_id: str) -> list[DiagnosticResult]:
        rows = self.db.fetchall(
            """
            SELECT id, session_id, ts, sequence, result_type, payload_json
            FROM internet_diagnostic_results
            WHERE session_id = ?
            ORDER BY sequence
            """,
            (session_id,),
        )
        return [
            DiagnosticResult(
                id=r[0],
                session_id=r[1],
                ts=r[2],
                sequence=r[3],
                result_type=r[4],
                payload_json=r[5],
            )
            for r in rows
        ]


class IncidentRepository:
    """Repository for internet_incidents table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def create(self, incident: Incident) -> str:
        self.db.execute(
            """
            INSERT INTO internet_incidents
            (id, started_at, ended_at, category, severity, status, title, summary, confidence, analyzer_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident.id,
                incident.started_at,
                incident.ended_at,
                incident.category,
                incident.severity,
                incident.status,
                incident.title,
                incident.summary,
                incident.confidence,
                incident.analyzer_version,
            ),
        )
        self.db.commit()
        return incident.id

    def update(self, incident: Incident) -> None:
        self.db.execute(
            """
            UPDATE internet_incidents
            SET ended_at = ?, status = ?, title = ?, summary = ?, confidence = ?
            WHERE id = ?
            """,
            (
                incident.ended_at,
                incident.status,
                incident.title,
                incident.summary,
                incident.confidence,
                incident.id,
            ),
        )
        self.db.commit()

    def get(self, incident_id: str) -> Incident | None:
        row = self.db.fetchone(
            """
            SELECT id, started_at, ended_at, category, severity, status, title, summary, confidence, analyzer_version
            FROM internet_incidents
            WHERE id = ?
            """,
            (incident_id,),
        )
        if not row:
            return None
        return Incident(
            id=row[0],
            started_at=row[1],
            ended_at=row[2],
            category=row[3],
            severity=row[4],
            status=row[5],
            title=row[6],
            summary=row[7],
            confidence=row[8],
            analyzer_version=row[9],
        )

    def list_incidents(
        self,
        status: str | None = None,
        category: str | None = None,
        since: float | None = None,
        limit: int = 50,
    ) -> list[Incident]:
        conditions = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if since:
            conditions.append("started_at >= ?")
            params.append(since)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(limit)

        rows = self.db.fetchall(
            f"""
            SELECT id, started_at, ended_at, category, severity, status, title, summary, confidence, analyzer_version
            FROM internet_incidents
            {where}
            ORDER BY started_at DESC LIMIT ?
            """,
            tuple(params),
        )
        return [
            Incident(
                id=r[0],
                started_at=r[1],
                ended_at=r[2],
                category=r[3],
                severity=r[4],
                status=r[5],
                title=r[6],
                summary=r[7],
                confidence=r[8],
                analyzer_version=r[9],
            )
            for r in rows
        ]

    def prune(self, cutoff_ts: float) -> int:
        cursor = self.db.execute(
            "DELETE FROM internet_incidents WHERE started_at < ?",
            (cutoff_ts,),
        )
        self.db.commit()
        return cursor.rowcount


class IncidentEvidenceRepository:
    """Repository for internet_incident_evidence table."""

    def __init__(self, db: InternetInsightsDB | None = None):
        self.db = db or get_db()

    def insert_batch(self, evidence_list: list[IncidentEvidence]) -> int:
        if not evidence_list:
            return 0
        params = [
            (e.incident_id, e.evidence_type, e.observed_at, e.payload_json)
            for e in evidence_list
        ]
        self.db.executemany(
            """
            INSERT INTO internet_incident_evidence
            (incident_id, evidence_type, observed_at, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            params,
        )
        self.db.commit()
        return len(evidence_list)

    def get_by_incident(self, incident_id: str) -> list[IncidentEvidence]:
        rows = self.db.fetchall(
            """
            SELECT id, incident_id, evidence_type, observed_at, payload_json
            FROM internet_incident_evidence
            WHERE incident_id = ?
            ORDER BY observed_at
            """,
            (incident_id,),
        )
        return [
            IncidentEvidence(
                id=r[0],
                incident_id=r[1],
                evidence_type=r[2],
                observed_at=r[3],
                payload_json=r[4],
            )
            for r in rows
        ]


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"sess_{uuid.uuid4().hex[:12]}"


def generate_incident_id() -> str:
    """Generate a unique incident ID."""
    return f"inc_{uuid.uuid4().hex[:12]}"
