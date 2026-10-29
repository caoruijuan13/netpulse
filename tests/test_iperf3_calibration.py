import json
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_iperf3_calibration import capacity_from_summary, receiver_mbps, summarize


class Iperf3CalibrationTests(unittest.TestCase):
    def test_receiver_summary_and_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for direction, rates in (("upload", (100, 110, 90)), ("download", (200, 220, 180))):
                for index, rate in enumerate(rates, 1):
                    (directory / f"{direction}-{index}.json").write_text(
                        json.dumps({"end": {"sum_received": {"bits_per_second": rate * 1_000_000}}}),
                        encoding="utf-8",
                    )
            summary = summarize(directory)

        self.assertEqual(summary["directions"]["upload"]["capacity_mbps"], 100)
        self.assertEqual(summary["directions"]["upload"]["sustained_target_bps"], 70_000_000)
        self.assertEqual(summary["directions"]["download"]["capacity_mbps"], 200)
        self.assertEqual(summary["burst_target_bps"], 90_000_000)

    def test_capacity_is_read_from_saved_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "summary.json"
            path.write_text(json.dumps({"directions": {"upload": {"capacity_mbps": 123.5}}}), encoding="utf-8")
            self.assertEqual(capacity_from_summary(path, "upload"), 123.5)
            with self.assertRaisesRegex(ValueError, "missing download capacity"):
                capacity_from_summary(path, "download")

    def test_error_or_missing_receiver_summary_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "upload-1.json"
            path.write_text(json.dumps({"error": "connection refused"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "connection refused"):
                receiver_mbps(path)
            path.write_text(json.dumps({"end": {"sum_sent": {"bits_per_second": 100}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing receiver-side summary"):
                receiver_mbps(path)


if __name__ == "__main__":
    unittest.main()
