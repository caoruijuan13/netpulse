import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netpulse.burst import BurstConfig, load_burst_config, plan_bursts, positive_float, run_bursts, send_pulse


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "pilot.toml"


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

    def test_invalid_rate_and_duration_are_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_float("nan")
        with self.assertRaises(ValueError):
            load_burst_config(CONFIG_PATH, overrides(duration_seconds=5, start_delay_seconds=5))


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
            seed=42,
            iperf_path="iperf",
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
    @patch("netpulse.burst.iperf2_path", return_value=("/usr/local/bin/iperf", "iperf version 2.2.0"))
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
        self.assertEqual(metadata["write_buffer_bytes"], 131_072)
        self.assertEqual(metadata["completed_pulses"], 1)
        self.assertEqual(events[0]["status"], "ok")
        self.assertEqual(events[0]["planned_offset_seconds"], 0)
        self.assertEqual(metadata["log_file"], "iperf.log")
        self.assertEqual(events[0]["log_file"], "iperf.log")
        self.assertIn("=== pulse 000 start", log)
        self.assertIn("=== pulse 000 end", log)
        self.assertEqual(send.call_args.args[0][-2:], ["-t", "1"])

    @patch("netpulse.burst.time.sleep")
    @patch("netpulse.burst.iperf2_path", return_value=("/usr/local/bin/iperf", "iperf version 2.2.0"))
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
    @patch("netpulse.burst.iperf2_path", return_value=("/usr/local/bin/iperf", "iperf version 2.2.0"))
    def test_failed_iperf_pulse_fails_run(self, _path, _send, _sleep):
        with tempfile.TemporaryDirectory() as temporary:
            run_dir, status = run_bursts(self._args(Path(temporary)), self._config())
            metadata = json.loads((run_dir / "run.json").read_text())
            event = json.loads((run_dir / "events.jsonl").read_text().splitlines()[0])

        self.assertEqual(status, "failed")
        self.assertEqual(metadata["completed_pulses"], 0)
        self.assertEqual(event["status"], "process_error")


if __name__ == "__main__":
    unittest.main()
