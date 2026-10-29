import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/mac_mac_iperf3_trial.sh"
FORMAL_SCRIPT = REPO / "scripts/mac_mac_iperf3_formal.sh"


class TrialScriptTests(unittest.TestCase):
    def _fake_command(self, directory: Path, name: str, body: str) -> None:
        path = directory / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def test_bash32_calibration_and_sustained_directions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self._fake_command(fake_bin, "ipconfig", "echo 192.168.1.119\n")
            self._fake_command(fake_bin, "route", "echo 'interface: en0'\n")
            self._fake_command(fake_bin, "sleep", "exit 0\n")
            self._fake_command(
                fake_bin, "caffeinate",
                'if [[ " $* " == *" netpulse.collect "* ]]; then '
                'printf "%s\\n" "$@" > "$NETPULSE_TEST_COLLECT_ARGS"; fi\n',
            )
            self._fake_command(
                fake_bin, "python3",
                'if [[ "${1:-}" == "-m" && "${2:-}" == "netpulse.burst" ]]; then\n'
                '  burst_dir="$NETPULSE_LOAD_ROOT/burst-20261022T091500Z-test"\n'
                '  mkdir -p "$burst_dir"\n'
                '  echo "{}" > "$burst_dir/run.json"\n'
                '  printf "Burst run burst-20261022T091500Z-test; logs: %s\\n" "$burst_dir"\n'
                '  /bin/sleep 0.3\n'
                '  exit 0\n'
                'fi\n'
                'if [[ "${1:-}" == "scripts/check_burst_overlap.py" ]]; then\n'
                '  printf "%s\\n" "$@" > "$NETPULSE_TEST_OVERLAP_ARGS"\n'
                '  exit 0\n'
                'fi\n'
                'exec "$NETPULSE_TEST_REAL_PYTHON" "$@"\n',
            )
            self._fake_command(
                fake_bin,
                "iperf3",
                'printf "%s\\n" "$@" > "$NETPULSE_TEST_IPERF_ARGS"\n'
                'if [[ " $* " == *" -t 930 "* ]]; then /bin/sleep 0.3; exit 0; fi\n'
                'rate=100000000\n'
                'if [[ " $* " == *" -R "* ]]; then rate=200000000; fi\n'
                'printf "{\\"end\\":{\\"sum_received\\":{\\"bits_per_second\\":%s}}}\\n" "$rate"\n',
            )
            environment = os.environ.copy()
            environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
            environment["NETPULSE_TEST_IPERF_ARGS"] = str(root / "iperf-args.txt")
            environment["NETPULSE_TEST_COLLECT_ARGS"] = str(root / "collect-args.txt")
            environment["NETPULSE_TEST_OVERLAP_ARGS"] = str(root / "overlap-args.txt")
            environment["NETPULSE_TEST_REAL_PYTHON"] = sys.executable
            environment["NETPULSE_LOAD_ROOT"] = str(root / "load")

            result = subprocess.run(
                ["bash", str(SCRIPT), "calibrate", "192.168.1.151", "en0"],
                cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calibration_dir = next((root / "load").glob("calibrate-*") )
            summary_path = calibration_dir / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["directions"]["upload"]["capacity_mbps"], 100)
            self.assertEqual(summary["directions"]["download"]["capacity_mbps"], 200)

            for mode, expected_bps, reverse in (("upload", "70000000", False), ("download", "140000000", True)):
                result = subprocess.run(
                    ["bash", str(SCRIPT), mode, "192.168.1.151", "en0", str(summary_path)],
                    cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                iperf_args = (root / "iperf-args.txt").read_text(encoding="utf-8").splitlines()
                collect_args = (root / "collect-args.txt").read_text(encoding="utf-8")
                self.assertEqual("-R" in iperf_args, reverse)
                self.assertIn(expected_bps, iperf_args)
                self.assertIn(f"--scenario\n{mode}", collect_args)

            result = subprocess.run(
                ["bash", str(SCRIPT), "burst", "192.168.1.151", "en0", str(summary_path), "42"],
                cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            collect_args = (root / "collect-args.txt").read_text(encoding="utf-8")
            self.assertIn("--scenario\nburst", collect_args)
            self.assertIn('"load_run_id":"burst-20261022T091500Z-test"', collect_args)
            self.assertIn('"target_rate_bps":90000000', collect_args)
            overlap_args = (root / "overlap-args.txt").read_text(encoding="utf-8")
            self.assertIn("scripts/check_burst_overlap.py", overlap_args)
            self.assertIn("burst-20261022T091500Z-test", overlap_args)
            self.assertNotIn("XXXXXX", result.stdout)

            result = subprocess.run(
                ["bash", str(FORMAL_SCRIPT), "D1-01", "idle", "192.168.1.151", "en0"],
                cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            collect_args = (root / "collect-args.txt").read_text(encoding="utf-8")
            self.assertIn("--scenario\nidle", collect_args)
            self.assertIn("configs/mac-mac-iperf3-v1.toml", collect_args)
            self.assertIn("slot_id=D1-01", collect_args)

            result = subprocess.run(
                ["bash", str(FORMAL_SCRIPT), "D1-02", "upload", "192.168.1.151", "en0", str(summary_path)],
                cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            collect_args = (root / "collect-args.txt").read_text(encoding="utf-8")
            self.assertIn("--scenario\nupload", collect_args)
            self.assertIn("configs/mac-mac-iperf3-v1.toml", collect_args)
            self.assertIn("slot_id=D1-02", collect_args)

            result = subprocess.run(
                ["bash", str(FORMAL_SCRIPT), "D1-01", "upload", "192.168.1.151", "en0", str(summary_path)],
                cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("assigned to idle", result.stderr)


if __name__ == "__main__":
    unittest.main()
