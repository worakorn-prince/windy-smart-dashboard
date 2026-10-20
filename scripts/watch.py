import os
import sys
import glob
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import metrics as metrics_mod
import export_json as export_mod

WATCH_PATTERNS = ("tool-calls.jsonl", "events.jsonl")
DEFAULT_INTERVAL = 2.0


def snapshot(root):
    state = {}
    base = os.path.join(root, ".agent")
    if not os.path.isdir(base):
        return state
    for name in WATCH_PATTERNS:
        for path in glob.glob(os.path.join(base, "**", name), recursive=True):
            try:
                st = os.stat(path)
            except OSError:
                continue
            state[os.path.abspath(path)] = (st.st_mtime, st.st_size)
    return state


def should_rebuild(prev, cur):
    if prev is None:
        return True
    if set(prev) != set(cur):
        return True
    for key in prev:
        if prev[key] != cur[key]:
            return True
    return False


def rebuild(root):
    manager_dir = os.path.join(root, ".agent", "manager")
    events_path = os.path.join(manager_dir, "events.jsonl")
    toolcalls_path = os.path.join(manager_dir, "tool-calls.jsonl")
    metrics_path = os.path.join(manager_dir, "metrics.json")
    history_dir = os.path.join(manager_dir, "history")
    out_path = os.path.join(root, "dashboard", "data.json")
    saved = (metrics_mod.MANAGER_DIR, metrics_mod.EVENTS_FILE,
             metrics_mod.TOOLCALLS_FILE, metrics_mod.METRICS_FILE,
             metrics_mod.HISTORY_DIR)
    metrics_mod.MANAGER_DIR = manager_dir
    metrics_mod.EVENTS_FILE = events_path
    metrics_mod.TOOLCALLS_FILE = toolcalls_path
    metrics_mod.METRICS_FILE = metrics_path
    metrics_mod.HISTORY_DIR = history_dir
    try:
        metrics_mod.rebuild()
    finally:
        (metrics_mod.MANAGER_DIR, metrics_mod.EVENTS_FILE,
         metrics_mod.TOOLCALLS_FILE, metrics_mod.METRICS_FILE,
         metrics_mod.HISTORY_DIR) = saved
    export_mod.export_data(
        out_path,
        metrics_path=metrics_path,
        events_path=events_path,
        toolcalls_path=toolcalls_path,
        queue_path=os.path.join(manager_dir, "queue.json"),
        reviews_dir=os.path.join(manager_dir, "reviews"),
        history_dir=history_dir,
        checkpoint_path=os.path.join(root, ".agent", "building", "checkpoint.json"),
        config_path=os.path.join(manager_dir, "config.json"),
    )
    return out_path


def cycle(root, prev):
    cur = snapshot(root)
    if not should_rebuild(prev, cur):
        return cur, False
    out_path = rebuild(root)
    print(f"[watch] rebuilt -> {out_path}")
    return cur, True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Watch .agent/**/tool-calls.jsonl + events.jsonl, rebuild dashboard/data.json on change")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help="Poll interval in seconds (default 2.0)")
    parser.add_argument("--once", action="store_true",
                        help="Run a single check cycle and exit")
    parser.add_argument("--root", default=os.getcwd(),
                        help="Project root to watch (default: cwd)")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    prev = None
    if args.once:
        cycle(root, prev)
        return 0
    print(f"[watch] polling {root} every {args.interval}s (Ctrl+C to stop)")
    try:
        while True:
            try:
                prev, _ = cycle(root, prev)
            except Exception as exc:
                print(f"[watch] cycle failed: {exc}", file=sys.stderr)
            time.sleep(max(0.0, args.interval))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
