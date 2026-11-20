"""Tests for Internet Insights storage layer."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from internet_insights.storage.database import InternetInsightsDB
from internet_insights.storage.migrations import apply_migrations, get_current_version
from internet_insights.storage.repositories import (
    QualitySample,
    QualitySampleRepository,
    InterfaceSample,
    InterfaceSampleRepository,
    TcpStatsSample,
    TcpStatsRepository,
    DnsProbeSample,
    DnsProbeRepository,
    DiagnosticSession,
    DiagnosticSessionRepository,
    DiagnosticResult,
    DiagnosticResultRepository,
    Incident,
    IncidentRepository,
    IncidentEvidence,
    IncidentEvidenceRepository,
    generate_session_id,
    generate_incident_id,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> InternetInsightsDB:
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_internet_insights.db"
    db = InternetInsightsDB(db_path)
    yield db
    db.close()


@pytest.fixture
def quality_repo(temp_db: InternetInsightsDB) -> QualitySampleRepository:
    return QualitySampleRepository(temp_db)


@pytest.fixture
def interface_repo(temp_db: InternetInsightsDB) -> InterfaceSampleRepository:
    return InterfaceSampleRepository(temp_db)


@pytest.fixture
def tcp_repo(temp_db: InternetInsightsDB) -> TcpStatsRepository:
    return TcpStatsRepository(temp_db)


@pytest.fixture
def dns_repo(temp_db: InternetInsightsDB) -> DnsProbeRepository:
    return DnsProbeRepository(temp_db)


@pytest.fixture
def session_repo(temp_db: InternetInsightsDB) -> DiagnosticSessionRepository:
    return DiagnosticSessionRepository(temp_db)


@pytest.fixture
def result_repo(temp_db: InternetInsightsDB) -> DiagnosticResultRepository:
    return DiagnosticResultRepository(temp_db)


@pytest.fixture
def incident_repo(temp_db: InternetInsightsDB) -> IncidentRepository:
    return IncidentRepository(temp_db)


@pytest.fixture
def evidence_repo(temp_db: InternetInsightsDB) -> IncidentEvidenceRepository:
    return IncidentEvidenceRepository(temp_db)


class TestMigrations:
    def test_apply_migrations_creates_all_tables(self, temp_db: InternetInsightsDB):
        conn = temp_db._get_conn()
        version = apply_migrations(conn)
        assert version == 1

        # Verify all tables exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'internet_%'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        expected = {
            "internet_quality_samples",
            "internet_interface_samples",
            "internet_tcp_stats_samples",
            "internet_dns_probe_samples",
            "internet_diagnostic_sessions",
            "internet_diagnostic_results",
            "internet_incidents",
            "internet_incident_evidence",
            "internet_insights_schema_version",
        }
        assert expected.issubset(table_names)

    def test_migration_idempotent(self, temp_db: InternetInsightsDB):
        conn = temp_db._get_conn()
        apply_migrations(conn)
        version1 = get_current_version(conn)
        apply_migrations(conn)  # Run again
        version2 = get_current_version(conn)
        assert version1 == version2 == 1

    def test_version_table_has_correct_value(self, temp_db: InternetInsightsDB):
        conn = temp_db._get_conn()
        apply_migrations(conn)
        row = conn.execute("SELECT version FROM internet_insights_schema_version").fetchone()
        assert row[0] == 1


class TestQualitySampleRepository:
    def test_insert_and_get_latest(self, quality_repo: QualitySampleRepository):
        sample = QualitySample(
            ts=time.time(),
            target_id="primary",
            probe_type="tcp",
            rtt_ms=18.4,
            status="success",
            error_code=None,
            timeout_ms=2000,
            interface_id="Ethernet0",
        )
        quality_repo.insert(sample)
        latest = quality_repo.get_latest("primary")
        assert latest is not None
        assert latest.target_id == "primary"
        assert latest.rtt_ms == 18.4
        assert latest.status == "success"

    def test_insert_batch(self, quality_repo: QualitySampleRepository):
        samples = [
            QualitySample(
                ts=time.time() + i,
                target_id="primary",
                probe_type="tcp",
                rtt_ms=10.0 + i,
                status="success",
                error_code=None,
                timeout_ms=2000,
                interface_id="Ethernet0",
            )
            for i in range(5)
        ]
        count = quality_repo.insert_batch(samples)
        assert count == 5

    def test_query_range(self, quality_repo: QualitySampleRepository):
        now = time.time()
        samples = [
            QualitySample(
                ts=now - 100 + i * 10,
                target_id="primary",
                probe_type="tcp",
                rtt_ms=10.0 + i,
                status="success",
                error_code=None,
                timeout_ms=2000,
                interface_id="Ethernet0",
            )
            for i in range(10)
        ]
        quality_repo.insert_batch(samples)

        results = quality_repo.query_range("primary", now - 200, now, limit=100)
        assert len(results) == 10

    def test_prune(self, quality_repo: QualitySampleRepository):
        now = time.time()
        samples = [
            QualitySample(
                ts=now - 86400 * 20,  # 20 days ago
                target_id="primary",
                probe_type="tcp",
                rtt_ms=10.0,
                status="success",
                error_code=None,
                timeout_ms=2000,
                interface_id="Ethernet0",
            ),
            QualitySample(
                ts=now - 86400 * 5,  # 5 days ago
                target_id="primary",
                probe_type="tcp",
                rtt_ms=10.0,
                status="success",
                error_code=None,
                timeout_ms=2000,
                interface_id="Ethernet0",
            ),
        ]
        quality_repo.insert_batch(samples)

        # Prune older than 14 days
        cutoff = now - 86400 * 14
        deleted = quality_repo.prune(cutoff)
        assert deleted == 1

        remaining = quality_repo.query_range("primary", 0, now, limit=100)
        assert len(remaining) == 1
        assert remaining[0].ts > cutoff


class TestInterfaceSampleRepository:
    def test_insert_and_get_latest(self, interface_repo: InterfaceSampleRepository):
        sample = InterfaceSample(
            ts=time.time(),
            interface_id="Ethernet0",
            bytes_sent=1000000,
            bytes_recv=2000000,
            send_bps=1250000,
            recv_bps=5200000,
            packets_sent=1000,
            packets_recv=2000,
            errors_in=0,
            errors_out=0,
            discards_in=0,
            discards_out=0,
            link_status="up",
        )
        interface_repo.insert(sample)
        latest = interface_repo.get_latest("Ethernet0")
        assert latest is not None
        assert latest.interface_id == "Ethernet0"
        assert latest.link_status == "up"

    def test_get_all_latest(self, interface_repo: InterfaceSampleRepository):
        now = time.time()
        samples = [
            InterfaceSample(
                ts=now - 10,
                interface_id="Ethernet0",
                bytes_sent=1000000,
                bytes_recv=2000000,
                send_bps=1250000,
                recv_bps=5200000,
                packets_sent=1000,
                packets_recv=2000,
                errors_in=0,
                errors_out=0,
                discards_in=0,
                discards_out=0,
                link_status="up",
            ),
            InterfaceSample(
                ts=now,
                interface_id="Wi-Fi",
                bytes_sent=500000,
                bytes_recv=1000000,
                send_bps=500000,
                recv_bps=1000000,
                packets_sent=500,
                packets_recv=1000,
                errors_in=1,
                errors_out=0,
                discards_in=0,
                discards_out=0,
                link_status="up",
            ),
        ]
        interface_repo.insert_batch(samples)

        all_latest = interface_repo.get_all_latest()
        assert len(all_latest) == 2
        ids = {s.interface_id for s in all_latest}
        assert ids == {"Ethernet0", "Wi-Fi"}


class TestTcpStatsRepository:
    def test_insert_and_get_latest(self, tcp_repo: TcpStatsRepository):
        sample = TcpStatsSample(
            ts=time.time(),
            active_opens=1250,
            passive_opens=890,
            failed_attempts=12,
            established_resets=5,
            current_established=42,
            segments_sent=1500000,
            segments_received=1450000,
            segments_retransmitted=3400,
            source="GetTcpStatisticsEx",
        )
        tcp_repo.insert(sample)
        latest = tcp_repo.get_latest()
        assert latest is not None
        assert latest.source == "GetTcpStatisticsEx"
        assert latest.current_established == 42


class TestDnsProbeRepository:
    def test_insert_and_query(self, dns_repo: DnsProbeRepository):
        sample = DnsProbeSample(
            ts=time.time(),
            resolver="1.1.1.1",
            hostname="cloudflare.com",
            record_type="A",
            duration_ms=12.3,
            status="success",
            answer_count=1,
            error_code=None,
            probe_method="system_resolver",
        )
        dns_repo.insert(sample)
        results = dns_repo.query_range("1.1.1.1", time.time() - 3600, time.time(), limit=10)
        assert len(results) == 1
        assert results[0].hostname == "cloudflare.com"


class TestDiagnosticSessionRepository:
    def test_create_and_get(self, session_repo: DiagnosticSessionRepository):
        session = DiagnosticSession(
            id=generate_session_id(),
            started_at=time.time(),
            completed_at=None,
            status="running",
            target="1.1.1.1",
            diagnostic_type="ping",
            config_json='{"count": 10}',
            summary_json=None,
            error=None,
        )
        session_repo.create(session)
        retrieved = session_repo.get(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        assert retrieved.status == "running"

    def test_update(self, session_repo: DiagnosticSessionRepository):
        session = DiagnosticSession(
            id=generate_session_id(),
            started_at=time.time(),
            completed_at=None,
            status="running",
            target="1.1.1.1",
            diagnostic_type="ping",
            config_json='{"count": 10}',
            summary_json=None,
            error=None,
        )
        session_repo.create(session)

        session.completed_at = time.time()
        session.status = "completed"
        session.summary_json = '{"loss_pct": 0}'
        session_repo.update(session)

        retrieved = session_repo.get(session.id)
        assert retrieved.status == "completed"
        assert retrieved.summary_json == '{"loss_pct": 0}'


class TestDiagnosticResultRepository:
    def test_insert_batch_and_get_by_session(self, result_repo: DiagnosticResultRepository, session_repo: DiagnosticSessionRepository):
        session_id = generate_session_id()
        session = DiagnosticSession(
            id=session_id,
            started_at=time.time(),
            completed_at=None,
            status="running",
            target="1.1.1.1",
            diagnostic_type="ping",
            config_json='{}',
            summary_json=None,
            error=None,
        )
        session_repo.create(session)

        results = [
            DiagnosticResult(
                id=0,
                session_id=session_id,
                ts=time.time(),
                sequence=i,
                result_type="probe",
                payload_json=f'{{"seq": {i}, "rtt_ms": 18.4}}',
            )
            for i in range(5)
        ]
        result_repo.insert_batch(results)

        retrieved = result_repo.get_by_session(session_id)
        assert len(retrieved) == 5
        assert retrieved[0].sequence == 0
        assert retrieved[4].sequence == 4


class TestIncidentRepository:
    def test_create_and_list(self, incident_repo: IncidentRepository):
        incident = Incident(
            id=generate_incident_id(),
            started_at=time.time(),
            ended_at=None,
            category="latency",
            severity="warning",
            status="active",
            title="High latency detected",
            summary="Median latency rose from 18ms to 85ms",
            confidence=0.82,
            analyzer_version="1.0.0",
        )
        incident_repo.create(incident)

        incidents = incident_repo.list_incidents(status="active")
        assert len(incidents) == 1
        assert incidents[0].title == "High latency detected"

    def test_update_incident(self, incident_repo: IncidentRepository):
        incident = Incident(
            id=generate_incident_id(),
            started_at=time.time(),
            ended_at=None,
            category="latency",
            severity="warning",
            status="active",
            title="High latency detected",
            summary="Median latency rose from 18ms to 85ms",
            confidence=0.82,
            analyzer_version="1.0.0",
        )
        incident_repo.create(incident)

        incident.ended_at = time.time()
        incident.status = "resolved"
        incident_repo.update(incident)

        retrieved = incident_repo.get(incident.id)
        assert retrieved.status == "resolved"
        assert retrieved.ended_at is not None


class TestIncidentEvidenceRepository:
    def test_insert_batch_and_get_by_incident(self, evidence_repo: IncidentEvidenceRepository, incident_repo: IncidentRepository):
        incident = Incident(
            id=generate_incident_id(),
            started_at=time.time(),
            ended_at=None,
            category="latency",
            severity="warning",
            status="active",
            title="High latency detected",
            summary="Test",
            confidence=0.82,
            analyzer_version="1.0.0",
        )
        incident_repo.create(incident)

        evidence = [
            IncidentEvidence(
                id=0,
                incident_id=incident.id,
                evidence_type="quality_sample",
                observed_at=time.time(),
                payload_json='{"target_id": "primary", "median_rtt_ms": 85.2}',
            ),
            IncidentEvidence(
                id=0,
                incident_id=incident.id,
                evidence_type="quality_sample",
                observed_at=time.time() + 10,
                payload_json='{"target_id": "primary", "median_rtt_ms": 87.1}',
            ),
        ]
        evidence_repo.insert_batch(evidence)

        retrieved = evidence_repo.get_by_incident(incident.id)
        assert len(retrieved) == 2
        assert retrieved[0].evidence_type == "quality_sample"


class TestUtilities:
    def test_generate_session_id(self):
        id1 = generate_session_id()
        id2 = generate_session_id()
        assert id1.startswith("sess_")
        assert id2.startswith("sess_")
        assert id1 != id2

    def test_generate_incident_id(self):
        id1 = generate_incident_id()
        id2 = generate_incident_id()
        assert id1.startswith("inc_")
        assert id2.startswith("inc_")
        assert id1 != id2
