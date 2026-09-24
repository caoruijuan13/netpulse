import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netpulse.diagnose_ping import diagnose_once, run_diagnostic


CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "pilot.toml"


class DiagnoseOnceTests(unittest.TestCase):
    @patch("netpulse.diagnose_ping.subprocess.run")
    def test_completed_ping_keeps_result_and_output(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["ping"], 0, "64 bytes: icmp_seq=0 time=4.2 ms\n", ""
        )
        result = diagnose_once(["ping"], 3.0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["rtt_ms"], 4.2)
        self.assertEqual(result["returncode"], 0)
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        self.assertIn("icmp_seq=0", result["stdout"])
        self.assertEqual(run.call_args.kwargs["timeout"], 3.0)

    @patch("netpulse.diagnose_ping.subprocess.run")
    def test_process_timeout_keeps_partial_output(self, run):
        run.side_effect = subprocess.TimeoutExpired(
            ["ping"], 3.0, output=b"PING target\n", stderr=b"partial diagnostic\n"
        )
        result = diagnose_once(["ping"], 3.0)
        self.assertEqual(result["status"], "process_timeout")
        self.assertIsNone(result["returncode"])
        self.assertEqual(result["stdout"], "PING target\n")
        self.assertEqual(result["stderr"], "partial diagnostic\n")


class DiagnosticRunTests(unittest.TestCase):
    @patch("netpulse.diagnose_ping.time.sleep")
    @patch("netpulse.diagnose_ping.diagnose_once")
    @patch("netpulse.diagnose_ping.shutil.which", return_value="/sbin/ping")
    @patch("netpulse.diagnose_ping.platform.system", return_value="Darwin")
    def test_writes_separate_diagnostic_run(self, _system, _which, diagnose, _sleep):
        diagnose.return_value = {
            "started_at_utc": "2026-09-24T00:00:00+00:00",
            "ended_at_utc": "2026-09-24T00:00:01+00:00",
            "elapsed_ms": 850,
            "status": "timeout",
            "rtt_ms": None,
            "error_code": "no_reply",
            "returncode": 2,
            "stdout": "0 packets received",
            "stderr": "",
        }
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(
                config=CONFIG_PATH,
                target="127.0.0.1",
                source_interface="lo0",
                scenario="upload",
                load_run_id="upload-test",
                samples=2,
                process_timeout_seconds=3.0,
                output_root=Path(temporary),
            )
            run_dir = run_diagnostic(args)
            metadata = json.loads((run_dir / "run.json").read_text())
            records = [json.loads(line) for line in (run_dir / "samples.jsonl").read_text().splitlines()]

        self.assertTrue(run_dir.name.startswith("pingdiag-upload-"))
        self.assertTrue(metadata["diagnostic_only"])
        self.assertEqual(metadata["load_run_id"], "upload-test")
        self.assertEqual(metadata["run_status"], "completed")
        self.assertEqual(metadata["counts"], {"timeout": 2})
        self.assertEqual([record["seq"] for record in records], [0, 1])
        self.assertEqual(metadata["command"][-3:], ["-b", "lo0", "127.0.0.1"])


if __name__ == "__main__":
    unittest.main()
