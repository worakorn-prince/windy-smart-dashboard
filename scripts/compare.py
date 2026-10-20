import argparse
import glob
import io
import json
import os
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import metrics as metrics_mod

METRICS_REL = os.path.join(".agent", "manager", "metrics.json")
TOOLCALLS_GLOB = os.path.join(".agent", "**", "tool-calls.jsonl")

THRESHOLDS = {
    "tool_calls": ("pct_increase", 20.0),
    "tokens_total": ("pct_increase", 25.0),
    "done_rate_pct": ("abs_decrease", 5.0),
    "failures": ("abs_increase", 0.0),
}

METRICS = (
    ("total_tasks", "Total tasks", "int"),
    ("done_rate_pct", "Done rate", "pct"),
    ("tool_calls", "Tool calls", "int"),
    ("tokens_total", "Tokens total", "int"),
    ("failures", "Failures", "int"),
    ("denied", "Denied", "int"),
    ("avg_tool_calls_per_task", "Avg tool calls / task", "float2"),
    ("avg_time_to_done_s", "Avg time to DONE (s)", "float1"),
)


class DatasetError(Exception):
    pass


def _num(value, default=0.0):
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_metrics(payload, source):
    if not isinstance(payload, dict) or not isinstance(payload.get("totals"), dict):
        raise DatasetError(f"invalid metrics payload (missing totals): {source}")
    return payload


def rebuild_dataset(run_dir):
    manager_dir = os.path.join(run_dir, ".agent", "manager")
    saved = (metrics_mod.MANAGER_DIR, metrics_mod.EVENTS_FILE,
             metrics_mod.TOOLCALLS_FILE, metrics_mod.METRICS_FILE,
             metrics_mod.HISTORY_DIR)
    metrics_mod.MANAGER_DIR = manager_dir
    metrics_mod.EVENTS_FILE = os.path.join(manager_dir, "events.jsonl")
    metrics_mod.TOOLCALLS_FILE = os.path.join(manager_dir, "tool-calls.jsonl")
    metrics_mod.METRICS_FILE = os.path.join(manager_dir, "metrics.json")
    metrics_mod.HISTORY_DIR = os.path.join(manager_dir, "history")
    try:
        with redirect_stdout(io.StringIO()):
            return metrics_mod.rebuild()
    finally:
        (metrics_mod.MANAGER_DIR, metrics_mod.EVENTS_FILE,
         metrics_mod.TOOLCALLS_FILE, metrics_mod.METRICS_FILE,
         metrics_mod.HISTORY_DIR) = saved


def load_dataset(run_dir):
    if not os.path.isdir(run_dir):
        raise DatasetError(f"run dir not found: {run_dir}")
    metrics_path = os.path.join(run_dir, METRICS_REL)
    if os.path.isfile(metrics_path):
        try:
            payload = _load_json(metrics_path)
        except (OSError, ValueError) as exc:
            raise DatasetError(f"cannot read {metrics_path}: {exc}")
        return _validate_metrics(payload, metrics_path)
    if glob.glob(os.path.join(run_dir, TOOLCALLS_GLOB), recursive=True):
        try:
            payload = rebuild_dataset(run_dir)
        except Exception as exc:
            raise DatasetError(f"rebuild failed for {run_dir}: {exc}")
        return _validate_metrics(payload, run_dir)
    raise DatasetError(
        f"no dataset in {run_dir} "
        f"(need {METRICS_REL} or {os.path.join('.agent', '**', 'tool-calls.jsonl')})")


def summarize(payload):
    totals = payload.get("totals") or {}
    per_task = payload.get("per_task") or {}
    tasks = int(_num(totals.get("tasks"), len(per_task)))
    done = int(_num(totals.get("done")))
    failed = int(_num(totals.get("failed")))
    denied = int(_num(totals.get("denied_attempts")))
    tool_calls = int(_num(totals.get("tool_calls")))
    tokens = int(_num(totals.get("tokens_total")))
    if "tool_calls" not in totals:
        tool_calls = int(sum(_num(v.get("tool_calls_per_task"))
                             for v in per_task.values() if isinstance(v, dict)))
    if "tokens_total" not in totals:
        tokens = int(sum(_num(v.get("tokens_total"))
                         for v in per_task.values() if isinstance(v, dict)))
    if "denied_attempts" not in totals:
        denied = int(sum(_num(v.get("denied_attempts"))
                         for v in per_task.values() if isinstance(v, dict)))
    success_rate = totals.get("success_rate")
    if success_rate is not None:
        done_rate = _num(success_rate) * 100.0
    elif tasks:
        done_rate = done / tasks * 100.0
    else:
        done_rate = 0.0
    avg_calls = (tool_calls / tasks) if tasks else 0.0
    times = []
    for row in per_task.values():
        if isinstance(row, dict) and row.get("time_to_DONE") is not None:
            times.append(_num(row.get("time_to_DONE")))
    avg_time = (sum(times) / len(times)) if times else None
    return {
        "total_tasks": tasks,
        "done_rate_pct": done_rate,
        "tool_calls": tool_calls,
        "tokens_total": tokens,
        "failures": failed,
        "denied": denied,
        "avg_tool_calls_per_task": avg_calls,
        "avg_time_to_done_s": avg_time,
    }


def _delta(base, cand):
    if base is None or cand is None:
        return None, None
    delta = cand - base
    pct = (delta / abs(base) * 100.0) if base else None
    return delta, pct


def _regression_reason(metric, base, cand):
    rule = THRESHOLDS.get(metric)
    if rule is None or base is None or cand is None:
        return None
    kind, limit = rule
    if kind == "pct_increase":
        if base == 0:
            if cand > 0:
                return f"{metric} 0 -> {cand:g} (threshold +{limit:g}%)"
            return None
        pct = (cand - base) / base * 100.0
        if pct > limit:
            return f"{metric} +{pct:.1f}% (threshold +{limit:g}%)"
    elif kind == "abs_decrease":
        drop = base - cand
        if drop > limit:
            return f"{metric} -{drop:.1f} pts (threshold > {limit:g} pts drop)"
    elif kind == "abs_increase":
        rise = cand - base
        if rise > limit:
            return f"{metric} +{rise:g} (threshold > {limit:g})"
    return None


def compare_datasets(base_payload, cand_payload):
    base = summarize(base_payload)
    cand = summarize(cand_payload)
    rows = []
    regressions = []
    for key, label, kind in METRICS:
        b = base[key]
        c = cand[key]
        delta, delta_pct = _delta(b, c)
        reason = _regression_reason(key, b, c)
        rule = THRESHOLDS.get(key)
        row = {
            "metric": key,
            "label": label,
            "base": b,
            "cand": c,
            "delta": delta,
            "delta_pct": delta_pct,
            "checked": rule is not None,
            "threshold": {"kind": rule[0], "limit": rule[1]} if rule else None,
            "regression": reason is not None,
        }
        if reason is not None:
            row["reason"] = reason
            regressions.append({
                "metric": key,
                "base": b,
                "cand": c,
                "delta": delta,
                "delta_pct": delta_pct,
                "reason": reason,
            })
        rows.append(row)
    return {
        "status": "REGRESSION" if regressions else "PASS",
        "metrics": rows,
        "regressions": regressions,
    }


def _fmt_value(value, kind):
    if value is None:
        return "n/a"
    if kind == "int":
        return f"{int(round(value)):,}"
    if kind == "pct":
        return f"{value:.1f}%"
    if kind == "float2":
        return f"{value:.2f}"
    return f"{value:.1f}"


def _fmt_delta(row, kind):
    value = row["delta"]
    if value is None:
        return "n/a"
    if kind == "pct":
        return f"{value:+.1f} pts"
    if kind == "int":
        return f"{int(round(value)):+,}"
    if kind == "float2":
        return f"{value:+.2f}"
    return f"{value:+.1f}"


def _fmt_pct(value):
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


def format_markdown(result, base_dir=None, cand_dir=None):
    lines = ["## Run comparison", ""]
    if base_dir:
        lines.append(f"- base: `{base_dir}`")
    if cand_dir:
        lines.append(f"- candidate: `{cand_dir}`")
    if base_dir or cand_dir:
        lines.append("")
    lines.append("| Metric | Base | Candidate | Delta | Delta % | Status |")
    lines.append("| --- | ---: | ---: | ---: | ---: | :--- |")
    for row in result["metrics"]:
        kind = next(kind for key, _, kind in METRICS if key == row["metric"])
        if row["regression"]:
            status = "REGRESSION"
        elif row["checked"]:
            status = "ok"
        else:
            status = "-"
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            row["label"],
            _fmt_value(row["base"], kind),
            _fmt_value(row["cand"], kind),
            _fmt_delta(row, kind),
            _fmt_pct(row["delta_pct"]),
            status,
        ))
    lines.append("")
    lines.append(f"Summary: **{result['status']}** "
                 f"({len(result['regressions'])} regression(s))")
    for reg in result["regressions"]:
        lines.append(f"- {reg['reason']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare two agent-viewer runs and flag metric regressions")
    parser.add_argument("--base", required=True,
                        help="Base run dir (.agent/manager/metrics.json or .agent/**/tool-calls.jsonl)")
    parser.add_argument("--cand", required=True,
                        help="Candidate run dir (.agent/manager/metrics.json or .agent/**/tool-calls.jsonl)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit machine-readable JSON instead of a markdown table")
    args = parser.parse_args(argv)
    try:
        base_payload = load_dataset(args.base)
        cand_payload = load_dataset(args.cand)
    except DatasetError as exc:
        print(f"[compare] {exc}", file=sys.stderr)
        return 2
    result = compare_datasets(base_payload, cand_payload)
    base_dir = os.path.abspath(args.base)
    cand_dir = os.path.abspath(args.cand)
    if args.as_json:
        output = {"base_dir": base_dir, "cand_dir": cand_dir}
        output.update(result)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_markdown(result, base_dir=base_dir, cand_dir=cand_dir))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
