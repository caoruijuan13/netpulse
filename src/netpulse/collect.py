"""Collect one macOS ICMP Echo pilot session without deriving model features."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import tomllib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
COLLECTOR_VERSION = "m0-pilot-3"
PROCESS_DEADLINE_MARGIN_NS = 100_000_000
RTT_PATTERN = re.compile(r"\bicmp_seq=\d+\b[^\n]*\btime=([0-9]+(?:\.[0-9]+)?)\s*ms\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class PilotConfig:
    experiment_id: str
    status: str
    source_link: str
    target_link: str
    payload_bytes: int
    interval_ns: int
    timeout_ms: int
    max_start_lateness_ns: int
    duration_seconds: int
    warmup_seconds: int
    history_samples: int
    future_samples: int
    window_stride_samples: int
    minimum_successful_probes: int
    target_percentile: int
    percentile_method: str
    scenarios: tuple[str, ...]


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def load_config(path: Path) -> PilotConfig:
    with path.open("rb") as file:
        data = tomllib.load(file)
    experiment = data["experiment"]
    topology = data["topology"]
    prediction = data["prediction"]
    pilot = data["pilot"]
    if experiment["probe_protocol"] != "icmp_echo":
        raise ValueError("the M0 collector supports only icmp_echo")
    if experiment["status"] not in ("draft", "frozen"):
        raise ValueError("experiment.status must be draft or frozen")
    interval = experiment["probe_interval_seconds"]
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
        raise ValueError("probe_interval_seconds must be a positive finite number")
    interval_ns = round(interval * 1_000_000_000)
    if interval_ns <= 0:
        raise ValueError("probe_interval_seconds is too small")
    timeout_ms = _positive_int(experiment["probe_timeout_ms"], "probe_timeout_ms")
    lateness_ms = _positive_int(experiment["max_start_lateness_ms"], "max_start_lateness_ms")
    if timeout_ms >= interval * 1000:
        raise ValueError("probe_timeout_ms must be shorter than the probe interval")
    if lateness_ms >= interval * 1000:
        raise ValueError("max_start_lateness_ms must be shorter than the probe interval")
    scenarios = pilot["scenarios"]
    if not isinstance(scenarios, list) or not scenarios or any(not isinstance(x, str) or not x for x in scenarios):
        raise ValueError("pilot.scenarios must be a nonempty list of names")
    if len(set(scenarios)) != len(scenarios):
        raise ValueError("pilot.scenarios must be unique")
    if any(re.fullmatch(r"[a-z][a-z0-9_-]*", scenario) is None for scenario in scenarios):
        raise ValueError("pilot.scenarios must be safe lowercase names")
    payload_bytes = _positive_int(experiment["probe_payload_bytes"], "probe_payload_bytes")
    if payload_bytes < 8:
        raise ValueError("probe_payload_bytes must be at least 8 for ping RTT measurement")
    history_samples = _positive_int(prediction["history_samples"], "history_samples")
    future_samples = _positive_int(prediction["future_samples"], "future_samples")
    minimum_successful = _positive_int(prediction["minimum_successful_probes"], "minimum_successful_probes")
    if minimum_successful > min(history_samples, future_samples):
        raise ValueError("minimum_successful_probes exceeds a prediction window")
    target_percentile = _positive_int(prediction["target_percentile"], "target_percentile")
    if target_percentile > 100 or prediction["percentile_method"] != "nearest_rank":
        raise ValueError("only a nearest-rank percentile between 1 and 100 is supported")
    duration_seconds = _positive_int(experiment["session_duration_seconds"], "session_duration_seconds")
    warmup_seconds = _positive_int(experiment["warmup_seconds"], "warmup_seconds")
    if warmup_seconds >= duration_seconds:
        raise ValueError("warmup_seconds must be shorter than session_duration_seconds")
    _positive_int(pilot["sessions_per_scenario"], "sessions_per_scenario")
    source_link = topology["source_link"]
    target_link = topology["target_link"]
    if source_link not in ("ethernet", "wifi") or target_link not in ("ethernet", "wifi"):
        raise ValueError("topology links must be ethernet or wifi")
    return PilotConfig(
        experiment_id=str(experiment["id"]),
        status=str(experiment["status"]),
        source_link=source_link,
        target_link=target_link,
        payload_bytes=payload_bytes,
        interval_ns=interval_ns,
        timeout_ms=timeout_ms,
        max_start_lateness_ns=lateness_ms * 1_000_000,
        duration_seconds=duration_seconds,
        warmup_seconds=warmup_seconds,
        history_samples=history_samples,
        future_samples=future_samples,
        window_stride_samples=_positive_int(prediction["window_stride_samples"], "window_stride_samples"),
        minimum_successful_probes=minimum_successful,
        target_percentile=target_percentile,
        percentile_method="nearest_rank",
        scenarios=tuple(scenarios),
    )


def local_ipv4(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("target must be a numeric IPv4 address") from exc
    if address.is_global or address.is_multicast or address.is_unspecified:
        raise argparse.ArgumentTypeError("target must be a local unicast IPv4 address")
    return str(address)


def classify_ping(returncode: int, stdout: str, stderr: str) -> tuple[str, float | None, str | None]:
    output = stdout + "\n" + stderr
    match = RTT_PATTERN.search(stdout)
    if returncode == 0 and match:
        rtt_ms = float(match.group(1))
        if math.isfinite(rtt_ms) and rtt_ms >= 0:
            return "ok", rtt_ms, None
    if returncode == 2 and "0 packets received" in stdout and "sendto:" not in output and "ping:" not in stderr:
        return "timeout", None, "no_reply"
    if returncode == 0:
        return "send_error", None, "unparsed_reply"
    return "send_error", None, f"ping_exit_{returncode}"


def probe_once(
    ping_path: str, target: str, interface: str, config: PilotConfig, next_slot_ns: int
) -> tuple[str, float | None, str | None, str | None]:
    command = [
        ping_path, "-n", "-c", "1", "-s", str(config.payload_bytes),
        "-W", str(config.timeout_ms), "-b", interface, target,
    ]
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    remaining_seconds = (next_slot_ns - PROCESS_DEADLINE_MARGIN_NS - time.monotonic_ns()) / 1_000_000_000
    if remaining_seconds <= 0:
        return "send_error", None, "ping_process_deadline_expired", None
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=min(config.timeout_ms / 1000 + 0.75, remaining_seconds),
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "send_error", None, "ping_process_timeout", None
    except OSError as exc:
        return "send_error", None, "ping_spawn_error", str(exc)[:1000]
    status, rtt_ms, error_code = classify_ping(result.returncode, result.stdout, result.stderr)
    diagnostic = None if status == "ok" else (result.stdout + "\n" + result.stderr).strip()[:1000]
    return status, rtt_ms, error_code, diagnostic


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_probe(file: Any, record: dict[str, Any]) -> None:
    file.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
    file.flush()


def collect(args: argparse.Namespace, config: PilotConfig) -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("this pilot collector supports macOS only")
    ping_path = shutil.which("ping")
    if ping_path is None:
        raise RuntimeError("ping was not found")
    if args.scenario not in config.scenarios:
        raise ValueError(f"scenario must be one of: {', '.join(config.scenarios)}")
    if args.scenario == "idle" and (args.traffic_tool or args.traffic_settings_json):
        raise ValueError("idle sessions must not declare a traffic generator")
    if args.scenario != "idle" and not args.traffic_tool:
        raise ValueError("non-idle sessions require --traffic-tool")
    traffic_settings = None
    if args.traffic_settings_json:
        traffic_settings = json.loads(args.traffic_settings_json)
        if not isinstance(traffic_settings, dict):
            raise ValueError("--traffic-settings-json must contain a JSON object")
    if args.scenario != "idle" and traffic_settings is None:
        raise ValueError("non-idle sessions require --traffic-settings-json")

    duration_seconds = args.duration_seconds or config.duration_seconds
    slot_count_float = duration_seconds * 1_000_000_000 / config.interval_ns
    slot_count = round(slot_count_float)
    if not math.isclose(slot_count_float, slot_count, abs_tol=1e-9) or slot_count <= 0:
        raise ValueError("duration must contain a whole number of probe intervals")

    session_id = args.scenario + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    session_dir = args.output_root / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    metadata_path = session_dir / "session.json"
    source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    config_hash = hashlib.sha256(args.config.read_bytes()).hexdigest()
    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "experiment_id": config.experiment_id,
        "experiment_status": config.status,
        "scenario": args.scenario,
        "started_at_utc": utc_now(),
        "ended_at_utc": None,
        "run_status": "running",
        "collector_version": COLLECTOR_VERSION,
        "collector_source_sha256": source_hash,
        "config_source_sha256": config_hash,
        "source_os": platform.platform(),
        "source_interface": args.source_interface,
        "source_link": args.source_link or config.source_link,
        "target_link": args.target_link or config.target_link,
        "target_address": args.target,
        "probe_protocol": "icmp_echo",
        "probe_payload_bytes": config.payload_bytes,
        "probe_interval_seconds": config.interval_ns / 1_000_000_000,
        "probe_timeout_ms": config.timeout_ms,
        "max_start_lateness_ms": config.max_start_lateness_ns / 1_000_000,
        "warmup_seconds": config.warmup_seconds,
        "history_samples": config.history_samples,
        "future_samples": config.future_samples,
        "window_stride_samples": config.window_stride_samples,
        "minimum_successful_probes": config.minimum_successful_probes,
        "target_percentile": config.target_percentile,
        "percentile_method": config.percentile_method,
        "planned_duration_seconds": duration_seconds,
        "expected_probe_slots": slot_count,
        "recorded_probe_slots": 0,
        "traffic_tool": args.traffic_tool,
        "traffic_settings": traffic_settings,
        "environment_notes": args.environment_notes,
    }
    write_metadata(metadata_path, metadata)

    run_status = "completed"
    counts = {name: 0 for name in ("ok", "timeout", "send_error", "missed_slot")}
    start_ns = time.monotonic_ns()
    try:
        with (session_dir / "probes.jsonl").open("x", encoding="utf-8") as output:
            for seq in range(slot_count):
                scheduled_ns = start_ns + seq * config.interval_ns
                remaining_ns = scheduled_ns - time.monotonic_ns()
                if remaining_ns > 0:
                    time.sleep(remaining_ns / 1_000_000_000)
                actual_ns = time.monotonic_ns()
                record: dict[str, Any] = {
                    "schema_version": SCHEMA_VERSION,
                    "session_id": session_id,
                    "probe_seq": seq,
                    "started_at_utc": None,
                    "scheduled_monotonic_ns": scheduled_ns,
                    "started_monotonic_ns": None,
                    "status": "missed_slot",
                    "rtt_ms": None,
                    "error_code": "start_too_late",
                }
                if actual_ns - scheduled_ns <= config.max_start_lateness_ns:
                    record["started_at_utc"] = utc_now()
                    record["started_monotonic_ns"] = actual_ns
                    try:
                        status, rtt_ms, error_code, diagnostic = probe_once(
                            ping_path, args.target, args.source_interface, config,
                            scheduled_ns + config.interval_ns,
                        )
                    except KeyboardInterrupt:
                        record.update(status="send_error", error_code="interrupted")
                        append_probe(output, record)
                        counts["send_error"] += 1
                        run_status = "interrupted"
                        break
                    record.update(status=status, rtt_ms=rtt_ms, error_code=error_code)
                    if diagnostic:
                        record["diagnostic"] = diagnostic
                append_probe(output, record)
                counts[record["status"]] += 1
            if run_status == "completed":
                remaining_ns = start_ns + slot_count * config.interval_ns - time.monotonic_ns()
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
        metadata["recorded_probe_slots"] = sum(counts.values())
        metadata["probe_counts"] = counts
        write_metadata(metadata_path, metadata)
    return session_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/pilot.toml"))
    parser.add_argument("--target", required=True, type=local_ipv4, help="local Windows PC IPv4 address")
    parser.add_argument("--scenario", required=True, help="scenario from the pilot config")
    parser.add_argument("--source-interface", required=True, help="macOS interface to bind, such as en0")
    parser.add_argument("--source-link", help="override the configured MacBook link type")
    parser.add_argument("--target-link", help="override the configured target link type")
    parser.add_argument("--environment-notes", default="")
    parser.add_argument("--traffic-tool", help="name of the separately running traffic generator")
    parser.add_argument("--traffic-settings-json", help="JSON object describing traffic settings")
    parser.add_argument("--duration-seconds", type=int, help="override duration for a short smoke test")
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)
    if args.duration_seconds is not None and args.duration_seconds <= 0:
        parser.error("--duration-seconds must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        session_dir = collect(args, load_config(args.config))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"collection error: {exc}", file=sys.stderr)
        return 1
    metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    print(f"Session {metadata['run_status']} and saved to {session_dir}")
    return 0 if metadata["run_status"] == "completed" else 130


if __name__ == "__main__":
    raise SystemExit(main())
