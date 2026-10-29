"""Reject a formal session whose mode or burst seed differs from its frozen slot."""

from __future__ import annotations

import argparse
import re


DAY_SCENARIOS = {
    1: ("idle", "upload", "download", "burst", "download", "burst", "idle", "upload"),
    2: ("upload", "burst", "idle", "download", "burst", "download", "upload", "idle"),
    3: ("download", "idle", "burst", "upload", "idle", "upload", "download", "burst"),
    4: ("burst", "download", "upload", "idle", "upload", "idle", "burst", "download"),
}
BURST_SEEDS = {
    (1, 4): 101,
    (1, 6): 102,
    (2, 2): 103,
    (2, 5): 104,
    (3, 3): 105,
    (3, 8): 106,
    (4, 1): 107,
    (4, 7): 108,
}


def check_formal_slot(slot_id: str, mode: str, seed: str | None = None) -> None:
    match = re.fullmatch(r"D([1-4])-0([1-8])", slot_id)
    if match is None:
        raise ValueError("slot ID must be D1-01 through D4-08")
    day, position = map(int, match.groups())
    expected = DAY_SCENARIOS[day][position - 1]
    if mode != expected:
        raise ValueError(f"{slot_id} is assigned to {expected}, not {mode}")
    if expected == "burst" and seed != str(BURST_SEEDS[(day, position)]):
        raise ValueError(f"{slot_id} requires burst seed {BURST_SEEDS[(day, position)]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slot_id")
    parser.add_argument("mode")
    parser.add_argument("seed", nargs="?")
    args = parser.parse_args()
    try:
        check_formal_slot(args.slot_id, args.mode, args.seed)
    except ValueError as exc:
        parser.exit(2, f"Formal slot error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
