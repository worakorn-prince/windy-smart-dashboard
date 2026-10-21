"""Token/cost analytics per model from .agent JSONL logs.

Scans ``<root>/.agent/**/tool-calls.jsonl`` and ``.agent/**/events.jsonl`` for
rows that carry both a model name and token counts. Rows without model/tokens
(or malformed lines) are skipped quietly and counted in ``skipped``.

Usage:
    python scripts/cost.py --root <dir> [--pricing prices.json]
                           [--budget <usd>] [--json]

Exit codes: 0 = ok / within budget, 1 = budget exceeded, 2 = invalid input.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

AGENT_DIR = ".agent"
LOG_NAMES = ("tool-calls.jsonl", "events.jsonl")
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}

MODEL_KEYS = ("model", "model_id", "model_name")
TOKEN_IN_KEYS = ("tokens_in", "input_tokens", "prompt_tokens")
TOKEN_OUT_KEYS = ("tokens_out", "output_tokens", "completion_tokens")

DEFAULT_PRICING = {
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4": (3.00, 15.00),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "deepseek-v3": (0.27, 1.10),
    "deepseek-v4.1-flash": (0.0, 0.0),
    "deepseek-v4.1-flash-free": (0.0, 0.0),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
}


class CostInputError(ValueError):
    pass


class PricingError(CostInputError):
    pass


def _to_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("_", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        if number < 0 or not number.is_integer():
            return None
        return int(number)
    return None


def _normalize_model(model):
    return str(model).strip().lower()


def _basename(model):
    return _normalize_model(model).rsplit("/", 1)[-1]


def _coerce_price(value, model):
    if isinstance(value, dict):
        price_in = value.get("input", value.get("input_per_1m", value.get("in")))
        price_out = value.get("output", value.get("output_per_1m", value.get("out")))
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        price_in, price_out = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        price_in = price_out = value
    else:
        raise PricingError(
            "pricing for model %r must be a number, [input, output], "
            "or an object with input/output" % model)
    numbers = []
    for name, number in (("input", price_in), ("output", price_out)):
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(float(number)) or float(number) < 0:
            raise PricingError(
                "pricing %s for model %r must be a non-negative number"
                % (name, model))
        numbers.append(float(number))
    return numbers[0], numbers[1]


def load_pricing(path):
    if path is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise PricingError("cannot read pricing file %s: %s" % (path, exc)) from exc
    except ValueError as exc:
        raise PricingError("invalid pricing JSON %s: %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise PricingError("pricing file %s must contain a JSON object" % path)
    return {str(model): _coerce_price(value, model)
            for model, value in data.items()}


def _pricing_lookup(table):
    lookup = {}
    for model, price in table.items():
        pair = _coerce_price(price, model)
        lookup[_normalize_model(model)] = pair
        lookup.setdefault(_basename(model), pair)
    return lookup


def resolve_price(model, lookup):
    key = _normalize_model(model)
    if not key:
        return None
    if key in lookup:
        return lookup[key]
    base = _basename(key)
    if base in lookup:
        return lookup[base]
    candidates = [name for name in lookup
                  if base.startswith(name + "-") or base.startswith(name + ".")]
    if candidates:
        return lookup[max(candidates, key=len)]
    return None


def _extract_row(row):
    model = None
    for key in MODEL_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            model = value.strip()
            break
    if model is None:
        return None
    tokens_in = tokens_out = 0
    found = False
    for key in TOKEN_IN_KEYS:
        if key in row:
            parsed = _to_int(row.get(key))
            if parsed is not None:
                tokens_in = parsed
                found = True
                break
    for key in TOKEN_OUT_KEYS:
        if key in row:
            parsed = _to_int(row.get(key))
            if parsed is not None:
                tokens_out = parsed
                found = True
                break
    if not found:
        return None
    return model, tokens_in, tokens_out


def iter_log_files(root):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise CostInputError("root is not a directory: %s" % root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        parts = os.path.normpath(dirpath).split(os.sep)
        if AGENT_DIR not in parts:
            continue
        for name in sorted(filenames):
            if name in LOG_NAMES:
                yield os.path.join(dirpath, name)


def _iter_rows(path, stats):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    stats["skipped"] += 1
                    continue
                if not isinstance(row, dict):
                    stats["skipped"] += 1
                    continue
                yield row
    except (OSError, UnicodeDecodeError):
        stats["skipped"] += 1


def aggregate(root, pricing=None):
    root = os.path.abspath(root)
    table = dict(DEFAULT_PRICING)
    if pricing:
        table.update(pricing)
    lookup = _pricing_lookup(table)

    models = {}
    stats = {"skipped": 0}
    files_read = 0
    for path in iter_log_files(root):
        files_read += 1
        for row in _iter_rows(path, stats):
            extracted = _extract_row(row)
            if extracted is None:
                stats["skipped"] += 1
                continue
            model, tokens_in, tokens_out = extracted
            price = resolve_price(model, lookup)
            entry = models.get(model)
            if entry is None:
                entry = {
                    "model": model,
                    "calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "tokens_total": 0,
                    "est_cost_usd": 0.0 if price is not None else None,
                }
                models[model] = entry
            entry["calls"] += 1
            entry["tokens_in"] += tokens_in
            entry["tokens_out"] += tokens_out
            entry["tokens_total"] += tokens_in + tokens_out
            if entry["est_cost_usd"] is not None and price is not None:
                entry["est_cost_usd"] += (
                    tokens_in / 1_000_000.0 * price[0]
                    + tokens_out / 1_000_000.0 * price[1]
                )

    rows = [models[name] for name in sorted(models, key=str.lower)]
    unknown_models = [row["model"] for row in rows
                      if row["est_cost_usd"] is None]
    known_costs = [row["est_cost_usd"] for row in rows
                   if row["est_cost_usd"] is not None]
    total = {
        "calls": sum(row["calls"] for row in rows),
        "tokens_in": sum(row["tokens_in"] for row in rows),
        "tokens_out": sum(row["tokens_out"] for row in rows),
        "tokens_total": sum(row["tokens_total"] for row in rows),
        "est_cost_usd": (sum(known_costs) if known_costs else
                         (None if rows else 0.0)),
        "unknown_models": unknown_models,
        "partial_cost": bool(unknown_models),
    }
    return {
        "root": root,
        "models": rows,
        "total": total,
        "skipped": stats["skipped"],
        "files_read": files_read,
    }


def _format_cost(value):
    if value is None:
        return "unknown pricing"
    return "$%.6f" % value


def format_table(result):
    lines = [
        "| Model | Calls | Tokens | Est. cost (USD) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in result["models"]:
        model = row["model"].replace("|", "\\|")
        lines.append("| %s | %d | %s | %s |" % (
            model, row["calls"], format(row["tokens_total"], ","),
            _format_cost(row["est_cost_usd"])))
    total = result["total"]
    total_cost = _format_cost(total["est_cost_usd"])
    if total["est_cost_usd"] is not None and total["partial_cost"]:
        total_cost += " (partial)"
    lines.append("| **TOTAL** | %d | %s | %s |" % (
        total["calls"], format(total["tokens_total"], ","), total_cost))
    if result["skipped"]:
        lines.append("")
        lines.append("Skipped rows without model/tokens: %d" % result["skipped"])
    return "\n".join(lines)


def _budget_verdict(total, budget):
    if budget is None:
        return False, None
    cost = total["est_cost_usd"]
    if cost is None:
        return False, ("**BUDGET CHECK**: est. cost unknown (no known pricing) "
                       "for budget $%.2f" % budget)
    if cost > budget:
        return True, ("**BUDGET EXCEEDED**: est. cost %s > budget $%.2f"
                      % (_format_cost(cost), budget))
    if total["partial_cost"]:
        return False, ("**BUDGET CHECK**: est. cost %s is partial (unknown "
                       "models) and within budget $%.2f"
                       % (_format_cost(cost), budget))
    return False, None


def build_payload(root, pricing=None, budget=None):
    result = aggregate(root, pricing=pricing)
    exceeded, warning = _budget_verdict(result["total"], budget)
    return {
        "root": result["root"],
        "models": result["models"],
        "total": result["total"],
        "skipped": result["skipped"],
        "budget_usd": budget,
        "budget_exceeded": exceeded,
    }, warning


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Token/cost analytics per model from .agent JSONL logs")
    parser.add_argument("--root", required=True,
                        help="project root containing .agent/**/*.jsonl")
    parser.add_argument("--pricing", default=None,
                        help="JSON file overriding built-in model prices")
    parser.add_argument("--budget", type=float, default=None,
                        help="budget in USD; exit 1 when est. cost exceeds it")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit a JSON payload instead of a markdown table")
    args = parser.parse_args(argv)

    if args.budget is not None and (not math.isfinite(args.budget)
                                    or args.budget < 0):
        print("error: --budget must be a finite non-negative number",
              file=sys.stderr)
        return 2
    try:
        pricing = load_pricing(args.pricing)
        payload, warning = build_payload(args.root, pricing=pricing,
                                         budget=args.budget)
    except CostInputError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_table(payload))
        if warning:
            print("")
            print(warning)
    return 1 if payload["budget_exceeded"] else 0


if __name__ == "__main__":
    sys.exit(main())
