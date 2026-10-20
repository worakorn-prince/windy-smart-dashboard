"""bootstrap.py — one-command setup for the Agent Observability Dashboard.

Modes:
  --demo            generate a deterministic synthetic fixture under --root,
                    then run the real pipeline (metrics -> export_json ->
                    aggregate) against it via subprocess, producing
                    data.json + all-projects.json inside --root.
  (no --demo)       init an empty .agent/ skeleton (missing files only).

The repo's own .agent/ is never touched: everything happens under --root
(default: a fresh temp dir, printed on completion).

Usage:
  python scripts/bootstrap.py --demo
  python scripts/bootstrap.py --demo --root D:\\tmp\\demo
  python scripts/bootstrap.py --root .
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

REQUIRED_DATA_KEYS = ("kpis", "per_task", "timeline", "recent_activity", "errors",
                      "durations", "agents", "efficiency", "tools")
REQUIRED_AGG_KEYS = ("combined", "per_project", "per_task", "timeline")


def _run(cmd):
    print("$ %s" % " ".join(cmd))
    return subprocess.run(cmd, check=True)


def _manager_paths(root):
    mgr = os.path.join(root, ".agent", "manager")
    return {
        "mgr": mgr,
        "events": os.path.join(mgr, "events.jsonl"),
        "calls": os.path.join(mgr, "tool-calls.jsonl"),
        "metrics": os.path.join(mgr, "metrics.json"),
        "history": os.path.join(mgr, "history"),
        "queue": os.path.join(mgr, "queue.json"),
        "reviews": os.path.join(mgr, "reviews"),
        "config": os.path.join(mgr, "config.json"),
        "checkpoint": os.path.join(root, ".agent", "building", "checkpoint.json"),
    }


def run_pipeline(root):
    """metrics -> export_json -> aggregate, pointed at <root> via subprocess.

    metrics.py / export_json.py derive their default paths from the repo's
    own .agent/ and their CLIs do not expose every path, so each step runs in
    a child process that imports the module and overrides its path constants
    before invoking it (no pipeline source file is modified).
    """
    p = _manager_paths(root)
    data_out = os.path.join(root, "data.json")
    agg_out = os.path.join(root, "all-projects.json")

    print("[1/3] metrics --rebuild (root: %s)" % root)
    code = (
        "import sys; sys.path.insert(0, %(here)r); "
        "import metrics; "
        "metrics.MANAGER_DIR = %(mgr)r; metrics.EVENTS_FILE = %(events)r; "
        "metrics.TOOLCALLS_FILE = %(calls)r; metrics.METRICS_FILE = %(metrics)r; "
        "metrics.HISTORY_DIR = %(history)r; "
        "metrics.rebuild()"
    ) % {"here": HERE, "mgr": p["mgr"], "events": p["events"], "calls": p["calls"],
         "metrics": p["metrics"], "history": p["history"]}
    _run([sys.executable, "-c", code])

    print("[2/3] export_json -> %s" % data_out)
    code = (
        "import sys; sys.path.insert(0, %(here)r); "
        "from export_json import export_data; "
        "export_data(%(out)r, metrics_path=%(metrics)r, events_path=%(events)r, "
        "toolcalls_path=%(calls)r, queue_path=%(queue)r, reviews_dir=%(reviews)r, "
        "history_dir=%(history)r, checkpoint_path=%(checkpoint)r, "
        "config_path=%(config)r)"
    ) % {"here": HERE, "out": data_out, "metrics": p["metrics"],
         "events": p["events"], "calls": p["calls"], "queue": p["queue"],
         "reviews": p["reviews"], "history": p["history"],
         "checkpoint": p["checkpoint"], "config": p["config"]}
    _run([sys.executable, "-c", code])

    print("[3/3] aggregate -> %s" % agg_out)
    _run([sys.executable, os.path.join(HERE, "aggregate.py"),
          "--projects", root, "--out", agg_out])
    return data_out, agg_out


def verify_outputs(data_out, agg_out):
    with open(data_out, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(agg_out, "r", encoding="utf-8") as f:
        agg = json.load(f)
    missing = [k for k in REQUIRED_DATA_KEYS if k not in data]
    if missing:
        raise RuntimeError("data.json missing sections: %s" % ", ".join(missing))
    missing = [k for k in REQUIRED_AGG_KEYS if k not in agg]
    if missing:
        raise RuntimeError("all-projects.json missing sections: %s" % ", ".join(missing))
    k = data["kpis"]
    print("data.json OK - kpis: %s tasks, %s done, success_rate %.2f, %s tool calls"
          % (k["total_tasks"], k["done"], k["success_rate"], k["total_tool_calls"]))
    c = agg["combined"]
    print("all-projects.json OK - combined: %s project(s), %s tasks, %s tool calls"
          % (c["projects"], c["total_tasks"], c["total_tool_calls"]))


def init_skeleton(root):
    mgr = os.path.join(root, ".agent", "manager")
    os.makedirs(mgr, exist_ok=True)
    for name in ("tool-calls.jsonl", "events.jsonl"):
        path = os.path.join(mgr, name)
        if os.path.exists(path):
            print("  keep existing %s" % path)
        else:
            with open(path, "w", encoding="utf-8", newline="\n"):
                pass
            print("  created %s" % path)


def print_next_steps(root, info, data_out, agg_out):
    print("")
    print("Demo data ready.")
    print("  root:              %s" % root)
    print("  tool-calls.jsonl:  %s  (%d rows)" % (info["tool_calls_path"], info["tool_calls"]))
    print("  events.jsonl:      %s  (%d rows)" % (info["events_path"], info["events"]))
    print("  data.json:         %s" % data_out)
    print("  all-projects.json: %s" % agg_out)
    print("")
    print("To open the dashboard with this demo data:")
    print("  1. copy the two JSON files over the dashboard's runtime copies:")
    print('       copy /Y "%s" dashboard\\data.json' % data_out)
    print('       copy /Y "%s" dashboard\\all-projects.json' % agg_out)
    print("     (overwrites current dashboard data - skip to keep real data)")
    print("  2. serve over http (fetch() is blocked on file://):")
    print("       python -m http.server")
    print("  3. open:")
    print("       http://localhost:8000/dashboard/index.html   (single-project view)")
    print("       http://localhost:8000/dashboard/all.html     (combined view)")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Init the dashboard skeleton or seed demo data and run the full pipeline.",
        epilog="The repo's own .agent/ is never touched - everything happens under --root.")
    parser.add_argument("--demo", action="store_true",
                        help="seed deterministic demo data and run metrics -> export_json -> aggregate")
    parser.add_argument("--root", default=None,
                        help="working root (default: a fresh temp dir)")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root) if args.root else tempfile.mkdtemp(prefix="dashboard-demo-")
    os.makedirs(root, exist_ok=True)
    print("bootstrap root: %s" % root)

    try:
        if args.demo:
            calls_path = os.path.join(root, ".agent", "manager", "tool-calls.jsonl")
            if os.path.exists(calls_path) and os.path.getsize(calls_path) > 0:
                print("refusing to overwrite existing data at %s - choose another --root"
                      % calls_path, file=sys.stderr)
                return 2
            from fixtures import demo_data
            info = demo_data.write_fixture(root)
            print("fixture: %d tool-call rows, %d event rows, %d tasks"
                  % (info["tool_calls"], info["events"], info["tasks"]))
            data_out, agg_out = run_pipeline(root)
            verify_outputs(data_out, agg_out)
            print_next_steps(root, info, data_out, agg_out)
        else:
            init_skeleton(root)
            print("skeleton ready - log rows into the .jsonl files, then run:")
            print("  python scripts/metrics.py --rebuild")
            print("  python scripts/export_json.py")
            print("  python scripts/aggregate.py")
            print("(these read the repo's own .agent/ by default;")
            print(" try 'python scripts/bootstrap.py --demo' for sample data in a temp dir)")
    except subprocess.CalledProcessError as exc:
        print("pipeline step failed (exit %s): %s" % (exc.returncode, exc.cmd),
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
