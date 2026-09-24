# M0 pilot plan

Status: **exploratory pilot completed; M0-v1 frozen**. Idle, upload, download, and burst sessions have been collected with the MacBook on Ethernet and the Windows PC on Wi-Fi. See [pilot-observations.md](pilot-observations.md) for quality findings. This page retains pilot instructions and gives the frozen procedure for later controlled collection. Pilot data are not a model benchmark.

## Before each session

1. Connect the MacBook over Ethernet and the Windows PC over Wi-Fi to the same local router/AP. Keep both on power and awake. Confirm the MacBook can reach the PC's chosen address and that ICMP Echo replies are permitted.
2. Record the actual topology, OS/interface, probe target, traffic tool/settings, and any VPN or background traffic in `session.json`. Use a new `session_id` for each run.
3. Confirm that the collector will write one record for every one-second slot, including timeouts or failures. Historical pilot sessions used [pilot.toml](../configs/pilot.toml); use frozen [m0-v1.toml](../configs/m0-v1.toml) for new controlled sessions.

On the MacBook, run from the repository root with Python 3.11 or newer. Replace the example address and interface with the PC's local IPv4 address and the MacBook's actual Ethernet interface. Pass the source and target links explicitly when verifying the physical setup:

```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config configs/m0-v1.toml \
  --target <PC_IP> \
  --scenario burst \
  --source-interface en6 \
  --source-link ethernet \
  --target-link wifi \
  --traffic-tool iperf2 \
  --traffic-settings-json '{"load_run_id":"<BURST_RUN_ID>","direction":"mac_to_pc"}' \
  --environment-notes "MacBook on power; VPN off; fixed location"
```

The command above is a burst example: replace the PC address, Mac interface, and burst run ID for each new session. For `idle`, use `--scenario idle` and omit the two traffic options. For `upload` or `download`, change the scenario and supply the corresponding traffic settings below. These values reflect recorded pilot targets, not verified achieved rates; check them against the generator command and its output before reuse:

| Scenario | `--traffic-settings-json` example |
| --- | --- |
| `upload` (Mac → PC) | `'{"direction":"mac_to_pc","capacity_mbps":310,"rate_fraction":0.70,"target_rate_bps":217000000}'` |
| `download` (PC → Mac) | `'{"direction":"pc_to_mac","capacity_mbps":310,"rate_fraction":0.70,"target_rate_bps":217000000,"parallel_streams":4,"per_flow_target_bps":54250000}'` |
| `burst` (Mac → PC) | `'{"load_run_id":"<BURST_RUN_ID>","direction":"mac_to_pc"}'` |

These numbers describe inspected pilot runs, not permanent rates for future sessions. The corrected download pilot's Mac receiver log confirms 217 Mbit/s aggregate; its Windows client output file has not been retained in this repository.

The collector binds `ping` to `--source-interface` and writes an ignored `data/raw/<scenario>-<UTC_TIMESTAMP>-<SUFFIX>/` directory. Its `session.json` and `probes.jsonl` filenames are fixed; their contents carry the same scenario-prefixed `session_id`. A short local smoke test can use `--target 127.0.0.1 --source-interface lo0 --source-link loopback --target-link loopback --duration-seconds 3`; those loopback results are not pilot data. The collector records load settings supplied through `--traffic-tool` and `--traffic-settings-json`, but does not generate load.

The collector caps each `ping` process wait before the next scheduled probe slot, with a small margin for cleanup and recording. If the process still does not finish, retain `send_error=ping_process_timeout`; do not relabel it as ICMP packet loss. A genuinely late start remains `missed_slot`. Under an unusually late start, the process deadline may occur before the configured ICMP reply timeout; treat that outcome as a collector/process error, not a network timeout.

### Diagnosing `ping_process_timeout`

Use a separate diagnostic run, not a formal M0 session, to see whether macOS `ping` exits after the collector's approximately 900 ms process budget. Keep the same ICMP `-W 800` setting but allow the process three seconds to finish. With no iperf load, run:

```sh
PYTHONPATH=src caffeinate -i python3 -m netpulse.diagnose_ping \
  --config configs/m0-v1.toml --target <PC_IP> --source-interface <MAC_ETHERNET_IFACE> \
  --scenario idle --samples 120
```

For comparison, start the normal upload iperf load, then repeat with `--scenario upload --load-run-id <UPLOAD_RUN_ID>` instead of `--scenario idle`. Do not run the normal collector at the same time; these extra probes would alter its experiment. Each diagnostic run writes ignored `data/diagnostics/pingdiag-<scenario>-<id>/run.json` and `samples.jsonl`. The latter records process elapsed time, exit code, and complete or partial stdout/stderr. A completed `timeout` means `ping` reported no timely reply; `process_timeout` means it still had not exited after three seconds. Neither result alone proves where a packet was lost. The diagnostic loop never overlaps ping processes, so starts may be more than one second apart when a process runs longer.

## Creating the four load scenarios

Use **iperf2** on both machines. The MacBook has been checked with iperf2 2.2.0; confirm that the Windows PC has a compatible iperf2 executable before testing. iperf2 has a native Windows build, while iperf3 does not officially support Windows. Do not mix iperf2 and iperf3 client/server processes. Limit any firewall allowance for ICMP Echo and iperf2's TCP port to the private experiment network. Save both ends' tool version and full output with the session record. See the [iperf2 manual](https://iperf2.sourceforge.io/iperf2-user-manual.html) and [iperf3 FAQ](https://software.es.net/iperf/faq.html).

Rate values are **direction- and flow-profile-specific**. For each sustained direction, run three separate 30-second uncapped TCP trials (`-b 0`) on the same path: one flow for Mac-to-PC upload, four flows for PC-to-Mac download. From each trial take the median receiver-side aggregate throughput over seconds 5–30; the median of those three values is that profile's capacity. Record both ends' full logs and tool versions. Investigate PC Wi-Fi signal/position, Mac Ethernet negotiation, and endpoint CPU saturation before interpreting a single-flow result as the wireless-link limit. M0-v1 starts sustained upload/download at **70% of matching-profile capacity** and bursts at **90% of one-flow Mac-to-PC capacity**. The achieved receiver rate, not `-b` alone, determines whether the requested load was delivered.

Commands below use `iperf` as a placeholder for the local iperf2 executable. Use `-t 30 -b 0` for calibration. For the 15-minute session, use `-t 930` to cover collector startup and its full 900 seconds. Start the load, then start the collector promptly in another terminal; record actual load start/end UTC times and confirm that traffic covers all 900 collector seconds. Set the collector scenario and traffic settings to the actual client command, flow count, aggregate target, per-flow target, and load run ID. Use a fresh output file for every load run; on Windows, pass an absolute path to `-o` and keep the resulting file with the session evidence.

| Scenario | Windows PC | MacBook |
| --- | --- | --- |
| `idle` | No load generator | Collector only |
| `upload` (Mac → PC) | `iperf -s -i 1 -o <PC_RECEIVER_LOG>` | `iperf -c <PC_IP> -t 930 -b <UPLOAD_AGGREGATE_BPS> -i 1` |
| `download` (PC → Mac) | `iperf -c <MAC_IP> -t 930 -b <DOWNLOAD_AGGREGATE_BPS_DIV_4> -P 4 -i 1 -o <PC_CLIENT_LOG>` | `iperf -s -i 1`, save the Mac receiver log, plus collector in another terminal |

For the inspected 310 Mbit/s four-flow PC-to-Mac capacity, a 70% aggregate target is 217 Mbit/s, so the pilot client used `-b 54250000 -P 4`. Its receiver `[SUM]` was 217 Mbit/s. `-b 217M -P 4` instead requested up to 217 Mbit/s **per flow** and produced 309 Mbit/s in the pilot. Recalibrate for new sessions rather than reusing either historical rate automatically. Mac-to-PC burst collection also requires a saved PC receiver log; the Mac generator log alone does not prove delivery.

For `burst`, run `iperf -s -i 1 -o <PC_RECEIVER_LOG>` on the PC, then use the MacBook burst generator below. The Windows log path must be absolute and its directory must already exist. It sends Mac → PC traffic only, using randomized 10–20 second on-periods and 20–40 second gaps by default. Give each session a different seed and retain its planned and actual pulse logs. Never supply the future pulse schedule to the prediction model.

```sh
PYTHONPATH=src python3 -m netpulse.burst \
  --config configs/m0-v1.toml \
  --target <PC_IP> \
  --capacity-mbps <MEASURED_MAC_TO_PC_CAPACITY> \
  --seed 20260924
```

The generator prints a `burst-<UTC_TIMESTAMP>-<SUFFIX>` run ID (use this as `load_run_id`) and saves `data/load/<run_id>/run.json`, `events.jsonl`, and one `iperf.log` for the entire run. The log has start/end markers for each pulse, while `events.jsonl` retains structured timing and outcomes. Start the `burst` collector promptly in another terminal and include the run ID in its `--traffic-settings-json`, for example `'{"load_run_id":"<run_id>","direction":"mac_to_pc"}'`. The initial 30-second generator delay allows collector startup; the generator runs for 930 seconds. If startup takes longer, record the offset and repeat the session rather than silently treating it as aligned. `--duration-seconds` and on/off overrides are available for a short local smoke test. Earlier pilot run IDs and their `pulse-*.log` files remain unchanged.

The burst generator chooses iperf2's TCP write-buffer size from the target rate and records the value in `run.json`. This avoids iperf2 rejecting low-rate pilot or smoke-test runs because its default buffer is too large.

## Session procedure

The exploratory pilot collected one 15-minute session per scenario. Formal sessions use the same 15-minute duration, with the first minute treated as warm-up; M1 sets the number of independent sessions per scenario before assigning splits. Keep each session's load mode constant; for `burst`, record the pulse schedule and seed in metadata, but never provide the future schedule to the model. Leave enough time between sessions for the load to stop and the environment to settle. Record actual behavior and deviations rather than silently relabeling a session.

## Quality review before formal collection

For every session, report:

- Expected, written, successful, timed-out, send-error, and missed-slot counts; duplicate or out-of-order sequence numbers.
- Median and P95 absolute scheduling offset (`started_monotonic_ns - scheduled_monotonic_ns`) and actual inter-probe intervals.
- Successful RTT distribution (median, P95, maximum), separate `timeout` and `ping_process_timeout` rates, accepted-window share, and fully observed-window share under the M0-v1 window rule.
- Whether the traffic tool achieved the intended load; any CPU saturation or endpoint instability observed.
- Differences across scenarios and notable changes within a session.

Investigate any missing records, clock/scheduling problems, or large numbers of invalid windows before training. If the PC does not answer ICMP Echo, a different probe method requires a new protocol version; do not mix methods in one evaluation dataset. For controlled sustained-load sessions, require the receiver-side mean during collector overlap within 15% of the declared target and no complete 60-second overlap block below 75% of target. Preserve a failed or underloaded session as raw diagnostic data, but exclude it from controlled scenario comparisons. Never change load settings mid-session to force a pass. Assign formal sessions to train/validation/test by session ID before deriving windows.

Compare UTC elapsed time with the monotonic probe schedule. If adjacent started probes differ by more than two seconds between their UTC and monotonic intervals, mark a discontinuity, exclude every derived window crossing it, and investigate. A confirmed sleep invalidates a controlled formal session; keep the raw records unchanged.
