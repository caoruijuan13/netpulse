"""Summarize six saved iperf3 JSON trials using receiver-side rates."""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path


def receiver_mbps(path: Path) -> float:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "error" in data:
        raise ValueError(f"{path}: {data['error']}")
    try:
        rate = data["end"]["sum_received"]["bits_per_second"] / 1_000_000
    except (KeyError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(f"{path}: missing receiver-side summary") from exc
    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        raise ValueError(f"{path}: invalid receiver-side rate")
    return float(rate)


def summarize(directory: Path) -> dict[str, object]:
    summary: dict[str, object] = {"source": "iperf3 end.sum_received.bits_per_second", "directions": {}}
    for direction in ("upload", "download"):
        trials = [receiver_mbps(directory / f"{direction}-{index}.json") for index in (1, 2, 3)]
        capacity = statistics.median(trials)
        summary["directions"][direction] = {
            "trial_receiver_mbps": trials,
            "capacity_mbps": capacity,
            "sustained_target_bps": round(capacity * 0.70 * 1_000_000),
        }
    summary["burst_target_bps"] = round(summary["directions"]["upload"]["capacity_mbps"] * 0.90 * 1_000_000)
    return summary


def capacity_from_summary(path: Path, direction: str) -> float:
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        capacity = float(data["directions"][direction]["capacity_mbps"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{path}: missing {direction} capacity") from exc
    if not math.isfinite(capacity) or capacity <= 0:
        raise ValueError(f"{path}: invalid {direction} capacity")
    return capacity


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 3 and args[0] == "--capacity" and args[1] in ("upload", "download"):
        try:
            print(capacity_from_summary(Path(args[2]), args[1]))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"calibration error: {exc}", file=sys.stderr)
            return 1
        return 0
    if len(args) != 1:
        print("usage: summarize_iperf3_calibration.py <CALIBRATION_DIR> | --capacity <upload|download> <SUMMARY_JSON>", file=sys.stderr)
        return 2
    directory = Path(args[0])
    try:
        result = summarize(directory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"calibration error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
