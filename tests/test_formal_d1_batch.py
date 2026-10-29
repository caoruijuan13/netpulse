import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from check_formal_d1_batch import _block_mean, _receiver_intervals, _receiver_summary  # noqa: E402


class FormalD1BatchTests(unittest.TestCase):
    def test_receiver_interval_parser_and_block_mean(self):
        lines = [
            f"[  5] {start:6.2f}-{start + 10:.2f} sec  450 MBytes  400 Mbits/sec"
            for start in range(0, 930, 10)
        ]
        lines.append("[  5]   0.00-930.00 sec  42.0 GBytes  400 Mbits/sec receiver")
        text = "\n".join(lines)
        self.assertEqual(_receiver_summary(text), 400_000_000)
        self.assertEqual(len(_receiver_intervals(text)), 93)
        self.assertEqual(_block_mean(_receiver_intervals(text), 3, 903), 400_000_000)

    def test_preflight_requires_completed_idle_and_unused_loaded_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            session_dir = raw / "idle-example"
            session_dir.mkdir(parents=True)
            calibration = root / "calibrate-example" / "summary.json"
            calibration.parent.mkdir()
            calibration.write_text(json.dumps({"directions": {
                "upload": {"trial_receiver_mbps": [500, 510, 520]},
                "download": {"trial_receiver_mbps": [550, 560, 570]},
            }}), encoding="utf-8")
            for direction in ("upload", "download"):
                for trial in range(1, 4):
                    (calibration.parent / f"{direction}-{trial}.json").write_text("{}", encoding="utf-8")
            session = {
                "session_id": "idle-example", "experiment_id": "mac-mac-iperf3-v1",
                "experiment_status": "frozen", "scenario": "idle", "run_status": "completed",
                "started_at_utc": "2026-10-22T00:00:00+00:00",
                "ended_at_utc": "2026-10-22T00:15:00+00:00",
                "expected_probe_slots": 900, "recorded_probe_slots": 900,
                "probe_counts": {"ok": 900, "missed_slot": 0},
                "max_start_lateness_ms": 250,
                "environment_notes": "slot_id=D1-01",
            }
            (session_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
            base = datetime(2026, 10, 22, tzinfo=timezone.utc)
            with (session_dir / "probes.jsonl").open("w", encoding="utf-8") as output:
                for seq in range(900):
                    output.write(json.dumps({
                        "probe_seq": seq, "status": "ok",
                        "scheduled_monotonic_ns": seq * 1_000_000_000,
                        "started_monotonic_ns": seq * 1_000_000_000 + 1_000_000,
                        "started_at_utc": (base + timedelta(seconds=seq, milliseconds=1)).isoformat(),
                    }) + "\n")
            command = [sys.executable, str(SCRIPTS / "check_formal_d1_batch.py"), "preflight", str(calibration), "--raw-root", str(raw)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("preflight passed", result.stdout)

            loaded = raw / "upload-example"
            loaded.mkdir()
            (loaded / "session.json").write_text(json.dumps({
                "environment_notes": "slot_id=D1-02", "started_at_utc": "2026-10-22T01:00:00+00:00",
            }), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("already has an attempt", result.stderr)

            new_idle = raw / "idle-new"
            new_idle.mkdir()
            new_session = {**session, "session_id": "idle-new",
                           "started_at_utc": "2026-10-23T00:00:00+00:00",
                           "ended_at_utc": "2026-10-23T00:15:00+00:00"}
            (new_idle / "session.json").write_text(json.dumps(new_session), encoding="utf-8")
            (new_idle / "probes.jsonl").write_text(
                (session_dir / "probes.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
            )
            anchored = command + ["--anchor-session-id", "idle-new"]
            result = subprocess.run(anchored, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("idle-new", result.stdout)

            new_loaded = raw / "upload-new"
            new_loaded.mkdir()
            (new_loaded / "session.json").write_text(json.dumps({
                "environment_notes": "slot_id=D1-02", "started_at_utc": "2026-10-23T01:00:00+00:00",
            }), encoding="utf-8")
            result = subprocess.run(anchored, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("already has an attempt", result.stderr)


if __name__ == "__main__":
    unittest.main()
