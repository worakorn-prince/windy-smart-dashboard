"""Baseline profile + anomaly detection over the metrics history DB.

Read-only consumer of the ``samples`` table owned by history.py: it never
writes and holds the shared connection lock only for the duration of one
SELECT. Baselines are per-metric hourly profiles (mean ± k·std per hour of
day) with a flat mean±std fallback when the retained history is too short to
trust an hourly split (retention is ~10 h, so a fresh install may hold well
under an hour of data). A sample is anomalous when |z| ≥ Z_THRESHOLD for
RUN_LENGTH consecutive samples; only a run that still extends to the most
recent sample is reported, so an episode clears once the metric returns
inside its band.
"""
from __future__ import annotations

import time
from datetime import datetime
from statistics import fmean, pstdev
from typing import Any

import history

# Hourly profiles use the machine's local time so the baseline reflects the
# user's local usage pattern (dashboard is local-only).
LOCAL_TZ = datetime.now().astimezone().tzinfo

RANGES: dict[str, int] = {"24h": 86_400, "7d": 604_800, "30d": 2_592_000}

# Classic load-spike signals; sensor-dependent columns (gpu_temp, disk_temp_max,
# cpu/gpu_power_w) are skipped because they are frequently NULL and would only
# contribute empty baselines.
METRICS: tuple[str, ...] = (
    "cpu_pct",
    "ram_pct",
    "swap_pct",
    "cpu_temp",
    "net_sent_bps",
    "net_recv_bps",
    "disk_read_bps",
    "disk_write_bps",
)

Z_THRESHOLD = 3.0
RUN_LENGTH = 3
MIN_BASELINE_SAMPLES = 120
MIN_PROFILE_HOURS = 6
MIN_HOURLY_SAMPLES = 20
MIN_STD_ABS = 0.5
MIN_STD_REL = 0.02
ANOMALY_LIMIT = 50


def _effective_std(std: float, mean: float) -> float:
    return max(std, MIN_STD_ABS, MIN_STD_REL * abs(mean))


def _round(value: float) -> float:
    return round(float(value), 2)


def _band(mean: float, std: float, n: int) -> dict[str, Any]:
    return {
        "n": n,
        "mean": _round(mean),
        "std": _round(std),
        "lo": _round(mean - Z_THRESHOLD * std),
        "hi": _round(mean + Z_THRESHOLD * std),
    }


def _load_samples(since: float) -> list[dict[str, Any]]:
    wanted = ["ts", *METRICS]
    with history._lock:
        conn = history._get_conn()
        existing = {r[1] for r in conn.execute("PRAGMA table_info(samples)")}
        cols = [c for c in wanted if c == "ts" or c in existing]
        rows = conn.execute(
            f"SELECT {', '.join(cols)} FROM samples WHERE ts >= ? ORDER BY ts",
            (since,),
        ).fetchall()
    return [dict(zip(cols, row, strict=True)) for row in rows]


def _build_baseline(samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    pairs_by_metric: dict[str, list[tuple[float, float]]] = {m: [] for m in METRICS}
    for sample in samples:
        ts = sample["ts"]
        for metric in METRICS:
            value = sample.get(metric)
            if value is not None:
                pairs_by_metric[metric].append((ts, float(value)))

    baseline: dict[str, dict[str, Any]] = {}
    for metric, pairs in pairs_by_metric.items():
        if not pairs:
            continue
        values = [v for _, v in pairs]
        mean = fmean(values)
        std = _effective_std(pstdev(values) if len(values) > 1 else 0.0, mean)
        profile: dict[str, Any] = {"mode": "flat", "hours": {}, **_band(mean, std, len(values))}

        hourly: dict[int, list[float]] = {}
        for ts, value in pairs:
            hourly.setdefault(datetime.fromtimestamp(ts, tz=LOCAL_TZ).hour, []).append(value)
        profiled = {h: vals for h, vals in hourly.items() if len(vals) >= MIN_HOURLY_SAMPLES}
        if len(values) >= MIN_BASELINE_SAMPLES and len(profiled) >= MIN_PROFILE_HOURS:
            hours: dict[str, dict[str, Any]] = {}
            for hour in sorted(profiled):
                vals = profiled[hour]
                hour_mean = fmean(vals)
                hour_std = _effective_std(pstdev(vals) if len(vals) > 1 else 0.0, hour_mean)
                hours[str(hour)] = _band(hour_mean, hour_std, len(vals))
            profile["mode"] = "hourly"
            profile["hours"] = hours
        baseline[metric] = profile
    return baseline


def _zscore(ts: float, value: float, profile: dict[str, Any]) -> tuple[float, float]:
    band: dict[str, Any] = profile
    if profile["mode"] == "hourly":
        band = profile["hours"].get(str(datetime.fromtimestamp(ts, tz=LOCAL_TZ).hour), profile)
    mean = float(band["mean"])
    std = float(band["std"])
    if std <= 0.0:
        return 0.0, mean
    return (value - mean) / std, mean


def _detect(
    samples: list[dict[str, Any]],
    baseline: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    series: dict[str, list[tuple[float, float]]] = {m: [] for m in METRICS}
    for sample in samples:
        ts = sample["ts"]
        for metric in METRICS:
            value = sample.get(metric)
            if value is not None:
                series[metric].append((ts, float(value)))

    entries: list[dict[str, Any]] = []
    for metric in METRICS:
        pairs = series[metric]
        profile = baseline.get(metric)
        if not pairs or profile is None:
            continue
        streak = 0
        first: tuple[float, float, float, float] | None = None
        for ts, value in pairs:
            z, expected = _zscore(ts, value, profile)
            if abs(z) >= Z_THRESHOLD:
                if streak == 0:
                    first = (ts, value, expected, z)
                streak += 1
            else:
                streak = 0
                first = None
        if streak >= RUN_LENGTH and first is not None:
            ts, value, expected, z = first
            entries.append({
                "metric": metric,
                "ts": ts,
                "value": _round(value),
                "expected": _round(expected),
                "z": _round(z),
                "direction": "high" if z > 0 else "low",
                "run_len": streak,
            })
    entries.sort(key=lambda e: e["ts"], reverse=True)
    return entries[:ANOMALY_LIMIT]


def compute_anomalies(range_str: str = "24h") -> dict[str, Any]:
    """Baseline profiles plus ongoing anomalies for ``24h|7d|30d`` (read-only)."""
    if range_str not in RANGES:
        raise ValueError(f"range must be one of {sorted(RANGES)}")
    since = time.time() - RANGES[range_str]
    samples = _load_samples(since)
    baseline = _build_baseline(samples)
    return {
        "range": range_str,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "n_samples": len(samples),
        "baseline": baseline,
        "anomalies": _detect(samples, baseline),
    }
