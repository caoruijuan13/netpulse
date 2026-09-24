import argparse
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from netpulse.collect import classify_ping, collect, load_config, local_ipv4, probe_once


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "pilot.toml"
FROZEN_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "m0-v1.toml"


class PilotConfigTests(unittest.TestCase):
    def test_loads_pilot_settings(self):
        config = load_config(CONFIG_PATH)
        self.assertEqual(config.timeout_ms, 800)
        self.assertEqual(config.interval_ns, 1_000_000_000)
        self.assertEqual(config.future_samples, 60)
        self.assertEqual((config.source_link, config.target_link), ("ethernet", "wifi"))
        self.assertIn("idle", config.scenarios)

    def test_loads_frozen_m0_settings(self):
        config = load_config(FROZEN_CONFIG_PATH)
        self.assertEqual((config.experiment_id, config.status), ("m0-v1", "frozen"))
        self.assertEqual(config.minimum_successful_probes, 57)
        self.assertEqual(config.scenarios, ("idle", "upload", "download", "burst"))

    def test_target_must_be_local_ipv4(self):
        self.assertEqual(local_ipv4("192.168.1.2"), "192.168.1.2")
        with self.assertRaises(argparse.ArgumentTypeError):
            local_ipv4("8.8.8.8")

    def test_scenario_name_cannot_escape_raw_directory(self):
        source = CONFIG_PATH.read_text()
        modified = source.replace('scenarios = ["idle",', 'scenarios = ["../idle",', 1)
        self.assertNotEqual(source, modified)
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "pilot.toml"
            config_path.write_text(modified)
            with self.assertRaisesRegex(ValueError, "safe lowercase names"):
                load_config(config_path)


class PingResultTests(unittest.TestCase):
    def test_success_uses_single_reply_rtt(self):
        output = "64 bytes from 127.0.0.1: icmp_seq=0 ttl=64 time=0.084 ms\n"
        self.assertEqual(classify_ping(0, output, ""), ("ok", 0.084, None))

    def test_no_reply_is_timeout(self):
        output = "1 packets transmitted, 0 packets received, 100.0% packet loss\n"
        self.assertEqual(classify_ping(2, output, ""), ("timeout", None, "no_reply"))

    def test_send_failure_is_not_reported_as_loss(self):
        output = "1 packets transmitted, 0 packets received, 100.0% packet loss\n"
        status, rtt, error = classify_ping(2, output, "ping: sendto: Operation not permitted")
        self.assertEqual((status, rtt, error), ("send_error", None, "ping_exit_2"))

    def test_unparsed_success_is_an_error(self):
        self.assertEqual(classify_ping(0, "unexpected reply", ""), ("send_error", None, "unparsed_reply"))

    @patch("netpulse.collect.subprocess.run")
    @patch("netpulse.collect.time.monotonic_ns", return_value=100_000_000)
    def test_process_wait_ends_before_next_slot(self, _clock, run):
        run.side_effect = subprocess.TimeoutExpired("ping", 0.9)
        result = probe_once("/sbin/ping", "127.0.0.1", "lo0", load_config(CONFIG_PATH), 1_100_000_000)
        self.assertEqual(result[:3], ("send_error", None, "ping_process_timeout"))
        self.assertAlmostEqual(run.call_args.kwargs["timeout"], 0.9)

    @patch("netpulse.collect.subprocess.run")
    @patch("netpulse.collect.time.monotonic_ns", return_value=1_000_000_000)
    def test_expired_process_deadline_does_not_start_ping(self, _clock, run):
        result = probe_once("/sbin/ping", "127.0.0.1", "lo0", load_config(CONFIG_PATH), 1_100_000_000)
        self.assertEqual(result[:3], ("send_error", None, "ping_process_deadline_expired"))
        run.assert_not_called()


class SessionTests(unittest.TestCase):
    @patch("netpulse.collect.probe_once", return_value=("ok", 0.25, None, None))
    @patch("netpulse.collect.shutil.which", return_value="/sbin/ping")
    def test_writes_one_probe_and_final_metadata(self, _which, _probe):
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(
                scenario="idle",
                traffic_tool=None,
                traffic_settings_json=None,
                duration_seconds=1,
                config=CONFIG_PATH,
                output_root=Path(temporary),
                source_interface="lo0",
                source_link="loopback",
                target_link="loopback",
                target="127.0.0.1",
                environment_notes="test",
            )
            session_dir = collect(args, load_config(CONFIG_PATH))
            metadata = json.loads((session_dir / "session.json").read_text())
            probes = [json.loads(line) for line in (session_dir / "probes.jsonl").read_text().splitlines()]

        self.assertEqual(metadata["run_status"], "completed")
        self.assertTrue(session_dir.name.startswith("idle-"))
        self.assertEqual(metadata["session_id"], session_dir.name)
        self.assertEqual(metadata["expected_probe_slots"], 1)
        self.assertEqual(metadata["recorded_probe_slots"], 1)
        self.assertEqual(metadata["probe_counts"]["ok"], 1)
        self.assertEqual(metadata["target_percentile"], 95)
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0]["status"], "ok")
        self.assertEqual(probes[0]["rtt_ms"], 0.25)
        self.assertEqual(probes[0]["session_id"], metadata["session_id"])

    @patch("netpulse.collect.subprocess.run")
    @patch("netpulse.collect.shutil.which", return_value="/sbin/ping")
    @patch("netpulse.collect.platform.platform", return_value="Darwin-test")
    def test_ping_process_timeout_does_not_force_next_slot_to_be_missed(self, _platform, _which, run):
        def ping_result(*args, **kwargs):
            if run.call_count == 1:
                time.sleep(kwargs["timeout"])
                raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
            return subprocess.CompletedProcess(args[0], 0, "64 bytes: icmp_seq=0 time=1.0 ms\n", "")

        run.side_effect = ping_result
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(
                scenario="idle",
                traffic_tool=None,
                traffic_settings_json=None,
                duration_seconds=2,
                config=CONFIG_PATH,
                output_root=Path(temporary),
                source_interface="lo0",
                source_link="loopback",
                target_link="loopback",
                target="127.0.0.1",
                environment_notes="test",
            )
            session_dir = collect(args, load_config(CONFIG_PATH))
            metadata = json.loads((session_dir / "session.json").read_text())
            probes = [json.loads(line) for line in (session_dir / "probes.jsonl").read_text().splitlines()]

        self.assertEqual(metadata["run_status"], "completed")
        self.assertEqual([probe["status"] for probe in probes], ["send_error", "ok"])
        self.assertEqual(probes[0]["error_code"], "ping_process_timeout")
        self.assertEqual(metadata["probe_counts"]["missed_slot"], 0)


if __name__ == "__main__":
    unittest.main()
