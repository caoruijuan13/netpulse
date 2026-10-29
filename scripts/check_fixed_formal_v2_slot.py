"""Fail fast after a fixed-load formal v2 slot with invalid probe timing."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def check(session_dir: Path, slot_id: str, scenario: str) -> tuple[int, int]:
    session = json.loads((session_dir / "session.json").read_text())
    probes = [json.loads(line) for line in (session_dir / "probes.jsonl").read_text().splitlines()]
    if session["experiment_id"] != "mac-mac-iperf3-fixed-v2" or session["experiment_status"] != "frozen":
        raise ValueError("wrong experiment or status")
    if session["scenario"] != scenario or f"slot_id={slot_id}" not in session["environment_notes"]:
        raise ValueError("wrong scenario or slot")
    if session["run_status"] != "completed" or len(probes) != 900:
        raise ValueError("session did not complete 900 probe slots")
    if [probe["probe_seq"] for probe in probes] != list(range(900)):
        raise ValueError("probe sequence is incomplete or unordered")
    if any(probe["status"] == "missed_slot" for probe in probes):
        raise ValueError("session contains a missed slot")
    started = datetime.fromisoformat(session["started_at_utc"])
    ended = datetime.fromisoformat(session["ended_at_utc"])
    elapsed = (ended - started).total_seconds()
    if abs(elapsed - 900) > 2:
        raise ValueError(f"wall-clock duration is {elapsed:.1f}s, expected about 900s")
    previous = None
    for probe in probes:
        if probe["started_at_utc"] is None or probe["started_monotonic_ns"] is None:
            continue
        current = (datetime.fromisoformat(probe["started_at_utc"]), probe["started_monotonic_ns"])
        if previous is not None:
            wall_step = (current[0] - previous[0]).total_seconds()
            monotonic_step = (current[1] - previous[1]) / 1_000_000_000
            if abs(wall_step - monotonic_step) > 2:
                raise ValueError(f"UTC/monotonic discontinuity near probe {probe['probe_seq']}")
        previous = current
    valid_windows = sum(
        sum(probe["status"] == "ok" for probe in probes[i : i + 60]) >= 57
        and sum(probe["status"] == "ok" for probe in probes[i + 60 : i + 120]) >= 57
        for i in range(0, 781, 10)
    )
    if valid_windows == 0:
        raise ValueError("no valid 60+60 RTT windows")
    return valid_windows, sum(probe["status"] == "ok" for probe in probes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("slot_id")
    parser.add_argument("scenario")
    args = parser.parse_args()
    try:
        windows, ok = check(args.session_dir, args.slot_id, args.scenario)
    except (KeyError, OSError, ValueError) as exc:
        parser.exit(1, f"Formal v2 slot {args.slot_id} failed quick gate: {exc}\n")
    print(f"Formal v2 slot {args.slot_id} probe gate passed: ok={ok}/900 valid_windows={windows}/79")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
