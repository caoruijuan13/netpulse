"""Generate logged, reproducible Mac-to-PC TCP bursts with iperf2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import shutil
import subprocess
import sys
import time
import tomllib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from netpulse.collect import local_ipv4, utc_now, write_metadata


BURST_VERSION = "m0-burst-3"
IPERF_LOG_NAME = "iperf.log"


@dataclass(frozen=True)
class BurstConfig:
    duration_seconds: int
    start_delay_seconds: int
    on_min_seconds: int
    on_max_seconds: int
    off_min_seconds: int
    off_max_seconds: int
    rate_fraction: float


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a number") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("value must be positive and finite")
    return number


def load_burst_config(path: Path, overrides: argparse.Namespace) -> BurstConfig:
    with path.open("rb") as file:
        data = tomllib.load(file)
    burst = data["burst"]
    fraction = data["load"]["burst_rate_fraction"]
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError("load.burst_rate_fraction must be between 0 and 1")

    def setting(name: str, minimum: int) -> int:
        override = getattr(overrides, name)
        return _integer(burst[name] if override is None else override, name, minimum=minimum)

    config = BurstConfig(
        duration_seconds=setting("duration_seconds", 1),
        start_delay_seconds=setting("start_delay_seconds", 0),
        on_min_seconds=setting("on_min_seconds", 1),
        on_max_seconds=setting("on_max_seconds", 1),
        off_min_seconds=setting("off_min_seconds", 1),
        off_max_seconds=setting("off_max_seconds", 1),
        rate_fraction=float(fraction),
    )
    if config.on_min_seconds > config.on_max_seconds or config.off_min_seconds > config.off_max_seconds:
        raise ValueError("burst minimum durations must not exceed maximum durations")
    if config.start_delay_seconds + config.on_min_seconds > config.duration_seconds:
        raise ValueError("burst duration is too short for one pulse")
    return config


def plan_bursts(config: BurstConfig, seed: int) -> list[dict[str, int]]:
    rng = random.Random(seed)
    planned: list[dict[str, int]] = []
    offset = config.start_delay_seconds
    while offset + config.on_min_seconds <= config.duration_seconds:
        on_seconds = rng.randint(config.on_min_seconds, config.on_max_seconds)
        if offset + on_seconds > config.duration_seconds:
            break
        off_seconds = rng.randint(config.off_min_seconds, config.off_max_seconds)
        planned.append({
            "pulse_index": len(planned),
            "planned_offset_seconds": offset,
            "on_seconds": on_seconds,
            "off_seconds_after": off_seconds,
        })
        offset += on_seconds + off_seconds
    return planned


def iperf2_path(candidate: str) -> tuple[str, str]:
    path = shutil.which(candidate)
    if path is None:
        raise ValueError(f"iperf executable not found: {candidate}")
    version = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, check=False)
    version_text = (version.stdout + " " + version.stderr).strip()
    if version.returncode != 0 or not version_text.startswith("iperf version 2."):
        raise ValueError("burst generator requires iperf2 on the MacBook")
    return path, version_text


def _stop_process(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def send_pulse(command: list[str], log: TextIO, on_seconds: int) -> tuple[int | None, str]:
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        return process.wait(timeout=on_seconds + 5), "exited"
    except subprocess.TimeoutExpired:
        _stop_process(process)
        return process.returncode, "process_timeout"
    except KeyboardInterrupt:
        _stop_process(process)
        raise


def run_bursts(args: argparse.Namespace, config: BurstConfig) -> tuple[Path, str]:
    if platform.system() != "Darwin":
        raise ValueError("this Mac-to-PC burst generator supports macOS only")
    path, version = iperf2_path(args.iperf_path)
    rate_bps = round(args.capacity_mbps * 1_000_000 * config.rate_fraction)
    if rate_bps < 1:
        raise ValueError("calibrated target rate is less than 1 bit/s")
    if rate_bps < 16_384:
        raise ValueError("calibrated target rate is too low for a 1 KiB iperf2 write buffer")
    write_buffer_bytes = min(131_072, rate_bps // 16)
    planned = plan_bursts(config, args.seed)
    run_id = "burst-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    metadata_path = run_dir / "run.json"
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "running",
        "started_at_utc": utc_now(),
        "ended_at_utc": None,
        "target_address": args.target,
        "direction": "mac_to_pc",
        "traffic_tool": "iperf2",
        "traffic_tool_version": version,
        "generator_version": BURST_VERSION,
        "generator_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "config_source_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "capacity_mbps": args.capacity_mbps,
        "rate_fraction": config.rate_fraction,
        "target_rate_bps": rate_bps,
        "write_buffer_bytes": write_buffer_bytes,
        "seed": args.seed,
        "duration_seconds": config.duration_seconds,
        "start_delay_seconds": config.start_delay_seconds,
        "on_min_seconds": config.on_min_seconds,
        "on_max_seconds": config.on_max_seconds,
        "off_min_seconds": config.off_min_seconds,
        "off_max_seconds": config.off_max_seconds,
        "planned_pulses": planned,
        "completed_pulses": 0,
        "log_file": IPERF_LOG_NAME,
    }
    write_metadata(metadata_path, metadata)
    print(f"Burst run {run_id}; logs: {run_dir}", flush=True)
    command_base = [
        path, "-c", args.target, "-b", str(rate_bps),
        "-l", str(write_buffer_bytes), "-i", "1",
    ]
    status = "completed"
    start_ns = time.monotonic_ns()
    try:
        with (run_dir / "events.jsonl").open("x", encoding="utf-8") as events, \
                (run_dir / IPERF_LOG_NAME).open("x", encoding="utf-8") as iperf_log:
            for pulse in planned:
                scheduled_ns = start_ns + pulse["planned_offset_seconds"] * 1_000_000_000
                remaining_ns = scheduled_ns - time.monotonic_ns()
                if remaining_ns > 0:
                    time.sleep(remaining_ns / 1_000_000_000)
                actual_start_ns = time.monotonic_ns()
                event: dict[str, Any] = {
                    **pulse,
                    "started_at_utc": utc_now(),
                    "start_offset_seconds": (actual_start_ns - start_ns) / 1_000_000_000,
                    "ended_at_utc": None,
                    "actual_duration_seconds": None,
                    "returncode": None,
                    "status": "running",
                    "log_file": IPERF_LOG_NAME,
                }
                iperf_log.write(
                    f"\n=== pulse {pulse['pulse_index']:03d} start "
                    f"utc={event['started_at_utc']} "
                    f"planned_offset_seconds={pulse['planned_offset_seconds']} "
                    f"on_seconds={pulse['on_seconds']} ===\n"
                )
                iperf_log.flush()
                try:
                    returncode, process_status = send_pulse(
                        command_base + ["-t", str(pulse["on_seconds"])],
                        iperf_log,
                        pulse["on_seconds"],
                    )
                    event["returncode"] = returncode
                    if process_status == "exited":
                        event["status"] = "ok" if returncode == 0 else "process_error"
                    else:
                        event["status"] = process_status
                except KeyboardInterrupt:
                    event["status"] = "interrupted"
                    status = "interrupted"
                except OSError as exc:
                    event["status"] = "spawn_error"
                    event["error"] = str(exc)[:1000]
                    status = "failed"
                event["ended_at_utc"] = utc_now()
                event["actual_duration_seconds"] = (time.monotonic_ns() - actual_start_ns) / 1_000_000_000
                iperf_log.write(
                    f"=== pulse {pulse['pulse_index']:03d} end "
                    f"utc={event['ended_at_utc']} "
                    f"status={event['status']} returncode={event['returncode']} ===\n"
                )
                iperf_log.flush()
                events.write(json.dumps(event, separators=(",", ":")) + "\n")
                events.flush()
                if event["status"] == "ok":
                    metadata["completed_pulses"] += 1
                else:
                    status = "interrupted" if event["status"] == "interrupted" else "failed"
                    break
            if status == "completed":
                remaining_ns = start_ns + config.duration_seconds * 1_000_000_000 - time.monotonic_ns()
                if remaining_ns > 0:
                    time.sleep(remaining_ns / 1_000_000_000)
    except KeyboardInterrupt:
        status = "interrupted"
    except Exception as exc:
        status = "failed"
        metadata["failure_reason"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        metadata["status"] = status
        metadata["ended_at_utc"] = utc_now()
        write_metadata(metadata_path, metadata)
    return run_dir, status


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/pilot.toml"))
    parser.add_argument("--target", type=local_ipv4, required=True, help="local Windows PC IPv4 address")
    parser.add_argument("--capacity-mbps", type=positive_float, required=True, help="measured Mac-to-PC TCP capacity")
    parser.add_argument("--seed", type=int, required=True, help="recorded seed for the pulse schedule")
    parser.add_argument("--iperf-path", default="iperf", help="path to the MacBook iperf2 executable")
    parser.add_argument("--output-root", type=Path, default=Path("data/load"))
    for name in (
        "duration_seconds", "start_delay_seconds", "on_min_seconds", "on_max_seconds",
        "off_min_seconds", "off_max_seconds",
    ):
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        run_dir, status = run_bursts(args, load_burst_config(args.config, args))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f"burst generation error: {exc}", file=sys.stderr)
        return 1
    print(f"Burst run {status}; logs: {run_dir}")
    return 0 if status == "completed" else 130 if status == "interrupted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
