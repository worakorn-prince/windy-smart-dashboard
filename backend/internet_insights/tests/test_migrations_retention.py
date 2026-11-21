"""Migration compatibility and retention-boundary tests (INET-M6-A).

Covers two production-survival scenarios:
1. A legacy dashboard-shaped database (``samples``/``schema_version`` tables
   with real rows, no internet_insights tables) must migrate cleanly:
   legacy data preserved, internet tables created, version table initialized.
2. ``IncidentManager.prune_retention`` must respect the 14/30/90-day cutoffs:
   rows older than the cutoff are deleted, rows younger are kept.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from internet_insights.storage.database import InternetInsightsDB
from internet_insights.storage.migrations import apply_migrations
from internet_insights.storage.repositories import (
    Incident,
    IncidentEvidence,
    IncidentEvidenceRepository,
    IncidentRepository,
    generate_incident_id,
)
from internet_insights.services.incident_manager import IncidentManager

LEGACY_DASH_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples(
    ts REAL PRIMARY KEY,
    cpu_pct REAL, ram_pct REAL, swap_pct REAL,
    cpu_temp REAL, gpu_temp REAL, disk_temp_max REAL,
    cpu_power_w REAL, gpu_power_w REAL,
    net_sent_bps REAL, net_recv_bps REAL,
    disk_read_bps REAL, disk_write_bps REAL
);
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
"""

LEGACY_ROWS = [
    (1000.0, 12.5, 40.0, 2.0, 45.0, None, None, 3.3, None, 15_000.0, 120_000.0, 900.0, 5_000.0),
    (1001.0, 13.5, 41.0, 2.5, 46.0, None, None, 3.4, None, 16_000.0, 121_000.0, 950.0, 5_100.0),
    (1002.0, 14.5, 42.0, 3.0, 47.0, None, None, 3.5, None, 17_000.0, 122_000.0, 1_000.0, 5_200.0),
]

INTERNET_TABLES = (
    "internet_quality_samples",
    "internet_interface_samples",
    "internet_tcp_stats_samples",
    "internet_dns_probe_samples",
    "internet_diagnostic_sessions",
    "internet_diagnostic_results",
    "internet_incidents",
    "internet_incident_evidence",
    "internet_route_samples",
    "internet_insights_schema_version",
)


def _legacy_db(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "legacy.db")
    conn.executescript(LEGACY_DASH_SCHEMA)
    conn.executemany(
        "INSERT INTO samples(ts, cpu_pct, ram_pct, swap_pct, cpu_temp, gpu_temp, disk_temp_max,"
        " cpu_power_w, gpu_power_w, net_sent_bps, net_recv_bps, disk_read_bps, disk_write_bps)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        LEGACY_ROWS,
    )
    conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (3)")
    conn.commit()
    return conn


def _table_names(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


class TestLegacyMigration:
    def test_legacy_dash_db_migrates_cleanly(self, tmp_path):
        conn = _legacy_db(tmp_path)

        legacy_before = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        assert legacy_before == len(LEGACY_ROWS)
        assert not any(name.startswith("internet_") for name in _table_names(conn))

        new_version = apply_migrations(conn)

        assert new_version >= 1
        names = _table_names(conn)
        for table in ("samples", "schema_version", *INTERNET_TABLES):
            assert table in names, f"missing table after migration: {table}"

        version_row = conn.execute(
            "SELECT MAX(version) FROM internet_insights_schema_version"
        ).fetchone()
        assert version_row is not None and version_row[0] == new_version

        legacy_after = conn.execute(
            "SELECT ts, cpu_pct, net_recv_bps, disk_write_bps FROM samples ORDER BY ts"
        ).fetchall()
        assert legacy_after == [
            (1000.0, 12.5, 120_000.0, 5_000.0),
            (1001.0, 13.5, 121_000.0, 5_100.0),
            (1002.0, 14.5, 122_000.0, 5_200.0),
        ]
        conn.close()

    def test_migrated_legacy_db_usable_by_repositories(self, tmp_path):
        conn = _legacy_db(tmp_path)
        apply_migrations(conn)

        db = InternetInsightsDB(tmp_path / "reuse.db")
        incident_repo = IncidentRepository(db)
        incident_id = incident_repo.create(
            Incident(
                id=generate_incident_id(),
                started_at=1000.0,
                ended_at=None,
                category="latency",
                severity="warning",
                status="active",
                title="post-migration write",
                summary=None,
                confidence=0.5,
                analyzer_version="test",
            )
        )
        assert incident_repo.get(incident_id) is not None
        db.close()
        conn.close()

    def test_apply_migrations_is_idempotent(self, tmp_path):
        conn = _legacy_db(tmp_path)
        first = apply_migrations(conn)
        second = apply_migrations(conn)
        assert first == second
        assert conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == len(LEGACY_ROWS)
        conn.close()


class TestRetentionBoundaries:
    @staticmethod
    def _make_incident(repo: IncidentRepository, started_at: float) -> str:
        return repo.create(
            Incident(
                id=generate_incident_id(),
                started_at=started_at,
                ended_at=None,
                category="latency",
                severity="warning",
                status="active",
                title="retention probe",
                summary=None,
                confidence=0.5,
                analyzer_version="test",
            )
        )

    @staticmethod
    def _add_evidence(repo: IncidentEvidenceRepository, incident_id: str, observed_at: float) -> None:
        repo.insert_batch(
            [
                IncidentEvidence(
                    id=0,
                    incident_id=incident_id,
                    evidence_type="quality_sample",
                    observed_at=observed_at,
                    payload_json="{}",
                )
            ]
        )

    @pytest.mark.parametrize("retention_days", [14, 30, 90])
    def test_prune_uses_configured_cutoff(self, tmp_path, retention_days):
        db = InternetInsightsDB(tmp_path / f"retention_{retention_days}.db")
        incident_repo = IncidentRepository(db)
        evidence_repo = IncidentEvidenceRepository(db)
        manager = IncidentManager(
            incident_repo=incident_repo,
            evidence_repo=evidence_repo,
            cooldown_sec=900.0,
            retention_days=retention_days,
            config=type("C", (), {"retention_incident_days": retention_days}),
        )

        now = 1_800_000_000.0
        cutoff = now - retention_days * 86400
        expired_ts = cutoff - 3600
        fresh_ts = cutoff + 3600

        expired_id = self._make_incident(incident_repo, expired_ts)
        fresh_id = self._make_incident(incident_repo, fresh_ts)
        self._add_evidence(evidence_repo, expired_id, expired_ts)
        self._add_evidence(evidence_repo, fresh_id, fresh_ts)

        result = manager.prune_retention(now=now)

        assert result == {"incidents": 1, "evidence": 1}
        remaining_ids = {inc.id for inc in incident_repo.list_incidents(limit=100)}
        assert fresh_id in remaining_ids
        assert expired_id not in remaining_ids
        assert len(evidence_repo.get_by_incident(fresh_id)) == 1
        assert evidence_repo.get_by_incident(expired_id) == []
        db.close()

    def test_prune_keeps_rows_exactly_at_cutoff(self, tmp_path):
        db = InternetInsightsDB(tmp_path / "retention_boundary.db")
        incident_repo = IncidentRepository(db)
        evidence_repo = IncidentEvidenceRepository(db)
        manager = IncidentManager(
            incident_repo=incident_repo,
            evidence_repo=evidence_repo,
            retention_days=14,
            config=type("C", (), {"retention_incident_days": 14}),
        )

        now = 1_800_000_000.0
        cutoff_ts = now - 14 * 86400
        boundary_id = self._make_incident(incident_repo, cutoff_ts)

        result = manager.prune_retention(now=now)

        assert result == {"incidents": 0, "evidence": 0}
        remaining_ids = {inc.id for inc in incident_repo.list_incidents(limit=100)}
        assert boundary_id in remaining_ids
        db.close()

    def test_prune_empty_db_returns_zeroes(self, tmp_path):
        db = InternetInsightsDB(tmp_path / "retention_empty.db")
        manager = IncidentManager(
            incident_repo=IncidentRepository(db),
            evidence_repo=IncidentEvidenceRepository(db),
            retention_days=14,
            config=type("C", (), {"retention_incident_days": 14}),
        )
        assert manager.prune_retention(now=1_800_000_000.0) == {"incidents": 0, "evidence": 0}
        db.close()
