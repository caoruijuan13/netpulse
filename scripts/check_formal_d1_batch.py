"""Quick, fail-closed checks for the unattended D1-02 through D1-04 batch."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

from check_burst_overlap import check_burst_overlap


EXPERIMENT_ID = "mac-mac-iperf3-v1"
SCENARIOS = {"D1-01": "idle", "D1-02": "upload", "D1-03": "download", "D1-04": "burst"}
RATE_UNITS = {"": 1, "K": 1_000, "M": 1_000_000, "G": 1_000_000_000}
INTERVAL = re.compile(
    r"^\[\s*\d+\]\s+(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s+sec\s+"
    r"[\d.]+\s+[KMG]?Bytes\s+([\d.]+)\s+([KMG]?)bits/sec"
)
RECEIVER = re.compile(
    r"^\[\s*\d+\]\s+0\.00-\d+(?:\.\d+)?\s+sec\s+"
    r"[\d.]+\s+[KMG]?Bytes\s+([\d.]+)\s+([KMG]?)bits/sec\s+receiver\s*$"
)


def matching_sessions(
    raw_root: Path, slot_id: str, *, after_utc: datetime | None = None,
    session_id: str | None = None,
) -> list[tuple[Path, dict]]:
    matches = []
    for path in raw_root.glob("*/session.json"):
        session = json.loads(path.read_text(encoding="utf-8"))
        if f"slot_id={slot_id}" not in session.get("environment_notes", ""):
            continue
        if session_id is not None and session.get("session_id") != session_id:
            continue
        if after_utc is not None and datetime.fromisoformat(session["started_at_utc"]) <= after_utc:
            continue
        matches.append((path, session))
    return matches


def check_session(
    raw_root: Path, slot_id: str, *, after_utc: datetime | None = None,
    session_id: str | None = None,
) -> tuple[Path, dict]:
    matches = matching_sessions(raw_root, slot_id, after_utc=after_utc, session_id=session_id)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {slot_id} session; found {len(matches)}")
    path, session = matches[0]
    if (session.get("experiment_id"), session.get("experiment_status"), session.get("scenario")) != (
        EXPERIMENT_ID, "frozen", SCENARIOS[slot_id]
    ):
        raise ValueError(f"{slot_id} has the wrong experiment or scenario metadata")
    if session.get("run_status") != "completed":
        raise ValueError(f"{slot_id} collector did not complete")
    if session.get("expected_probe_slots") != 900 or session.get("recorded_probe_slots") != 900:
        raise ValueError(f"{slot_id} does not have 900 recorded probe slots")
    if session.get("probe_counts", {}).get("missed_slot") != 0:
        raise ValueError(f"{slot_id} has missed probe slots")
    probes = [json.loads(line) for line in (path.parent / "probes.jsonl").read_text(encoding="utf-8").splitlines()]
    if [probe["probe_seq"] for probe in probes] != list(range(900)):
        raise ValueError(f"{slot_id} probe sequence is incomplete or out of order")
    wall_mono = []
    for probe in probes:
        started = probe.get("started_monotonic_ns")
        if started is not None:
            lateness_ms = (started - probe["scheduled_monotonic_ns"]) / 1_000_000
            if lateness_ms > session["max_start_lateness_ms"]:
                raise ValueError(f"{slot_id} has a late probe start")
            if probe.get("started_at_utc"):
                wall_mono.append((datetime.fromisoformat(probe["started_at_utc"]).timestamp(), started / 1e9))
    for previous, current in zip(wall_mono, wall_mono[1:]):
        if abs((current[0] - previous[0]) - (current[1] - previous[1])) > 2:
            raise ValueError(f"{slot_id} has a UTC/monotonic discontinuity")
    return path, session


def check_calibration(path: Path) -> None:
    if not path.is_file() or not path.parent.name.startswith("calibrate-"):
        raise ValueError("pass an existing calibrate-*/summary.json file")
    summary = json.loads(path.read_text(encoding="utf-8"))
    for direction in ("upload", "download"):
        values = summary["directions"][direction]["trial_receiver_mbps"]
        if len(values) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values):
            raise ValueError(f"calibration lacks three valid {direction} receiver rates")
        for trial in range(1, 4):
            if not (path.parent / f"{direction}-{trial}.json").is_file():
                raise ValueError(f"calibration lacks {direction}-{trial}.json")


def _rate(match: re.Match[str], value_index: int) -> float:
    return float(match.group(value_index)) * RATE_UNITS[match.group(value_index + 1)]


def _receiver_summary(text: str) -> float:
    for line in text.splitlines():
        match = RECEIVER.match(line)
        if match:
            return _rate(match, 1)
    raise ValueError("iperf3 receiver summary is missing")


def _receiver_intervals(text: str) -> list[tuple[float, float, float]]:
    rows = []
    for line in text.splitlines():
        match = INTERVAL.match(line)
        if match:
            start, end = float(match.group(1)), float(match.group(2))
            if 0 < end - start <= 10.5:
                rows.append((start, end, _rate(match, 3)))
    if not rows:
        raise ValueError("iperf3 receiver intervals are missing")
    return rows


def _block_mean(rows: list[tuple[float, float, float]], start: float, end: float) -> float:
    covered = 0.0
    total = 0.0
    for left, right, rate in rows:
        overlap = max(0.0, min(right, end) - max(left, start))
        covered += overlap
        total += overlap * rate
    if covered < (end - start) - 1:
        raise ValueError("iperf3 receiver intervals do not cover the collector overlap")
    return total / covered


def verify_loaded(raw_root: Path, slot_id: str, *, after_utc: datetime | None = None) -> str:
    _, session = check_session(raw_root, slot_id, after_utc=after_utc)
    target = session["traffic_settings"]["target_rate_bps"]
    log_path = Path(session["traffic_settings"]["iperf_client_log"])
    log = log_path.read_text(encoding="utf-8", errors="replace")
    if slot_id == "D1-04":
        run_dir = log_path.parent
        session_id, count = check_burst_overlap(run_dir, raw_root)
        sections = re.split(r"(?=^=== pulse \d+ start)", log, flags=re.MULTILINE)
        rates = [_receiver_summary(section) for section in sections if re.search(r"^=== pulse \d+ start", section, re.MULTILINE)]
        if len(rates) != count or min(rates) < 0.75 * target or not 0.85 * target <= sum(rates) / count <= 1.15 * target:
            raise ValueError("burst receiver-side pulse rates fail the frozen load gate")
        return f"{slot_id}: {count} fully observed pulses; receiver mean {sum(rates) / count / 1e6:.1f} Mbps; {session_id}"

    if "iperf Done." not in log:
        raise ValueError(f"{slot_id} iperf3 did not finish normally")
    receiver_text = log.split("Server output:", 1)[1] if slot_id == "D1-02" else log.split("Server output:", 1)[0]
    summary_rate = _receiver_summary(receiver_text)
    rows = _receiver_intervals(receiver_text)
    overlap_mean = _block_mean(rows, 3, 903)
    block_means = [_block_mean(rows, 3 + 60 * index, 63 + 60 * index) for index in range(15)]
    if not 0.85 * target <= overlap_mean <= 1.15 * target or min(block_means) < 0.75 * target:
        raise ValueError(f"{slot_id} receiver-side load fails the frozen adherence gate")
    return (
        f"{slot_id}: receiver summary {summary_rate / 1e6:.1f} Mbps; "
        f"overlap {overlap_mean / 1e6:.1f} Mbps; min 60s {min(block_means) / 1e6:.1f} Mbps"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "verify"))
    parser.add_argument("value", help="calibration summary for preflight; slot ID for verify")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--anchor-session-id", help="completed D1-01 session that starts a restarted D1")
    args = parser.parse_args()
    try:
        after_utc = None
        if args.anchor_session_id:
            _, anchor = check_session(args.raw_root, "D1-01", session_id=args.anchor_session_id)
            after_utc = datetime.fromisoformat(anchor["ended_at_utc"])
        if args.action == "preflight":
            check_calibration(Path(args.value))
            _, idle = (check_session(args.raw_root, "D1-01", session_id=args.anchor_session_id)
                       if args.anchor_session_id else check_session(args.raw_root, "D1-01"))
            for slot_id in ("D1-02", "D1-03", "D1-04"):
                if matching_sessions(args.raw_root, slot_id, after_utc=after_utc):
                    raise ValueError(f"{slot_id} already has an attempt; review it before running a batch")
            print(f"D1 preflight passed: idle {idle['session_id']} completed; calibration {args.value}")
        else:
            if args.value not in ("D1-02", "D1-03", "D1-04"):
                raise ValueError("verify expects D1-02, D1-03, or D1-04")
            print(verify_loaded(args.raw_root, args.value, after_utc=after_utc))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, IndexError) as exc:
        print(f"D1 batch check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
