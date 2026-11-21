"""Tests for the Internet Insights incident manager (INET-M5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from internet_insights.storage.database import InternetInsightsDB
from internet_insights.storage.repositories import (
    IncidentEvidenceRepository,
    IncidentRepository,
)
from internet_insights.services.incident_manager import (
    IncidentManager,
    IncidentNotFoundError,
    InvalidIncidentTransitionError,
    VALID_CATEGORIES,
    VALID_EVIDENCE_TYPES,
    VALID_SEVERITIES,
    VALID_STATUSES,
)


class _Eval:
    """Minimal RuleEvaluation stand-in."""

    def __init__(self, **kwargs):
        defaults = {
            "rule_id": "sustained_latency_increase",
            "triggered": True,
            "skipped_reason": None,
            "confidence": 0.75,
            "observations": {
                "triggering_observations": [{"ts": 1000.0, "rtt_ms": 90.0}],
                "timestamp_range": {"start": 940.0, "end": 1000.0},
            },
            "baseline": {"baseline_median_ms": 20.0, "detection_median_ms": 90.0, "latency_increase_pct": 350.0},
            "detection_window": (940.0, 1000.0),
            "baseline_window": (100.0, 940.0),
            "affected_target": "primary",
            "interface_id": "eth0",
            "title": "Sustained latency increase on primary",
            "category": "latency",
            "severity": "warning",
            "summary": "Median latency tripled",
            "uncertainty": "limited by sample size",
        }
        defaults.update(kwargs)
        for key, value in defaults.items():
            setattr(self, key, value)


@pytest.fixture
def temp_db(tmp_path: Path) -> InternetInsightsDB:
    db = InternetInsightsDB(tmp_path / "test_incident_manager.db")
    yield db
    db.close()


@pytest.fixture
def repos(temp_db: InternetInsightsDB):
    from internet_insights.storage.migrations import apply_migrations

    apply_migrations(temp_db)
    return IncidentRepository(temp_db), IncidentEvidenceRepository(temp_db)


@pytest.fixture
def manager(repos) -> IncidentManager:
    incident_repo, evidence_repo = repos
    return IncidentManager(
        incident_repo=incident_repo,
        evidence_repo=evidence_repo,
        cooldown_sec=900.0,
        retention_days=90,
        config=type("C", (), {"retention_incident_days": 90}),
    )


class TestLifecycle:
    def test_create_starts_active(self, manager):
        outcome = manager.create_from_evaluation(_Eval())
        assert outcome.action == "created"
        assert outcome.incident.status == "active"
        assert outcome.incident.ended_at is None
        assert outcome.incident.id.startswith("inc_") or outcome.incident.id

    def test_resolve_from_active(self, manager):
        incident = manager.create_from_evaluation(_Eval()).incident
        resolved = manager.resolve_incident(incident.id)
        assert resolved.status == "resolved"
        assert resolved.ended_at is not None

    def test_resolve_from_acknowledged(self, manager):
        incident = manager.create_from_evaluation(_Eval()).incident
        acknowledged = manager.acknowledge_incident(incident.id)
        assert acknowledged.status == "acknowledged"
        resolved = manager.resolve_incident(incident.id)
        assert resolved.status == "resolved"
        assert resolved.ended_at is not None

    def test_resolve_already_resolved_raises(self, manager):
        incident = manager.create_from_evaluation(_Eval()).incident
        manager.resolve_incident(incident.id)
        with pytest.raises(InvalidIncidentTransitionError):
            manager.resolve_incident(incident.id)

    def test_acknowledge_non_active_raises(self, manager):
        incident = manager.create_from_evaluation(_Eval()).incident
        manager.resolve_incident(incident.id)
        with pytest.raises(InvalidIncidentTransitionError):
            manager.acknowledge_incident(incident.id)

    def test_missing_incident_raises_not_found(self, manager):
        with pytest.raises(IncidentNotFoundError):
            manager.resolve_incident("inc_missing")
        with pytest.raises(IncidentNotFoundError):
            manager.acknowledge_incident("inc_missing")

    def test_valid_domains(self):
        assert set(VALID_STATUSES) == {"active", "acknowledged", "resolved", "suppressed"}
        assert set(VALID_SEVERITIES) == {"info", "warning", "critical"}
        assert "latency" in VALID_CATEGORIES and "route" in VALID_CATEGORIES
        assert set(VALID_EVIDENCE_TYPES) == {
            "quality_sample",
            "interface_counter",
            "dns_probe",
            "tcp_stat",
            "route_change",
            "diagnostic_result",
        }


class TestProcessEvaluation:
    def test_created_outcome(self, manager):
        outcome = manager.process_evaluation(_Eval(), now=1000.0)
        assert outcome.action == "created"
        assert outcome.incident.status == "active"

    def test_updated_outcome_merges_confidence_and_severity(self, manager):
        manager.process_evaluation(_Eval(), now=1000.0)
        outcome = manager.process_evaluation(
            _Eval(confidence=0.9, severity="critical", summary="worse now"), now=1100.0
        )
        assert outcome.action == "updated"
        assert outcome.incident.confidence == pytest.approx(0.9)
        assert outcome.incident.severity == "critical"
        assert outcome.incident.summary == "worse now"
        assert manager.list_incidents(limit=10)[0].id == outcome.incident.id

    def test_auto_resolved_outcome(self, manager):
        created = manager.process_evaluation(_Eval(), now=1000.0).incident
        outcome = manager.process_evaluation(_Eval(triggered=False), now=2000.0)
        assert outcome.action == "auto_resolved"
        assert outcome.incident.id == created.id
        assert outcome.incident.status == "resolved"

    def test_none_outcome_without_existing(self, manager):
        outcome = manager.process_evaluation(_Eval(triggered=False), now=1000.0)
        assert outcome.action == "none"
        assert outcome.incident is None

    def test_skipped_cooldown_blocks_reopen(self, manager):
        manager.process_evaluation(_Eval(), now=1000.0)
        manager.process_evaluation(_Eval(triggered=False), now=2000.0)  # auto-resolve
        outcome = manager.process_evaluation(_Eval(), now=2000.0 + 60)
        assert outcome.action == "skipped_cooldown"
        assert outcome.incident is not None
        assert len(manager.list_incidents(limit=10)) == 1

    def test_reopen_allowed_after_cooldown(self, manager):
        manager.process_evaluation(_Eval(), now=1000.0)
        manager.process_evaluation(_Eval(triggered=False), now=2000.0)
        outcome = manager.process_evaluation(_Eval(), now=2000.0 + 901)
        assert outcome.action == "created"
        assert len(manager.list_incidents(limit=10)) == 2

    def test_different_identity_creates_separate_incident(self, manager):
        manager.process_evaluation(_Eval(), now=1000.0)
        other = manager.process_evaluation(
            _Eval(rule_id="sustained_packet_loss", affected_target="primary", category="loss"), now=1010.0
        )
        assert other.action == "created"
        assert len(manager.list_incidents(limit=10)) == 2

    def test_skipped_evaluation_does_not_auto_resolve(self, manager):
        created = manager.process_evaluation(_Eval(), now=1000.0).incident
        outcome = manager.process_evaluation(
            _Eval(triggered=False, skipped_reason="min_sample_count (3 < 20)"), now=2000.0
        )
        assert outcome.action == "none"
        assert manager.get(created.id).status == "active"


class TestEvidence:
    def test_evidence_kinds_complete_after_create(self, manager, repos):
        _incident_repo, evidence_repo = repos
        outcome = manager.process_evaluation(_Eval(), now=1000.0)
        kinds = set()
        for ev in evidence_repo.get_by_incident(outcome.incident.id):
            payload = json.loads(ev.payload_json)
            kinds.add(payload["kind"])
        assert {
            "rule_identity",
            "triggering_observations",
            "timestamp_range",
            "affected_target",
            "relevant_interface",
            "baseline_comparison",
            "related_diagnostic_session",
            "confidence",
            "uncertainty",
        } <= kinds

    def test_rule_identity_stored_and_reused(self, manager, repos):
        _, _evidence_repo_unused = repos
        outcome = manager.process_evaluation(_Eval(), now=1000.0)
        identity = manager._incident_identity(outcome.incident.id)
        assert identity == ("sustained_latency_increase", "primary")

    def test_evidence_types_map_by_category(self, manager, repos):
        _, evidence_repo = repos
        outcome = manager.process_evaluation(
            _Eval(rule_id="dns_resolution_degradation", affected_target="dns", category="dns"), now=1000.0
        )
        types = {ev.evidence_type for ev in evidence_repo.get_by_incident(outcome.incident.id)}
        assert types <= set(VALID_EVIDENCE_TYPES)
        assert "dns_probe" in types


class TestRetention:
    def test_prune_removes_old_incidents_and_evidence(self, manager, repos, monkeypatch):
        _, evidence_repo = repos
        clock = {"now": 1.0}
        monkeypatch.setattr(
            "internet_insights.services.incident_manager.time.time", lambda: clock["now"]
        )
        old = manager.process_evaluation(_Eval())
        clock["now"] = 89 * 86400
        fresh = manager.process_evaluation(
            _Eval(rule_id="sustained_packet_loss", affected_target="primary", category="loss")
        )
        clock["now"] = 100 * 86400 + 10
        result = manager.prune_retention()
        assert result["incidents"] >= 1
        assert result["evidence"] >= 1
        assert manager.get(old.incident.id) is None
        assert manager.get(fresh.incident.id) is not None
        assert evidence_repo.get_by_incident(old.incident.id) == []
