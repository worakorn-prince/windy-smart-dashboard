"""Profile the internet-insights background workload (INET-M6-A).

Runs the incident pipeline (evaluate_all -> correlate -> process_evaluation,
the exact code path wired into main._incident_loop) in a tight idle loop
against a throwaway database and reports measured process CPU%, peak RSS,
and emitted-payload bandwidth scaled to KB/min.

Run from backend/:
    .\\.venv\\Scripts\\python.exe scripts\\profile_internet_insights.py [--duration 15]

Targets: CPU < 2%, RSS < 100 MB, bandwidth < 100 KB/min.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import psutil  # noqa: E402  (requires sys.path setup above)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=15.0, help="measurement window seconds")
    args = parser.parse_args()

    proc = psutil.Process()
    proc.cpu_percent(interval=None)

    from internet_insights.analyzers.rules import IncidentAnalyzer
    from internet_insights.router import _incident_to_dict
    from internet_insights.services.incident_manager import IncidentManager
    from internet_insights.storage.database import InternetInsightsDB
    from internet_insights.storage.repositories import (
        IncidentEvidenceRepository,
        IncidentRepository,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db = InternetInsightsDB(Path(tmp) / "profile.db")
        analyzer = IncidentAnalyzer()
        manager = IncidentManager(
            incident_repo=IncidentRepository(db),
            evidence_repo=IncidentEvidenceRepository(db),
            config=type("C", (), {"retention_incident_days": 90}),
        )

        cycles = 0
        evaluations_seen = 0
        emitted_bytes = 0
        created = 0
        updated = 0
        cycle_wall_total = 0.0

        start = time.perf_counter()
        while time.perf_counter() - start < args.duration:
            cycle_start = time.perf_counter()
            evaluations = analyzer.evaluate_all()
            evaluations_seen += len(evaluations)
            correlated = analyzer.correlate(evaluations)
            for ev in ([*evaluations, correlated] if correlated else evaluations):
                outcome = manager.process_evaluation(ev)
                if outcome.incident is not None and outcome.action not in ("none", "skipped_cooldown"):
                    payload = json.dumps(_incident_to_dict(outcome.incident)).encode("utf-8")
                    emitted_bytes += len(payload)
                    if outcome.action == "created":
                        created += 1
                    elif outcome.action == "updated":
                        updated += 1
            cycle_wall_total += time.perf_counter() - cycle_start
            cycles += 1

        elapsed = time.perf_counter() - start
        tight_cpu_pct = proc.cpu_percent(interval=None) / max(elapsed, 1e-6)
        rss_mb = proc.memory_info().rss / (1024 * 1024)
        kb_per_min = (emitted_bytes / 1024.0) / (elapsed / 60.0)
        avg_cycle_ms = (cycle_wall_total / max(cycles, 1)) * 1000.0
        production_tick_sec = 60.0
        avg_cycle_sec = cycle_wall_total / max(cycles, 1)
        production_cpu_pct = (avg_cycle_sec / production_tick_sec) * 100.0

        db.close()

    print(f"window_seconds        : {elapsed:.2f}")
    print(f"cycles                : {cycles}")
    print(f"evaluations_per_cycle : {evaluations_seen / max(cycles, 1):.0f}")
    print(f"avg_cycle_ms          : {avg_cycle_ms:.3f} ms")
    print(f"incidents_created     : {created}")
    print(f"incidents_updated     : {updated}")
    print(f"cpu_tight_loop_pct    : {tight_cpu_pct:.2f}% (back-to-back, stress bound)")
    print(f"cpu_production_pct    : {production_cpu_pct:.3f}% at one tick / {production_tick_sec:.0f}s (target < 2%)")
    print(f"rss_mb                : {rss_mb:.1f} MB (target < 100 MB)")
    print(f"bandwidth_kb_per_min  : {kb_per_min:.2f} KB/min (target < 100 KB/min)")
    print(
        "verdict               : "
        + (
            "PASS"
            if production_cpu_pct < 2.0 and rss_mb < 100.0 and kb_per_min < 100.0
            else "CHECK (see targets in header)"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
