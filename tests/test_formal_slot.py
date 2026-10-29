import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_formal_slot.py"


class FormalSlotTests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)

    def test_preassigned_scenarios_and_seeds(self):
        self.assertEqual(self._run("D1-01", "idle", "").returncode, 0)
        self.assertEqual(self._run("D1-04", "burst", "101").returncode, 0)
        self.assertEqual(self._run("D4-07", "burst", "108").returncode, 0)

    def test_wrong_scenario_or_seed_is_rejected(self):
        wrong_mode = self._run("D1-01", "upload", "")
        self.assertEqual(wrong_mode.returncode, 2)
        self.assertIn("assigned to idle", wrong_mode.stderr)
        wrong_seed = self._run("D1-04", "burst", "42")
        self.assertEqual(wrong_seed.returncode, 2)
        self.assertIn("requires burst seed 101", wrong_seed.stderr)


if __name__ == "__main__":
    unittest.main()
