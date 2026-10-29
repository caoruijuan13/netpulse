#!/usr/bin/env python3
"""Run the frozen formal-v2 model once on the D4 held-out sessions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_formal_v2_baselines as pipeline  # noqa: E402

DEFAULT_ANALYSIS = ROOT / "data/derived/formal-v2-baselines-20261029T092529Z"
DEFAULT_TEST_SELECTION = ROOT / "data/load/fixed-formal-v2-d4-07-retry-20261027T104537Z-DIqpPI/selection.json"
DEFAULT_OUTPUT = ROOT / "data/derived/formal-v2-final-test-D4"


def read_test_sessions(selection_path: Path) -> list[dict[str, Any]]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (
        selection.get("experiment_id") != pipeline.EXPERIMENT_ID
        or selection.get("status") != "accepted_after_audit"
        or selection.get("split") != "test"
    ):
        raise ValueError(f"D4 is not an accepted held-out selection: {selection_path}")
    selected = selection.get("selected_sessions", {})
    expected_slots = {f"D4-{i:02d}" for i in range(1, 9)}
    if set(selected) != expected_slots:
        raise ValueError("D4 held-out selection must contain all eight slots")
    sessions = []
    for slot_id, choice in selected.items():
        session_id = choice["session_id"]
        session_dir = ROOT / "data/raw" / session_id
        metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
        probes = [
            json.loads(line)
            for line in (session_dir / "probes.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if (
            metadata.get("experiment_id") != pipeline.EXPERIMENT_ID
            or metadata.get("experiment_status") != "frozen"
            or metadata.get("run_status") != "completed"
            or metadata.get("scenario") != choice.get("scenario")
            or f"slot_id={slot_id}" not in (metadata.get("environment_notes") or "")
        ):
            raise ValueError(f"D4 session does not match its selected slot: {session_id}")
        pipeline.validate_session(metadata, probes, session_id)
        sessions.append(
            {
                "split": "test",
                "day": "D4",
                "slot_id": slot_id,
                "scenario": choice["scenario"],
                "session_id": session_id,
                "metadata": metadata,
                "probes": probes,
            }
        )
    return sessions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--selection", type=Path, default=DEFAULT_TEST_SELECTION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    analysis_dir = args.analysis_dir if args.analysis_dir.is_absolute() else ROOT / args.analysis_dir
    selection_path = args.selection if args.selection.is_absolute() else ROOT / args.selection
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    lock_path = analysis_dir / "model_lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if (
        lock.get("status") != "frozen_before_test_evaluation"
        or lock.get("selected_model") != "Ridge linear regression"
        or lock.get("ridge_alpha") != pipeline.RIDGE_ALPHA
        or lock.get("features") != list(pipeline.RIDGE_FEATURES)
        or lock.get("d4_outcomes_used_for_selection") is not False
    ):
        raise SystemExit("Frozen model lock does not match this evaluation code")
    if output_dir.exists():
        raise SystemExit(f"D4 final evaluation already started; refusing a second read: {output_dir}")
    # Check the selection manifest and record the locked evaluation before reading D4 probes.
    selection_bytes = selection_path.read_bytes()
    selection_preview = json.loads(selection_bytes)
    if selection_preview.get("status") != "accepted_after_audit" or selection_preview.get("split") != "test":
        raise SystemExit("D4 selection is not accepted as the held-out test split")
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "evaluation_started.json").write_text(
        json.dumps(
            {
                "started_at_utc": datetime.now(UTC).isoformat(),
                "model_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                "test_selection_sha256": hashlib.sha256(selection_bytes).hexdigest(),
                "note": "One-time final holdout evaluation; reruns are blocked by this output directory.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    train_validation_path = analysis_dir / "windows.csv"
    with train_validation_path.open(newline="", encoding="utf-8") as stream:
        fit_rows = list(csv.DictReader(stream))
    if not fit_rows or any(row["split"] not in {"train", "validation"} for row in fit_rows):
        raise ValueError("D1-D3 development windows must contain train/validation only")
    session_ids = {row["session_id"] for row in fit_rows}
    if len(session_ids) != 24:
        raise ValueError(f"Expected 24 D1-D3 fit sessions, found {len(session_ids)}")
    d4_sessions = read_test_sessions(selection_path)
    test_rows: list[dict[str, Any]] = []
    coverage = []
    for session in d4_sessions:
        windows, candidates, fully_observed = pipeline.build_windows(session)
        test_rows.extend(windows)
        coverage.append(
            {
                "slot_id": session["slot_id"],
                "session_id": session["session_id"],
                "scenario": session["scenario"],
                "candidate_windows": candidates,
                "valid_windows": len(windows),
                "fully_observed_windows": fully_observed,
                "probe_counts": session["metadata"]["probe_counts"],
            }
        )
    if len(test_rows) != 8 * 79:
        raise ValueError(f"Expected 632 valid D4 windows, found {len(test_rows)}")
    final_model = pipeline.fit_ridge(fit_rows, test_rows)
    final_model["fit_on_split"] = "train+validation"
    final_model["fit_session_count"] = len(session_ids)
    metrics = pipeline.metrics_for(test_rows)
    result = {
        "experiment_id": pipeline.EXPERIMENT_ID,
        "test_day": "D4",
        "test_selection": str(selection_path.relative_to(ROOT)),
        "model_lock": str(lock_path.relative_to(ROOT)),
        "fit_splits": ["train", "validation"],
        "fit_sessions": len(session_ids),
        "test_sessions": len(d4_sessions),
        "valid_test_windows": len(test_rows),
        "coverage": coverage,
        "metrics": metrics,
        "d4_used_for_tuning": False,
        "aggregation": "Metrics are computed per session, then averaged equally; overlapping windows are not independent replicates.",
    }
    with (output_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(test_rows[0]))
        writer.writeheader()
        writer.writerows(test_rows)
    (output_dir / "ridge_model.json").write_text(json.dumps(final_model, indent=2) + "\n", encoding="utf-8")
    (output_dir / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report = [
        "# Formal v2 Final Held-Out Evaluation",
        "",
        "The model and alpha were locked using D3 validation before this evaluation. D4 was not used for tuning.",
        "The final Ridge model was refit on D1-D3 and evaluated once on D4.",
        "Metrics are averaged equally over sessions; overlapping windows are not independent replicates.",
        "",
        "| Scenario | Sessions | Valid windows | Fully observed windows | History P95 MAE (ms) | Ridge MAE (ms) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    by_scenario = {row["scenario"]: row for row in metrics["per_scenario_session_equal"]}
    for scenario in ("idle", "upload", "download", "burst"):
        row = by_scenario[scenario]
        cov = [item for item in coverage if item["scenario"] == scenario]
        report.append(
            f"| {scenario} | {row['sessions']} | {sum(x['valid_windows'] for x in cov)} | "
            f"{sum(x['fully_observed_windows'] for x in cov)} | "
            f"{row['history_p95_mae_ms']:.2f} | {row['ridge_mae_ms']:.2f} |"
        )
    overall = metrics["overall_session_equal"][0]
    report.extend(
        [
            "",
            f"Overall across {overall['sessions']} held-out sessions: history-P95 MAE "
            f"{overall['history_p95_mae_ms']:.2f} ms; Ridge MAE {overall['ridge_mae_ms']:.2f} ms.",
            "",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Final D4 evaluation saved to {output_dir}")
    print(
        f"D4: {overall['sessions']} sessions, {len(test_rows)} windows; "
        f"history-P95 MAE={overall['history_p95_mae_ms']:.3f} ms, "
        f"Ridge MAE={overall['ridge_mae_ms']:.3f} ms"
    )
    print("D4 results were not used to tune the model; reruns are blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
