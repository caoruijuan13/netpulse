#!/usr/bin/env python3
"""Build frozen formal-v2 windows and evaluate simple RTT-P95 baselines.

The script reads only D1-D2 train and D3 validation selections. It never loads
the D4 held-out selection. Output files are derived artifacts under data/.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SELECTIONS = (
    ("train", "D1", "data/load/fixed-formal-v2-d1-05-08-20261024T050624Z-XcWQ7h/selection.json"),
    ("train", "D2", "data/load/fixed-formal-v2-d2-05-08-20261025T102708Z-aRoIoF/selection.json"),
    ("validation", "D3", "data/load/fixed-formal-v2-d3-05-08-20261026T111750Z-jsyVJc/selection.json"),
)
EXPERIMENT_ID = "mac-mac-iperf3-fixed-v2"
WINDOW_SIZE = 60
STRIDE = 10
MIN_SUCCESS = 57
TARGET_PERCENTILE = 0.95
RIDGE_ALPHA = 1.0
RIDGE_FEATURES = (
    "baseline_history_p95_ms",
    "baseline_history_mean_ms",
    "history_ok_count",
    "history_timeout_count",
    "history_ping_process_timeout_count",
    "history_other_send_error_count",
)


def nearest_rank(values: list[float], percentile: float = TARGET_PERCENTILE) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("nearest-rank percentile requires at least one value")
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def load_selected_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    seen_session_ids: set[str] = set()
    for expected_split, expected_day, relative_path in SELECTIONS:
        selection_path = ROOT / relative_path
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if (
            selection.get("experiment_id") != EXPERIMENT_ID
            or selection.get("status") != "accepted_after_audit"
            or selection.get("split") != expected_split
        ):
            raise ValueError(f"Unexpected or unaccepted split manifest: {selection_path}")
        selected = selection.get("selected_sessions", {})
        expected_slots = {f"{expected_day}-{i:02d}" for i in range(1, 9)}
        if set(selected) != expected_slots:
            raise ValueError(f"{expected_day} selection is incomplete: {selection_path}")
        for slot_id, choice in selected.items():
            session_id = choice["session_id"]
            if session_id in seen_session_ids:
                raise ValueError(f"Session appears in more than one split: {session_id}")
            seen_session_ids.add(session_id)
            session_dir = ROOT / "data/raw" / session_id
            metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            if (
                metadata.get("session_id") != session_id
                or metadata.get("experiment_id") != EXPERIMENT_ID
                or metadata.get("experiment_status") != "frozen"
                or metadata.get("run_status") != "completed"
                or metadata.get("scenario") != choice.get("scenario")
                or f"slot_id={slot_id}" not in (metadata.get("environment_notes") or "")
            ):
                raise ValueError(f"Session does not match its accepted slot: {session_id}")
            rows = [
                json.loads(line)
                for line in (session_dir / "probes.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            validate_session(metadata, rows, session_id)
            sessions.append(
                {
                    "split": expected_split,
                    "day": expected_day,
                    "slot_id": slot_id,
                    "scenario": choice["scenario"],
                    "session_id": session_id,
                    "metadata": metadata,
                    "probes": rows,
                }
            )
    return sessions


def validate_session(metadata: dict[str, Any], probes: list[dict[str, Any]], session_id: str) -> None:
    if len(probes) != 900 or [row.get("probe_seq") for row in probes] != list(range(900)):
        raise ValueError(f"Expected 900 ordered probe slots: {session_id}")
    if any(row.get("session_id") != session_id for row in probes):
        raise ValueError(f"Probe session IDs do not match: {session_id}")
    if any(row.get("status") == "missed_slot" for row in probes):
        raise ValueError(f"Session contains a missed slot: {session_id}")
    start = datetime.fromisoformat(metadata["started_at_utc"])
    end = datetime.fromisoformat(metadata["ended_at_utc"])
    if abs((end - start).total_seconds() - 900) > 2:
        raise ValueError(f"Session duration differs from 900 seconds: {session_id}")
    previous: tuple[datetime, int] | None = None
    for row in probes:
        if row.get("started_at_utc") is None or row.get("started_monotonic_ns") is None:
            continue
        current = (datetime.fromisoformat(row["started_at_utc"]), row["started_monotonic_ns"])
        if previous is not None:
            utc_step = (current[0] - previous[0]).total_seconds()
            monotonic_step = (current[1] - previous[1]) / 1_000_000_000
            if abs(utc_step - monotonic_step) > 2:
                raise ValueError(f"UTC/monotonic discontinuity in {session_id}")
        previous = current


def build_windows(session: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    probes = session["probes"]
    candidates = 0
    fully_observed = 0
    windows: list[dict[str, Any]] = []
    for start in range(0, len(probes) - 2 * WINDOW_SIZE + 1, STRIDE):
        candidates += 1
        history = probes[start : start + WINDOW_SIZE]
        future = probes[start + WINDOW_SIZE : start + 2 * WINDOW_SIZE]
        history_ok = [row["rtt_ms"] for row in history if row["status"] == "ok"]
        future_ok = [row["rtt_ms"] for row in future if row["status"] == "ok"]
        if len(history_ok) == WINDOW_SIZE and len(future_ok) == WINDOW_SIZE:
            fully_observed += 1
        if len(history_ok) < MIN_SUCCESS or len(future_ok) < MIN_SUCCESS:
            continue
        windows.append(
            {
                "split": session["split"],
                "day": session["day"],
                "slot_id": session["slot_id"],
                "session_id": session["session_id"],
                "scenario": session["scenario"],
                "history_start_probe_seq": start,
                "history_end_probe_seq": start + WINDOW_SIZE - 1,
                "target_start_probe_seq": start + WINDOW_SIZE,
                "target_end_probe_seq": start + 2 * WINDOW_SIZE - 1,
                "history_ok_count": len(history_ok),
                "history_timeout_count": sum(row["status"] == "timeout" for row in history),
                "history_ping_process_timeout_count": sum(
                    row["error_code"] == "ping_process_timeout" for row in history
                ),
                "history_other_send_error_count": sum(
                    row["status"] == "send_error" and row["error_code"] != "ping_process_timeout"
                    for row in history
                ),
                "target_ok_count": len(future_ok),
                "target_p95_ms": nearest_rank(future_ok),
                "baseline_history_p95_ms": nearest_rank(history_ok),
                "baseline_history_mean_ms": statistics.fmean(history_ok),
            }
        )
    return windows, candidates, fully_observed


def p95_abs_error(errors: list[float]) -> float:
    return nearest_rank(errors, 0.95)


def metrics_for(windows: list[dict[str, Any]]) -> dict[str, Any]:
    by_session: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in windows:
        by_session[(row["split"], row["day"], row["session_id"])].append(row)
    session_metrics: list[dict[str, Any]] = []
    for (split, day, session_id), rows in sorted(by_session.items()):
        first = rows[0]
        item: dict[str, Any] = {
            "split": split,
            "day": day,
            "slot_id": first["slot_id"],
            "session_id": session_id,
            "scenario": first["scenario"],
            "valid_windows": len(rows),
        }
        for name, prediction_key in (
            ("history_p95", "baseline_history_p95_ms"),
            ("history_mean", "baseline_history_mean_ms"),
            ("ridge", "ridge_prediction_ms"),
        ):
            errors = [row[prediction_key] - row["target_p95_ms"] for row in rows]
            absolute = [abs(error) for error in errors]
            item[f"{name}_mae_ms"] = statistics.fmean(absolute)
            item[f"{name}_signed_bias_ms"] = statistics.fmean(errors)
            item[f"{name}_p95_absolute_error_ms"] = p95_abs_error(absolute)
        session_metrics.append(item)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in session_metrics:
        groups[(item["split"], item["scenario"])].append(item)
    scenario_metrics: list[dict[str, Any]] = []
    for (split, scenario), items in sorted(groups.items()):
        out: dict[str, Any] = {"split": split, "scenario": scenario, "sessions": len(items)}
        for name in ("history_p95", "history_mean", "ridge"):
            for metric in ("mae_ms", "signed_bias_ms", "p95_absolute_error_ms"):
                key = f"{name}_{metric}"
                out[key] = statistics.fmean(item[key] for item in items)
        scenario_metrics.append(out)
    splits = sorted({item["split"] for item in session_metrics})
    overall: list[dict[str, Any]] = []
    for split in splits:
        items = [item for item in session_metrics if item["split"] == split]
        out = {"split": split, "sessions": len(items)}
        for name in ("history_p95", "history_mean", "ridge"):
            for metric in ("mae_ms", "signed_bias_ms", "p95_absolute_error_ms"):
                key = f"{name}_{metric}"
                out[key] = statistics.fmean(item[key] for item in items)
        overall.append(out)
    return {"per_session": session_metrics, "per_scenario_session_equal": scenario_metrics, "overall_session_equal": overall}


def fit_ridge(train_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit a small standardized ridge regressor using training rows only."""
    if not train_rows:
        raise ValueError("Ridge regression requires training windows")
    train_x = [[float(row[name]) for name in RIDGE_FEATURES] for row in train_rows]
    means = [statistics.fmean(column) for column in zip(*train_x)]
    scales = [statistics.pstdev(column) or 1.0 for column in zip(*train_x)]
    train_z = [[(value - mean) / scale for value, mean, scale in zip(x, means, scales)] for x in train_x]
    targets = [float(row["target_p95_ms"]) for row in train_rows]
    intercept = statistics.fmean(targets)
    centered_y = [value - intercept for value in targets]
    coefficients = [0.0] * len(RIDGE_FEATURES)
    fitted = [0.0] * len(train_z)
    for _ in range(5000):
        max_change = 0.0
        for column in range(len(RIDGE_FEATURES)):
            numerator = sum(
                x[column] * (target - prediction + coefficients[column] * x[column])
                for x, target, prediction in zip(train_z, centered_y, fitted)
            )
            denominator = sum(x[column] ** 2 for x in train_z) + RIDGE_ALPHA
            updated = numerator / denominator
            change = updated - coefficients[column]
            if change:
                for index, x in enumerate(train_z):
                    fitted[index] += change * x[column]
            coefficients[column] = updated
            max_change = max(max_change, abs(change))
        if max_change < 1e-8:
            break

    for row in rows:
        standardized = [
            (float(row[name]) - mean) / scale
            for name, mean, scale in zip(RIDGE_FEATURES, means, scales)
        ]
        row["ridge_prediction_ms"] = intercept + sum(
            coefficient * value for coefficient, value in zip(coefficients, standardized)
        )
    return {
        "model": "Ridge linear regression",
        "alpha": RIDGE_ALPHA,
        "features": list(RIDGE_FEATURES),
        "scenario_label_used_as_feature": False,
        "fit_on_split": "train",
        "fit_window_count": len(train_rows),
        "fit_session_ids": sorted({row["session_id"] for row in train_rows}),
        "standardization_means": dict(zip(RIDGE_FEATURES, means)),
        "standardization_scales": dict(zip(RIDGE_FEATURES, scales)),
        "intercept_ms": intercept,
        "coefficients": dict(zip(RIDGE_FEATURES, coefficients)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    sessions = load_selected_sessions()
    all_windows: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for session in sessions:
        windows, candidates, fully_observed = build_windows(session)
        all_windows.extend(windows)
        metadata = session["metadata"]
        status_counts = metadata["probe_counts"]
        coverage.append(
            {
                "split": session["split"],
                "day": session["day"],
                "slot_id": session["slot_id"],
                "session_id": session["session_id"],
                "scenario": session["scenario"],
                "candidate_windows": candidates,
                "valid_windows": len(windows),
                "valid_window_coverage": len(windows) / candidates,
                "fully_observed_windows": fully_observed,
                "fully_observed_window_coverage": fully_observed / candidates,
                "probe_counts": status_counts,
                "timeout_rate": status_counts.get("timeout", 0) / len(session["probes"]),
                "ping_process_timeout_rate": sum(
                    row["error_code"] == "ping_process_timeout" for row in session["probes"]
                ) / len(session["probes"]),
            }
        )
    if not all_windows:
        raise SystemExit("No valid windows were built")
    train_rows = [row for row in all_windows if row["split"] == "train"]
    ridge_model = fit_ridge(train_rows, all_windows)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or ROOT / "data/derived" / f"formal-v2-baselines-{stamp}"
    output_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=False)
    window_path = output_dir / "windows.csv"
    with window_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_windows[0]))
        writer.writeheader()
        writer.writerows(all_windows)
    result = {
        "experiment_id": EXPERIMENT_ID,
        "window_policy": {
            "history_slots": WINDOW_SIZE,
            "future_slots": WINDOW_SIZE,
            "stride_slots": STRIDE,
            "minimum_successful_probes_per_side": MIN_SUCCESS,
            "target": "nearest-rank P95 of successful RTTs in the future window (ms)",
            "d4_accessed": False,
        },
        "sessions": {split: sum(item["split"] == split for item in sessions) for split in ("train", "validation")},
        "windows": {split: sum(row["split"] == split for row in all_windows) for split in ("train", "validation")},
        "coverage": coverage,
        "metrics": metrics_for(all_windows),
        "ridge_model": ridge_model,
        "baseline_definitions": {
            "history_p95": "Predict future 60-slot RTT P95 with the nearest-rank P95 of successful RTTs in the previous 60 slots (primary frozen baseline).",
            "history_mean": "Predict with the arithmetic mean of successful RTTs in the previous 60 slots (secondary baseline).",
            "ridge": "Ridge linear regression trained on D1-D2 windows, using only previous-window P95, mean, successful-probe count, timeout count, ping-process-timeout count, and other send-error count.",
        },
        "aggregation": "Compute metrics per session first, then average sessions equally; overlapping windows are not independent replicates.",
    }
    (output_dir / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output_dir / "ridge_model.json").write_text(json.dumps(ridge_model, indent=2) + "\n", encoding="utf-8")
    validation_rows = [
        row for row in result["metrics"]["per_scenario_session_equal"] if row["split"] == "validation"
    ]
    validation_coverage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in coverage:
        if item["split"] == "validation":
            validation_coverage[item["scenario"]].append(item)
    report = [
        "# Formal v2 Baseline Evaluation",
        "",
        "This report uses D1-D2 for the train split and D3 for validation. The D4 held-out selection was not read.",
        "All metrics are descriptive; windows overlap, so sessions are the aggregation unit.",
        "",
        "## Overall",
        "",
        "| Split | Sessions | Valid windows | History P95 MAE (ms) | History mean MAE (ms) | Ridge MAE (ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in result["metrics"]["overall_session_equal"]:
        report.append(
            f"| {row['split']} | {result['sessions'][row['split']]} | {result['windows'][row['split']]} | "
            f"{row['history_p95_mae_ms']:.2f} | {row['history_mean_mae_ms']:.2f} | {row['ridge_mae_ms']:.2f} |"
        )
    report.extend(
        [
            "",
            "## Validation by scenario",
            "",
            "| Scenario | Sessions | Valid windows | Fully observed windows | History P95 MAE (ms) | History mean MAE (ms) | Ridge MAE (ms) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in validation_rows:
        cov = validation_coverage[row["scenario"]]
        report.append(
            f"| {row['scenario']} | {row['sessions']} | "
            f"{sum(x['valid_windows'] for x in cov)} | {sum(x['fully_observed_windows'] for x in cov)} | "
            f"{row['history_p95_mae_ms']:.2f} | {row['history_mean_mae_ms']:.2f} | {row['ridge_mae_ms']:.2f} |"
        )
    report.extend(
        [
            "",
            "The history-P95 baseline is the frozen primary baseline; history mean is secondary. Ridge uses only D1-D2 fit statistics and past-window features, without scenario labels.",
            "These results do not authorize model tuning on D4; D4 remains the final held-out set.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Output: {output_dir}")
    print(f"Train: {result['sessions']['train']} sessions, {result['windows']['train']} valid windows")
    print(f"Validation: {result['sessions']['validation']} sessions, {result['windows']['validation']} valid windows")
    print("D4 held-out selection was not read.")
    for row in result["metrics"]["overall_session_equal"]:
        print(
            f"{row['split']}: history-P95 MAE={row['history_p95_mae_ms']:.3f} ms, "
            f"history-mean MAE={row['history_mean_mae_ms']:.3f} ms, "
            f"ridge MAE={row['ridge_mae_ms']:.3f} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
