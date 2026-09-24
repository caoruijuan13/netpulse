"""Run separate, short ping diagnostics without producing M0 training data."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from netpulse.collect import append_probe, classify_ping, load_config, local_ipv4, utc_now, write_metadata


OUTPUT_LIMIT = 4000


def _output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[:OUTPUT_LIMIT]


def diagnose_once(command: list[str], process_timeout_seconds: float) -> dict[str, Any]:
    started_at_utc = utc_now()
    started_ns = time.monotonic_ns()
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=process_timeout_seconds,
            env=environment,
            check=False,
        )
        status, rtt_ms, error_code = classify_ping(result.returncode, result.stdout, result.stderr)
        returncode = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        status, rtt_ms, error_code = "process_timeout", None, "ping_process_timeout"
        returncode = None
        stdout = exc.stdout
        stderr = exc.stderr
    except OSError as exc:
        status, rtt_ms, error_code = "spawn_error", None, "ping_spawn_error"
        returncode = None
        stdout = ""
        stderr = str(exc)
    return {
        "started_at_utc": started_at_utc,
        "ended_at_utc": utc_now(),
        "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000,
        "status": status,
        "rtt_ms": rtt_ms,
        "error_code": error_code,
        "returncode": returncode,
        "stdout": _output_text(stdout),
        "stderr": _output_text(stderr),
    }


def run_diagnostic(args: argparse.Namespace) -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("ping diagnostics support macOS only")
    ping_path = shutil.which("ping")
    if ping_path is None:
        raise RuntimeError("ping was not found")
    config = load_config(args.config)
    if args.scenario not in config.scenarios:
        raise ValueError(f"scenario must be one of: {', '.join(config.scenarios)}")
    if args.samples <= 0:
        raise ValueError("samples must be positive")
    if not math.isfinite(args.process_timeout_seconds) or args.process_timeout_seconds <= config.timeout_ms / 1000:
        raise ValueError("process timeout must exceed the ICMP reply timeout")

    run_id = "pingdiag-" + args.scenario + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    command = [
        ping_path, "-n", "-c", "1", "-s", str(config.payload_bytes),
        "-W", str(config.timeout_ms), "-b", args.source_interface, args.target,
    ]
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "diagnostic_only": True,
        "scenario": args.scenario,
        "load_run_id": args.load_run_id,
        "started_at_utc": utc_now(),
        "ended_at_utc": None,
        "run_status": "running",
        "command": command,
        "reply_timeout_ms": config.timeout_ms,
        "process_timeout_seconds": args.process_timeout_seconds,
        "minimum_start_interval_seconds": config.interval_ns / 1_000_000_000,
        "requested_samples": args.samples,
        "recorded_samples": 0,
        "counts": {},
    }
    metadata_path = run_dir / "run.json"
    write_metadata(metadata_path, metadata)
    counts: dict[str, int] = {}
    run_status = "completed"
    try:
        with (run_dir / "samples.jsonl").open("x", encoding="utf-8") as output:
            for seq in range(args.samples):
                sample_start_ns = time.monotonic_ns()
                record = {"seq": seq, **diagnose_once(command, args.process_timeout_seconds)}
                append_probe(output, record)
                counts[record["status"]] = counts.get(record["status"], 0) + 1
                if seq + 1 < args.samples:
                    remaining_ns = config.interval_ns - (time.monotonic_ns() - sample_start_ns)
                    if remaining_ns > 0:
                        time.sleep(remaining_ns / 1_000_000_000)
    except KeyboardInterrupt:
        run_status = "interrupted"
    except Exception as exc:
        run_status = "failed"
        metadata["failure_reason"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        metadata["ended_at_utc"] = utc_now()
        metadata["run_status"] = run_status
        metadata["recorded_samples"] = sum(counts.values())
        metadata["counts"] = counts
        write_metadata(metadata_path, metadata)
    return run_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/pilot.toml"))
    parser.add_argument("--target", type=local_ipv4, required=True)
    parser.add_argument("--source-interface", required=True)
    parser.add_argument("--scenario", required=True, help="label for the diagnostic run; does not create load")
    parser.add_argument("--load-run-id", help="optional ID of a separately running iperf load")
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--process-timeout-seconds", type=float, default=3.0)
    parser.add_argument("--output-root", type=Path, default=Path("data/diagnostics"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        run_dir = run_diagnostic(parse_args(argv))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"ping diagnostic error: {exc}", file=sys.stderr)
        return 1
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    print(f"Ping diagnostic {metadata['run_status']}; saved to {run_dir}")
    return 0 if metadata["run_status"] == "completed" else 130


if __name__ == "__main__":
    raise SystemExit(main())
