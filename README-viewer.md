# Agent Observability Dashboard

File-based observability dashboards (pure Python stdlib — no `pip install`)
for AI-agent tool-call / session / review history, across projects.
Works with any harness or framework — just write logs in the schema below.

## Get started in 2 steps (after cloning)

```bat
python scripts\bootstrap.py --demo
run_dashboard.bat
```
(On macOS/Linux use `sh run_dashboard.sh` for the second step.)

- `--demo` seeds sample data first → the browser opens with charts populated
- If real data already exists (`./.agent/`), drop `--demo` (the script never touches existing files)
- The browser opens the **combined view** (`dashboard/all.html`); the
  **single-project view** is `dashboard/index.html`

## Manual run (without the one-click script)

```powershell
python scripts/metrics.py --rebuild   # compute from .agent/manager/*.jsonl
python scripts/export_json.py         # → dashboard/data.json (single view)
python scripts/aggregate.py           # → dashboard/all-projects.json (combined view)
python -m http.server                 # open dashboard/*.html over http (do not open file:// directly, fetch gets blocked)
```

## Log schema (the only contract to follow)

**`./.agent/manager/tool-calls.jsonl`** — one JSON object per line:
```json
{"time": "2026-09-14T08:00:00+00:00", "task": "TASK-1", "attempt": 1,
 "session_id": "ses-1", "agent": "builder", "operation": "CALL",
 "tool": "Read", "duration_ms": 45, "status": "ok", "error": null,
 "prompt_hash": "-", "tokens_in": 800, "tokens_out": 200}
```
`agent` can be anything (`builder`, `planner`, `my-bot` — shown as-is),
recommended `operation`: `DISPATCH|CALL|RESULT`,
recommended `status`: `ok|error|blocked|limit`

**`./.agent/manager/events.jsonl`** — any rows with `time/event/task`:
```json
{"time": "...", "event": "TASK_DONE", "task": "TASK-1"}
```
Events the dashboards understand: `TASK_CREATED`,
`WORKER_STARTED/WORKER_RESUMED` (session counts), `RECOVERY_STARTED`,
`REVIEW_FAILED/REVIEW_PASSED`, `TASK_DONE/TASK_FAILED/TASK_CANCELLED`.
Unknown event names are skipped safely.

Log from any language — only the file format above matters — then run the
same 3 commands and the dashboards light up.

## File layout

```text
scripts/
  manager.py         # Optional Python logging API (log_tool_call / save_review)
  metrics.py         # 6 metrics + daily history/ snapshots
  export_json.py     # metrics+events → dashboard/data.json (15 sections)
  aggregate.py       # cross-project merge → dashboard/all-projects.json (--projects A,B,C)
  tools_inventory.py # 16-tool catalog x agent permissions (optional) x actual usage
  bootstrap.py       # init .agent/ skeleton (+ --demo sample data)
  watch.py           # live tail: rebuild dashboard/data.json when JSONL changes
  compare.py         # base vs candidate run comparison (regression gate)
  cost.py            # token/cost per model (+ --budget gate)
  retention.py       # archive old JSONL rows to .agent/archive/
  test_logging.py    # 32 tests
dashboard/
  index.html         # single-project view (5 charts + 17 tables)
  all.html           # cross-project view (6 charts + 20 tables)
```

## Live tail

`watch.py` polls `.agent/**/tool-calls.jsonl` and `events.jsonl` and rebuilds
`dashboard/data.json` whenever a file changes (default every 2 s):

```powershell
python scripts/watch.py --root . --interval 2   # Ctrl+C to stop
python scripts/watch.py --root . --once         # single check cycle, then exit
```

Open `dashboard/index.html?auto=1` — the header shows a **LIVE** badge and the
page refreshes every 5 s. Without `auto=1` the page loads data once.

## Run comparison

`compare.py` diffs two runs (base vs candidate) and prints a markdown table
(or `--json`). A regression makes the process **exit 1**, so it can gate CI:

```powershell
python scripts/compare.py --base .\runs\before --cand .\runs\after
python scripts/compare.py --base .\runs\before --cand .\runs\after --json
```

`--base`/`--cand` accept a project dir containing `.agent/` (metrics.json or
tool-calls.jsonl) — exit code 2 means invalid/missing input.

## Cost analytics

`cost.py` aggregates tokens and estimated USD cost per model, with an optional
budget gate:

```powershell
python scripts/cost.py --root . --budget 5
python scripts/cost.py --root . --pricing prices.json --json
```

Exit codes: `0` within budget, `1` budget exceeded, `2` invalid input. The
`--pricing` file overrides the built-in per-model price table.

## Retention

`retention.py` moves rows older than `--days` into
`.agent/archive/<stem>-<YYYYMMDD>.jsonl` and rewrites the source file; rows
without a parseable timestamp are always kept. Preview first with `--dry-run`:

```powershell
python scripts/retention.py --root . --days 30 --dry-run
python scripts/retention.py --root . --days 30
```

The backend history DB has its own pruner (default 30 days):

```powershell
python backend/history.py prune --days 30
```

## Tool permission tables (optional)

With agent capability manifests (a folder of `.md` files containing a
`permission:` block mapping `tool → allow/deny` per agent), the dashboards
render a "tool × agent (allowed/denied/actually used)" matrix.
Without manifests that section stays empty — actual usage still shows fully.

Run tests: `python -m unittest discover -s scripts -p "test_logging.py"`

CI: `.github/workflows/ci.yml` runs the viewer logging tests (`python
scripts/test_logging.py`) on every push/PR to `master`, alongside the
backend pytest suite and the frontend build.
