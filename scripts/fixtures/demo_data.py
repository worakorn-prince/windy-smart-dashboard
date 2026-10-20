"""Deterministic synthetic demo data for the observability dashboard.

Generates `.agent/manager/tool-calls.jsonl` + `.agent/manager/events.jsonl`
under a caller-provided root, following the log schema documented in
README-viewer.md (13-field tool-call rows, time/event/task event rows).

Deterministic by construction: fixed base timestamp + inline LCG, so every
run on any machine produces identical files. Task ids intentionally avoid
the `TEST-`/`DEP-` prefixes (metrics.py excludes those from metrics).

Importable for tests:
    from fixtures.demo_data import build_fixture, write_fixture
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

BASE_TIME = "2026-09-14T07:00:00+00:00"
ROW_SECONDS = 45
N_TASKS = 24
SEED = 20260914
AGENTS = ("building", "planning", "review", "error_debug")
TOOLS = ("Read", "Edit", "Bash", "Grep", "Write", "Glob", "Task")
ERROR_MESSAGES = (
    "FileNotFoundError: expected artifact missing after step 3",
    "timeout after 30000ms waiting for command output",
    "AssertionError: acceptance evidence not found",
    "ConnectionResetError: upstream session dropped mid-call",
)
DENIED_REASONS = (
    "permission: bash denied for this agent",
    "sandbox: write outside project root denied",
)

_BASE_DT = datetime(2026, 9, 14, 7, 0, 0, tzinfo=timezone.utc)


class _Rng:
    """Tiny inline LCG — deterministic across Python versions and platforms."""

    def __init__(self, seed=SEED):
        self.state = seed & 0x7FFFFFFF

    def next(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return self.state / 0x7FFFFFFF

    def int(self, lo, hi):
        return lo + int(self.next() * (hi - lo + 1))

    def pick(self, seq):
        return seq[self.int(0, len(seq) - 1)]


def _iso(row_index):
    return (_BASE_DT + timedelta(seconds=row_index * ROW_SECONDS)).isoformat()


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _plan_task(i, n_tasks=N_TASKS):
    """Outcome plan per task index — deterministic mix of success/failure/retry."""
    if i == n_tasks - 1:
        return {"outcome": "running", "attempts": 2, "reviews": 0, "recovery": True}
    mod = i % 8
    if mod == 4:
        return {"outcome": "done", "attempts": 2, "reviews": 1, "recovery": True}
    if mod == 5:
        return {"outcome": "failed", "attempts": 2, "reviews": 1, "recovery": True}
    if mod == 6:
        return {"outcome": "cancelled", "attempts": 1, "reviews": 0, "recovery": False}
    if mod == 7:
        return {"outcome": "done", "attempts": 1, "reviews": 2, "recovery": False}
    return {"outcome": "done", "attempts": 1,
            "reviews": 1 if i % 3 == 0 else 0, "recovery": False}


def build_fixture(n_tasks=N_TASKS, seed=SEED):
    """Return (toolcalls, events) as lists of dict rows — pure, writes nothing."""
    rng = _Rng(seed)
    toolcalls = []
    events = []
    row = 0

    def tcall(task, attempt, session, agent, operation, tool, duration_ms,
              status, error, prompt, tokens_in, tokens_out):
        nonlocal row
        toolcalls.append({
            "time": _iso(row),
            "task": task,
            "attempt": attempt,
            "session_id": session,
            "agent": agent,
            "operation": operation,
            "tool": tool,
            "duration_ms": duration_ms,
            "status": status,
            "error": error,
            "prompt_hash": _hash(prompt) if prompt else "-",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        })
        row += 1

    def event(etype, task, message, extra=None):
        nonlocal row
        entry = {"time": _iso(row), "event": etype, "task": task, "message": message}
        if extra:
            entry.update(extra)
        events.append(entry)
        row += 1

    for i in range(n_tasks):
        task = "TASK-D%03d" % (i + 1)
        plan = _plan_task(i, n_tasks)
        agent = AGENTS[i % len(AGENTS)]
        session = "ses-d%03d-a" % (i + 1)
        prompt = "%s implement demo step %d" % (task, i)
        event("TASK_CREATED", task, "Demo task %d created" % (i + 1),
              {"title": "Demo task %d" % (i + 1)})
        event("WORKER_STARTED", task, "Dispatch %s session %s" % (agent, session),
              {"session_id": session, "agent": agent, "attempt": 1})
        tcall(task, 1, session, agent, "DISPATCH", "Task", 0, "ok", None,
              prompt, None, None)

        for attempt in range(1, plan["attempts"] + 1):
            if attempt > 1:
                session = "ses-d%03d-%s" % (i + 1, chr(96 + attempt))
                event("WORKER_RESUMED", task,
                      "Resume %s session %s (attempt %d)" % (agent, session, attempt),
                      {"session_id": session, "agent": agent, "attempt": attempt})
                tcall(task, attempt, session, agent, "DISPATCH", "Task", 0, "ok", None,
                      "%s resume attempt %d" % (task, attempt), None, None)
            last_attempt = attempt == plan["attempts"]
            attempt_fails = (not last_attempt) or plan["outcome"] == "failed"
            n_calls = 32 + rng.int(0, 20)
            for j in range(n_calls):
                tool = TOOLS[(i + j) % len(TOOLS)]
                dur = rng.int(40, 42000)
                tin = rng.int(200, 4200)
                tout = rng.int(40, 1600)
                if j == n_calls - 1 and attempt_fails:
                    tcall(task, attempt, session, agent, "CALL", tool, dur, "error",
                          ERROR_MESSAGES[(i + attempt) % len(ERROR_MESSAGES)],
                          "%s attempt %d call %d" % (task, attempt, j), tin, tout)
                else:
                    tcall(task, attempt, session, agent, "CALL", tool, dur, "ok", None,
                          "%s attempt %d call %d" % (task, attempt, j), tin, tout)
            if i % 5 == 3 and attempt == 1:
                for d in range(2):
                    tcall(task, attempt, session, agent, "ATTEMPT", "Bash", 0, "denied",
                          DENIED_REASONS[d % len(DENIED_REASONS)], "", None, None)
            if plan["outcome"] == "running" and last_attempt:
                continue
            if attempt_fails:
                result_status = "error"
                result_error = "attempt failed - see last CALL error"
                if last_attempt and plan["outcome"] == "failed" and i % 2 == 1:
                    result_status = "limit"
                    result_error = "session tool-call limit reached"
                tcall(task, attempt, session, agent, "RESULT", tool, rng.int(50, 900),
                      result_status, result_error,
                      "%s attempt %d result" % (task, attempt), None, None)
                if not last_attempt:
                    event("RECOVERY_STARTED", task,
                          "Recovery after failed attempt %d" % attempt,
                          {"attempt": attempt})
            else:
                tcall(task, attempt, session, agent, "RESULT", tool, rng.int(50, 900),
                      "ok", None, "%s attempt %d result" % (task, attempt), None, None)

        for r in range(plan["reviews"]):
            event("REVIEW_FAILED", task, "Review failed: %d finding(s)" % (r + 1),
                  {"reviewer": "review", "findings_count": 1 + r})
        if plan["outcome"] == "done" and plan["reviews"]:
            event("REVIEW_PASSED", task, "Review passed after rework",
                  {"reviewer": "review", "findings_count": 0})
        if plan["outcome"] == "done":
            event("TASK_DONE", task, "Task %s marked DONE" % task)
        elif plan["outcome"] == "failed":
            event("TASK_FAILED", task,
                  "Task %s failed after %d attempts" % (task, plan["attempts"]))
        elif plan["outcome"] == "cancelled":
            event("TASK_CANCELLED", task, "Task %s cancelled by user" % task)

    return toolcalls, events


def write_fixture(root, n_tasks=N_TASKS, seed=SEED):
    """Write the fixture under <root>/.agent/manager/. Returns a summary dict."""
    toolcalls, events = build_fixture(n_tasks, seed)
    mgr = os.path.join(root, ".agent", "manager")
    os.makedirs(mgr, exist_ok=True)
    calls_path = os.path.join(mgr, "tool-calls.jsonl")
    events_path = os.path.join(mgr, "events.jsonl")
    for path, rows in ((calls_path, toolcalls), (events_path, events)):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {
        "root": root,
        "tasks": n_tasks,
        "tool_calls": len(toolcalls),
        "events": len(events),
        "tool_calls_path": calls_path,
        "events_path": events_path,
    }


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="dashboard-demo-")
    info = write_fixture(target)
    print("fixture written: %d tool-call rows, %d event rows -> %s"
          % (info["tool_calls"], info["events"], info["root"]))
