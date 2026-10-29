import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/collect_formal_day1.sh"


class DayOneScriptTests(unittest.TestCase):
    def test_dry_run_lists_all_eight_without_starting_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = Path(temporary) / "summary.json"
            summary.write_text(json.dumps({
                "directions": {
                    "upload": {"capacity_mbps": 500},
                    "download": {"capacity_mbps": 550},
                }
            }), encoding="utf-8")
            result = subprocess.run(
                ["bash", str(SCRIPT), "192.168.1.151", "en0", str(summary), "--dry-run"],
                cwd=REPO, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("\n[D1-"), 8)
            self.assertIn("D1-04 burst", result.stdout)
            self.assertIn("D1-06 burst", result.stdout)
            self.assertIn("Dry run complete; no sessions were started.", result.stdout)

            resumed = subprocess.run(
                ["bash", str(SCRIPT), "192.168.1.151", "en0", str(summary), "--from", "D1-05", "--dry-run"],
                cwd=REPO, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(resumed.stdout.count("\n[D1-"), 4)


if __name__ == "__main__":
    unittest.main()
