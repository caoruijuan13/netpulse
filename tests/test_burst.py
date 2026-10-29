import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netpulse.burst import BurstConfig, iperf3_path, load_burst_config, plan_bursts, positive_float, run_bursts, send_pulse


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "mac-mac-iperf3-pilot-v1.toml"
FIXED_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "mac-mac-iperf3-fixed-pilot-v2.toml"
HISTORICAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "m0-v1.toml"
OLD_MAC_PILOT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "mac-mac-iperf3-pilot.toml"


def overrides(**values):
    defaults = {
        "duration_seconds": None,
        "start_delay_seconds": None,
        "on_min_seconds": None,
        "on_max_seconds": None,
        "off_min_seconds": None,
        "off_max_seconds": None,
    }
    defaults.update(values)
    return argparse.Namespace(**defaults)


class BurstPlanTests(unittest.TestCase):
    def test_plan_is_reproducible_and_nonoverlapping(self):
        config = load_burst_config(CONFIG_PATH, overrides())
        first = plan_bursts(config, seed=42)
        self.assertEqual(first, plan_bursts(config, seed=42))
        self.assertNotEqual(first, plan_bursts(config, seed=43))
        self.assertGreater(len(first), 1)
        for pulse, following in zip(first, first[1:]):
            self.assertEqual(
                following["planned_offset_seconds"],
                pulse["planned_offset_seconds"] + pulse["on_seconds"] + pulse["off_seconds_after"],
            )
        self.assertLessEqual(first[-1]["planned_offset_seconds"] + first[-1]["on_seconds"], config.duration_seconds)

    def test_pilot_plan_does_not_schedule_pulses_after_collector(self):
        config = load_burst_config(CONFIG_PATH, overrides())
        pulses = plan_bursts(config, seed=37)
        self.assertEqual(config.duration_seconds, 900)
        self.assertEqual(len(pulses), 18)
        self.assertLessEqual(pulses[-1]["planned_offset_seconds"] + pulses[-1]["on_seconds"], 900)

    def test_fixed_rate_config_does_not_require_a_capacity_fraction(self):
        config = load_burst_config(FIXED_CONFIG_PATH, overrides())
        self.assertEqual(config.fixed_target_bps, 350_000_000)
        self.assertIsNone(config.rate_fraction)

    def test_invalid_rate_and_duration_are_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_float("nan")
        with self.assertRaises(ValueError):
            load_burst_config(CONFIG_PATH, overrides(duration_seconds=5, start_delay_seconds=5))
        with self.assertRaisesRegex(ValueError, "collector session duration"):
            load_burst_config(CONFIG_PATH, overrides(duration_seconds=930))

    def test_historical_iperf2_config_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "iperf3 experiment config"):
            load_burst_config(HISTORICAL_CONFIG_PATH, overrides())

    def test_old_mac_topology_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Wi-Fi collector to Ethernet target"):
            load_burst_config(OLD_MAC_PILOT_CONFIG_PATH, overrides())

    @patch("netpulse.burst.subprocess.run")
    @patch("netpulse.burst.shutil.which", return_value="/usr/local/bin/iperf3")
    def test_iperf3_version_is_required(self, _which, run):
        run.return_value = argparse.Namespace(returncode=0, stdout="iperf version 2.2.0", stderr="")
        with self.assertRaisesRegex(ValueError, "requires iperf3"):
            iperf3_path("iperf3")
        run.return_value = argparse.Namespace(returncode=0, stdout="iperf 3.22", stderr="")
        self.assertEqual(iperf3_path("iperf3"), ("/usr/local/bin/iperf3", "iperf 3.22"))


class BurstRunTests(unittest.TestCase):
    def test_child_output_appends_between_pulse_markers(self):
        with tempfile.TemporaryDirectory() as temporary:
            log_path = Path(temporary) / "iperf.log"
            with log_path.open("x", encoding="utf-8") as log:
                log.write("=== pulse 000 start ===\n")
                log.flush()
                result = send_pulse([sys.executable, "-c", "print('measured rate')"], log, 1)
                log.write("=== pulse 000 end ===\n")
            lines = log_path.read_text().splitlines()

        self.assertEqual(result, (0, "exited"))
        self.assertEqual(lines, ["=== pulse 000 start ===", "measured rate", "=== pulse 000 end ==="])

    def _args(self, output_root):
        return argparse.Namespace(
            capacity_mbps=100.0,
            target="127.0.0.1",
            port=5201,
            seed=42,
            iperf_path="iperf3",
            output_root=output_root,
            config=CONFIG_PATH,
        )

    def _config(self):
        return BurstConfig(
            duration_seconds=2,
            start_delay_seconds=0,
            on_min_seconds=1,
            on_max_seconds=1,
            off_min_seconds=1,
            off_max_seconds=1,
            rate_fraction=0.9,
        )

    @patch("netpulse.burst.time.sleep")
    @patch("netpulse.burst.send_pulse", return_value=(0, "exited"))
    @patch("netpulse.burst.iperf3_path", return_value=("/usr/local/bin/iperf3", "iperf 3.22"))
    def test_run_records_plan_and_actual_pulse(self, _path, send, _sleep):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, status = run_bursts(self._args(Path(temporary)), self._config())
            metadata = json.loads((run_dir / "run.json").read_text())
            events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
            log = (run_dir / "iperf.log").read_text()

        self.assertEqual(status, "completed")
        self.assertTrue(run_dir.name.startswith("burst-"))
        self.assertEqual(metadata["run_id"], run_dir.name)
        self.assertEqual(metadata["target_rate_bps"], 90_000_000)
        self.assertEqual(metadata["traffic_tool"], "iperf3")
        self.assertEqual(metadata["direction"], "wifi_to_ethernet")
        self.assertEqual(metadata["target_port"], 5201)
        self.assertEqual(metadata["parallel_streams"], 1)
        self.assertEqual(metadata["completed_pulses"], 1)
        self.assertEqual(events[0]["status"], "ok")
        self.assertEqual(events[0]["planned_offset_seconds"], 0)
        self.assertEqual(metadata["log_file"], "iperf.log")
        self.assertEqual(events[0]["log_file"], "iperf.log")
        self.assertIn("=== pulse 000 start", log)
        self.assertIn("=== pulse 000 end", log)
        self.assertEqual(send.call_args.args[0][-2:], ["-t", "1"])
        self.assertIn("--get-server-output", send.call_args.args[0])
        self.assertEqual(send.call_args.args[0][send.call_args.args[0].index("-b") + 1], "90000000")
        self.assertEqual(send.call_args.args[0][send.call_args.args[0].index("-p") + 1], "5201")

    @patch("netpulse.burst.time.sleep")
    @patch("netpulse.burst.send_pulse", return_value=(0, "exited"))
    @patch("netpulse.burst.iperf3_path", return_value=("/usr/local/bin/iperf3", "iperf 3.22"))
    def test_fixed_rate_run_records_target_without_inventing_capacity(self, _path, send, _sleep):
        config = BurstConfig(
            duration_seconds=2, start_delay_seconds=0,
            on_min_seconds=1, on_max_seconds=1,
            off_min_seconds=1, off_max_seconds=1,
            rate_fraction=None, fixed_target_bps=350_000_000,
        )
        with tempfile.TemporaryDirectory() as temporary:
            args = self._args(Path(temporary))
            args.capacity_mbps = None
            args.config = FIXED_CONFIG_PATH
            run_dir, status = run_bursts(args, config)
            metadata = json.loads((run_dir / "run.json").read_text())

        self.assertEqual(status, "completed")
        self.assertEqual(metadata["target_rate_bps"], 350_000_000)
        self.assertEqual(metadata["rate_policy"], "fixed_sender_target")
        self.assertIsNone(metadata["capacity_mbps"])
        self.assertIsNone(metadata["rate_fraction"])
        self.assertEqual(send.call_args.args[0][send.call_args.args[0].index("-b") + 1], "350000000")

    @patch("netpulse.burst.time.sleep")
    @patch("netpulse.burst.iperf3_path", return_value=("/usr/local/bin/iperf3", "iperf 3.22"))
    def test_multiple_pulses_share_one_log(self, _path, _sleep):
        def fake_send(_command, log, _duration):
            log.write("[  1] 0.00-1.00 sec  11.2 MBytes  94.0 Mbits/sec\n")
            log.flush()
            return 0, "exited"

        config = BurstConfig(
            duration_seconds=3,
            start_delay_seconds=0,
            on_min_seconds=1,
            on_max_seconds=1,
            off_min_seconds=1,
            off_max_seconds=1,
            rate_fraction=0.9,
        )
        with patch("netpulse.burst.send_pulse", side_effect=fake_send):
            with tempfile.TemporaryDirectory() as temporary:
                run_dir, status = run_bursts(self._args(Path(temporary)), config)
                log_names = sorted(path.name for path in run_dir.glob("*.log"))
                log = (run_dir / "iperf.log").read_text()
                events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]

        self.assertEqual(status, "completed")
        self.assertEqual(log_names, ["iperf.log"])
        self.assertEqual([event["log_file"] for event in events], ["iperf.log", "iperf.log"])
        self.assertLess(log.index("=== pulse 000 start"), log.index("=== pulse 000 end"))
        self.assertLess(log.index("=== pulse 000 end"), log.index("=== pulse 001 start"))
        self.assertEqual(log.count("94.0 Mbits/sec"), 2)

    @patch("netpulse.burst.time.sleep")
    @patch("netpulse.burst.send_pulse", return_value=(1, "exited"))
    @patch("netpulse.burst.iperf3_path", return_value=("/usr/local/bin/iperf3", "iperf 3.22"))
    def test_failed_iperf_pulse_fails_run(self, _path, _send, _sleep):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, status = run_bursts(self._args(Path(temporary)), self._config())
            metadata = json.loads((run_dir / "run.json").read_text())
            event = json.loads((run_dir / "events.jsonl").read_text().splitlines()[0])

        self.assertEqual(status, "failed")
        self.assertEqual(metadata["completed_pulses"], 0)
        self.assertEqual(event["status"], "process_error")

    @patch("netpulse.burst.time.sleep", side_effect=KeyboardInterrupt)
    @patch("netpulse.burst.iperf3_path", return_value=("/usr/local/bin/iperf3", "iperf 3.22"))
    def test_interruption_before_first_pulse_records_status(self, _path, _sleep):
        config = BurstConfig(
            duration_seconds=3,
            start_delay_seconds=1,
            on_min_seconds=1,
            on_max_seconds=1,
            off_min_seconds=1,
            off_max_seconds=1,
            rate_fraction=0.9,
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, status = run_bursts(self._args(Path(temporary)), config)
            metadata = json.loads((run_dir / "run.json").read_text())

        self.assertEqual(status, "interrupted")
        self.assertEqual(metadata["status"], "interrupted")

    @patch("netpulse.burst.time.sleep")
    @patch("netpulse.burst.send_pulse", side_effect=KeyboardInterrupt)
    @patch("netpulse.burst.iperf3_path", return_value=("/usr/local/bin/iperf3", "iperf 3.22"))
    def test_interruption_during_pulse_records_status(self, _path, _send, _sleep):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, status = run_bursts(self._args(Path(temporary)), self._config())
            metadata = json.loads((run_dir / "run.json").read_text())
            event = json.loads((run_dir / "events.jsonl").read_text().splitlines()[0])

        self.assertEqual(status, "interrupted")
        self.assertEqual(metadata["status"], "interrupted")
        self.assertEqual(event["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
