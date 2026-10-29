import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/mac_mac_iperf3_fixed_pilot_v2.sh"


class FixedPilotV2Tests(unittest.TestCase):
    def _fake_command(self, directory: Path, name: str, body: str) -> None:
        path = directory / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def test_fixed_rate_modes_keep_target_and_direction(self):
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
                '  printf "%s\\n" "$@" > "$NETPULSE_TEST_BURST_ARGS"\n'
                '  burst_dir="$NETPULSE_LOAD_ROOT/burst-20261023T080000Z-test"\n'
                '  mkdir -p "$burst_dir"\n'
                '  echo "{}" > "$burst_dir/run.json"\n'
                '  printf "Burst run burst-20261023T080000Z-test; logs: %s\\n" "$burst_dir"\n'
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
                fake_bin, "iperf3",
                'printf "%s\\n" "$@" > "$NETPULSE_TEST_IPERF_ARGS"\n'
                '/bin/sleep 0.5\n',
            )
            environment = os.environ.copy()
            environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
            environment["NETPULSE_TEST_REAL_PYTHON"] = sys.executable
            environment["NETPULSE_TEST_COLLECT_ARGS"] = str(root / "collect-args.txt")
            environment["NETPULSE_TEST_IPERF_ARGS"] = str(root / "iperf-args.txt")
            environment["NETPULSE_TEST_BURST_ARGS"] = str(root / "burst-args.txt")
            environment["NETPULSE_TEST_OVERLAP_ARGS"] = str(root / "overlap-args.txt")
            environment["NETPULSE_LOAD_ROOT"] = str(root / "load")
            environment["NETPULSE_RAW_ROOT"] = str(root / "raw")

            for mode, expected_rate, reverse in (
                ("upload", "300000000", False),
                ("download", "300000000", True),
            ):
                result = subprocess.run(
                    ["bash", str(SCRIPT), mode, "192.168.1.151", "en0"],
                    cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                iperf_args = (root / "iperf-args.txt").read_text().splitlines()
                collect_args = (root / "collect-args.txt").read_text()
                self.assertIn(expected_rate, iperf_args)
                self.assertEqual("-R" in iperf_args, reverse)
                self.assertIn(f"--scenario\n{mode}", collect_args)
                self.assertIn('"rate_policy": "fixed_sender_target"', collect_args)
                self.assertIn('"target_rate_bps": 300000000', collect_args)
                self.assertIn("mac-mac-iperf3-fixed-pilot-v2.toml", collect_args)

            result = subprocess.run(
                ["bash", str(SCRIPT), "burst", "192.168.1.151", "en0", "42"],
                cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            burst_args = (root / "burst-args.txt").read_text()
            collect_args = (root / "collect-args.txt").read_text()
            self.assertIn("--seed\n42", burst_args)
            self.assertNotIn("--capacity-mbps", burst_args)
            self.assertIn('"target_rate_bps": 350000000', collect_args)
            self.assertIn("burst-20261023T080000Z-test", (root / "overlap-args.txt").read_text())

            result = subprocess.run(
                ["bash", str(SCRIPT), "idle", "192.168.1.151", "en0"],
                cwd=REPO, env=environment, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--scenario\nidle", (root / "collect-args.txt").read_text())


if __name__ == "__main__":
    unittest.main()
