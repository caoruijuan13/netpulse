"""Verify that every completed burst pulse was fully observed by one RTT session."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def check_burst_overlap(load_dir: Path, raw_root: Path) -> tuple[str, int]:
    run = json.loads((load_dir / "run.json").read_text(encoding="utf-8"))
    if run["status"] != "completed":
        raise ValueError(f"burst load status is {run['status']}, not completed")

    matches = []
    for path in raw_root.glob("burst-*/session.json"):
        session = json.loads(path.read_text(encoding="utf-8"))
        if (session.get("traffic_settings") or {}).get("load_run_id") == run["run_id"]:
            matches.append(session)
    if len(matches) != 1:
        raise ValueError(f"expected one RTT session for {run['run_id']}; found {len(matches)}")
    session = matches[0]
    if session["run_status"] != "completed":
        raise ValueError(f"RTT session status is {session['run_status']}, not completed")
    if session["recorded_probe_slots"] != session["expected_probe_slots"]:
        raise ValueError("RTT session has incomplete probe slot coverage")

    events = [json.loads(line) for line in (load_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    planned = run["planned_pulses"]
    if not planned or len(events) != len(planned) or run["completed_pulses"] != len(planned):
        raise ValueError("burst pulse count does not match the completed plan")

    session_start = _timestamp(session["started_at_utc"])
    session_end = _timestamp(session["ended_at_utc"])
    for expected, event in zip(planned, events):
        index = expected["pulse_index"]
        if event["pulse_index"] != index or event["status"] != "ok":
            raise ValueError(f"pulse {index} is missing or did not complete successfully")
        start = _timestamp(event["started_at_utc"])
        end = _timestamp(event["ended_at_utc"])
        if not session_start <= start <= end <= session_end:
            raise ValueError(f"pulse {index} was not fully observed by RTT session {session['session_id']}")
    return session["session_id"], len(events)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("load_dir", type=Path)
    parser.add_argument("raw_root", type=Path)
    args = parser.parse_args()
    try:
        session_id, count = check_burst_overlap(args.load_dir, args.raw_root)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Burst overlap check failed: {exc}\n")
    print(f"Burst overlap verified: {count} pulses fully observed by {session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
