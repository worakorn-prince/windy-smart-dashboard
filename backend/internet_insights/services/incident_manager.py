"""Incident manager for Internet Insights Intelligence Engine.

Owns the incident lifecycle (active -> acknowledged -> resolved), evidence
linking (spec §15.4), reopen cooldown, and 90-day retention pruning.
The DB CHECK constraint has no 'open' status: incidents start at 'active'.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..analyzers.rules import ANALYZER_VERSION
from ..storage.repositories import (
    Incident,
    IncidentEvidence,
    IncidentEvidenceRepository,
    IncidentRepository,
    generate_incident_id,
)

logger = logging.getLogger("dashboard.internet_insights.services.incident_manager")

VALID_CATEGORIES = ("latency", "loss", "dns", "gateway", "interface", "tcp", "route")
VALID_SEVERITIES = ("info", "warning", "critical")
VALID_STATUSES = ("active", "acknowledged", "resolved", "suppressed")
VALID_EVIDENCE_TYPES = (
    "quality_sample",
    "interface_counter",
    "dns_probe",
    "tcp_stat",
    "route_change",
    "diagnostic_result",
)

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


class IncidentNotFoundError(LookupError):
    """Raised when an incident id does not exist."""


class InvalidIncidentTransitionError(ValueError):
    """Raised when a lifecycle transition is not allowed (e.g. resolve a resolved incident)."""


@dataclass
class EvaluationOutcome:
    """Result of feeding one RuleEvaluation into the manager."""

    action: str  # created | updated | auto_resolved | skipped_cooldown | none
    incident: Incident | None = None
    evidence: list[IncidentEvidence] = field(default_factory=list)
    reason: str | None = None


class IncidentManager:
    """Creates, updates, and resolves incidents with evidence linking."""

    def __init__(
        self,
        incident_repo: IncidentRepository | None = None,
        evidence_repo: IncidentEvidenceRepository | None = None,
        cooldown_sec: float | None = None,
        retention_days: int | None = None,
        config=None,
    ):
        if config is None:
            from ..config import get_config

            config = get_config()
        self.config = config
        self.incident_repo = incident_repo or IncidentRepository()
        self.evidence_repo = evidence_repo or IncidentEvidenceRepository()
        self.cooldown_sec = cooldown_sec if cooldown_sec is not None else 900.0
        self.retention_days = retention_days if retention_days is not None else config.retention_incident_days

    # ---- identity helpers (rule_id + target are stored as an evidence tag) ----

    @staticmethod
    def _identity_tag(rule_id: str, target: str) -> str:
        return json.dumps({"kind": "rule_identity", "rule_id": rule_id, "target": target})

    def _incident_identity(self, incident_id: str) -> tuple[str, str] | None:
        for ev in self.evidence_repo.get_by_incident(incident_id):
            try:
                payload = json.loads(ev.payload_json)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("kind") == "rule_identity":
                return str(payload.get("rule_id", "")), str(payload.get("target", ""))
        return None

    def _find_unresolved(self, rule_id: str, target: str) -> Incident | None:
        for incident in self.incident_repo.list_incidents(limit=200):
            if incident.status in ("resolved", "suppressed"):
                continue
            identity = self._incident_identity(incident.id)
            if identity == (rule_id, target):
                return incident
        return None

    def _find_last_resolved(self, rule_id: str, target: str) -> Incident | None:
        for incident in self.incident_repo.list_incidents(limit=200):
            if incident.status != "resolved" or incident.ended_at is None:
                continue
            identity = self._incident_identity(incident.id)
            if identity == (rule_id, target):
                return incident
        return None

    # ---- evidence (spec §15.4) ----

    def _build_evidence(self, incident_id: str, evaluation: Any) -> list[IncidentEvidence]:
        """Build the full §15.4 evidence set for an incident from a RuleEvaluation."""
        now = time.time()
        observations = getattr(evaluation, "observations", {}) or {}
        baseline = getattr(evaluation, "baseline", {}) or {}
        windows = getattr(evaluation, "detection_window", (0.0, 0.0))
        target = getattr(evaluation, "affected_target", "")
        interface_id = getattr(evaluation, "interface_id", None)
        rule_id = getattr(evaluation, "rule_id", "unknown")
        category = getattr(evaluation, "category", "")

        triggering = observations.get("triggering_observations", [])
        ts_range = observations.get("timestamp_range", {"start": windows[0], "end": windows[1]})
        observed = ts_range.get("end", now)
        last_trigger_ts = triggering[-1].get("ts", now) if triggering else now

        evidence_type_by_category = {
            "latency": "quality_sample",
            "loss": "quality_sample",
            "gateway": "quality_sample",
            "dns": "dns_probe",
            "tcp": "tcp_stat",
            "route": "route_change",
            "interface": "interface_counter",
        }
        primary_type = evidence_type_by_category.get(category, "quality_sample")

        def _item(payload: dict, evidence_type: str | None = None, at: float | None = None) -> IncidentEvidence:
            return IncidentEvidence(
                id=0,
                incident_id=incident_id,
                evidence_type=evidence_type or primary_type,
                observed_at=at if at is not None else observed,
                payload_json=json.dumps(payload, default=str),
            )

        evidence: list[IncidentEvidence] = [
            _item({"kind": "rule_identity", "rule_id": rule_id, "target": target}),
        ]
        if triggering:
            evidence.append(_item({"kind": "triggering_observations", "items": triggering}, at=last_trigger_ts))
        evidence.append(_item({"kind": "timestamp_range", "start": ts_range.get("start"), "end": ts_range.get("end")}))
        evidence.append(_item({"kind": "affected_target", "target": target}))
        if interface_id:
            evidence.append(_item({"kind": "relevant_interface", "interface_id": interface_id}, evidence_type="interface_counter"))
        evidence.append(_item({"kind": "baseline_comparison", **baseline}))
        evidence.append(_item({"kind": "related_diagnostic_session", "session_id": None}))
        evidence.append(_item({"kind": "confidence", "value": getattr(evaluation, "confidence", 0.0)}, at=last_trigger_ts))
        evidence.append(_item({"kind": "uncertainty", "note": getattr(evaluation, "uncertainty", "")}, at=last_trigger_ts))
        return evidence

    # ---- creation / processing ----

    def create_from_evaluation(self, evaluation: Any) -> EvaluationOutcome:
        """Create a new incident (status 'active') with full evidence."""
        incident_id = generate_incident_id()
        now = time.time()
        incident = Incident(
            id=incident_id,
            started_at=now,
            ended_at=None,
            category=getattr(evaluation, "category", ""),
            severity=getattr(evaluation, "severity", "warning"),
            status="active",
            title=getattr(evaluation, "title", "Incident"),
            summary=getattr(evaluation, "summary", ""),
            confidence=float(getattr(evaluation, "confidence", 0.0)),
            analyzer_version=getattr(evaluation, "analyzer_version", ANALYZER_VERSION),
        )
        evidence = self._build_evidence(incident_id, evaluation)
        self.incident_repo.create(incident)
        if evidence:
            self.evidence_repo.insert_batch(evidence)
        logger.info("Incident %s created (%s/%s)", incident_id, incident.category, incident.severity)
        return EvaluationOutcome(action="created", incident=incident, evidence=evidence)

    def process_evaluation(self, evaluation: Any, now: float | None = None) -> EvaluationOutcome:
        """Feed one rule evaluation: create, update, auto-resolve, or cooldown-skip."""
        if now is None:
            now = time.time()
        rule_id = getattr(evaluation, "rule_id", "unknown")
        target = getattr(evaluation, "affected_target", "")

        if evaluation.triggered:
            existing = self._find_unresolved(rule_id, target)
            if existing is not None:
                existing.confidence = max(existing.confidence, float(getattr(evaluation, "confidence", 0.0)))
                if _SEVERITY_ORDER.get(getattr(evaluation, "severity", "warning"), 1) > _SEVERITY_ORDER.get(existing.severity, 1):
                    existing.severity = evaluation.severity
                existing.summary = getattr(evaluation, "summary", existing.summary)
                self.incident_repo.update(existing)
                evidence = self._build_evidence(existing.id, evaluation)
                self.evidence_repo.insert_batch(evidence)
                return EvaluationOutcome(action="updated", incident=existing, evidence=evidence)

            last_resolved = self._find_last_resolved(rule_id, target)
            if last_resolved is not None and last_resolved.ended_at is not None:
                elapsed = now - last_resolved.ended_at
                if elapsed < self.cooldown_sec:
                    return EvaluationOutcome(
                        action="skipped_cooldown",
                        incident=last_resolved,
                        reason=f"reopened within cooldown ({elapsed:.0f}s < {self.cooldown_sec:.0f}s)",
                    )
            return self.create_from_evaluation(evaluation)

        # Not triggered: auto-resolve the matching incident only when the rule
        # fully evaluated (skipped_reason is None -> recovery condition holds).
        existing = self._find_unresolved(rule_id, target)
        if existing is not None and getattr(evaluation, "skipped_reason", None) is None:
            self._resolve(existing, now)
            return EvaluationOutcome(action="auto_resolved", incident=existing)
        return EvaluationOutcome(action="none", incident=existing)

    # ---- lifecycle ----

    def _resolve(self, incident: Incident, ended_at: float) -> Incident:
        incident.status = "resolved"
        incident.ended_at = ended_at
        self.incident_repo.update(incident)
        logger.info("Incident %s resolved at %s", incident.id, ended_at)
        return incident

    def get(self, incident_id: str) -> Incident | None:
        return self.incident_repo.get(incident_id)

    def list_incidents(
        self,
        status: str | None = None,
        category: str | None = None,
        since: float | None = None,
        limit: int = 50,
    ) -> list[Incident]:
        return self.incident_repo.list_incidents(status=status, category=category, since=since, limit=limit)

    def evidence_for(self, incident_id: str) -> list[IncidentEvidence]:
        return self.evidence_repo.get_by_incident(incident_id)

    def acknowledge_incident(self, incident_id: str) -> Incident:
        incident = self.incident_repo.get(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        if incident.status != "active":
            raise InvalidIncidentTransitionError(f"cannot acknowledge incident in status '{incident.status}'")
        incident.status = "acknowledged"
        self.incident_repo.update(incident)
        return incident

    def resolve_incident(self, incident_id: str, ended_at: float | None = None) -> Incident:
        incident = self.incident_repo.get(incident_id)
        if incident is None:
            raise IncidentNotFoundError(incident_id)
        if incident.status in ("resolved", "suppressed"):
            raise InvalidIncidentTransitionError(f"cannot resolve incident in status '{incident.status}'")
        return self._resolve(incident, ended_at if ended_at is not None else time.time())

    # ---- retention ----

    def prune_retention(self, now: float | None = None) -> dict[str, int]:
        """Delete incidents (and their evidence) older than retention_days."""
        if now is None:
            now = time.time()
        cutoff = now - self.retention_days * 86400
        evidence_removed = self.evidence_repo.prune(cutoff)
        incidents_removed = self.incident_repo.prune(cutoff)
        return {"incidents": incidents_removed, "evidence": evidence_removed}
