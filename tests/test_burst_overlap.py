import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_burst_overlap.py"


class BurstOverlapTests(unittest.TestCase):
    def _fixture(self, root: Path, *, pulse_end: str = "2026-10-22T10:16:25+00:00") -> tuple[Path, Path]:
        load_dir = root / "load" / "burst-example"
        raw_root = root / "raw"
        session_dir = raw_root / "burst-session"
        load_dir.mkdir(parents=True)
        session_dir.mkdir(parents=True)
        (load_dir / "run.json").write_text(json.dumps({
            "run_id": "burst-example",
            "status": "completed",
            "completed_pulses": 1,
            "planned_pulses": [{"pulse_index": 0}],
        }), encoding="utf-8")
        (load_dir / "events.jsonl").write_text(json.dumps({
            "pulse_index": 0,
            "status": "ok",
            "started_at_utc": "2026-10-22T10:16:05+00:00",
            "ended_at_utc": pulse_end,
        }) + "\n", encoding="utf-8")
        (session_dir / "session.json").write_text(json.dumps({
            "session_id": "burst-session",
            "run_status": "completed",
            "recorded_probe_slots": 900,
            "expected_probe_slots": 900,
            "started_at_utc": "2026-10-22T10:15:35+00:00",
            "ended_at_utc": "2026-10-22T10:30:35+00:00",
            "traffic_settings": {"load_run_id": "burst-example"},
        }), encoding="utf-8")
        return load_dir, raw_root

    def test_full_overlap_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            load_dir, raw_root = self._fixture(Path(temporary))
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(load_dir), str(raw_root)],
                capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 pulses fully observed", result.stdout)

    def test_pulse_after_collector_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            load_dir, raw_root = self._fixture(
                Path(temporary), pulse_end="2026-10-22T10:30:40+00:00",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(load_dir), str(raw_root)],
                capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("not fully observed", result.stderr)


if __name__ == "__main__":
    unittest.main()
