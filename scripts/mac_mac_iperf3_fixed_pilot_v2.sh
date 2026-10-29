#!/usr/bin/env bash
# Draft fixed-sender-target trial. Do not use this as the frozen v1 campaign runner.
set -euo pipefail

usage() {
  echo 'Usage: bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh <idle|upload|download|burst> <SERVER_IP> <WIFI_IFACE> [BURST_SEED]' >&2
}

[[ $# -ge 3 && $# -le 4 ]] || { usage; exit 2; }
mode=$1
server_ip=$2
wifi_iface=$3
if [[ $mode == burst ]]; then
  [[ $# -eq 4 && $4 =~ ^[0-9]+$ ]] || { usage; exit 2; }
  seed=$4
else
  [[ $# -eq 3 && ( $mode == idle || $mode == upload || $mode == download ) ]] || { usage; exit 2; }
fi

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
formal_slot=${NETPULSE_SLOT_ID:-}
if [[ -n $formal_slot ]]; then
  python3 scripts/check_formal_slot.py "$formal_slot" "$mode" "${seed:-}"
fi
config=${NETPULSE_FIXED_CONFIG:-"$repo_dir/configs/mac-mac-iperf3-fixed-pilot-v2.toml"}
run_tag=${NETPULSE_FIXED_RUN_TAG:-v2}
[[ -f $config && $run_tag =~ ^[a-zA-Z0-9-]+$ ]] || {
  echo 'Fixed-pilot config is missing or run tag is invalid' >&2
  exit 2
}
load_root=${NETPULSE_LOAD_ROOT:-data/load}
raw_root=${NETPULSE_RAW_ROOT:-data/raw}
mkdir -p "$load_root" "$raw_root"
slot_note=''
if [[ -n $formal_slot ]]; then
  slot_note="; slot_id=$formal_slot"
fi

wifi_ip=$(ipconfig getifaddr "$wifi_iface") || { echo "No IPv4 address on $wifi_iface" >&2; exit 1; }
route_iface=$(route -n get "$server_ip" | awk '/^[[:space:]]*interface:/ { print $2; exit }')
[[ $route_iface == "$wifi_iface" ]] || {
  printf 'Route to %s uses %s, not %s. Fix the route before testing.\n' "$server_ip" "$route_iface" "$wifi_iface" >&2
  exit 1
}

collect_args=(
  --config "$config" --target "$server_ip" --scenario "$mode"
  --source-interface "$wifi_iface" --source-link wifi --target-link ethernet
  --output-root "$raw_root"
  --environment-notes "Both MacBooks on power; VPN off; fixed-rate run ($run_tag)$slot_note"
)
if [[ $mode == idle ]]; then
  exec env PYTHONPATH=src caffeinate -i python3 -m netpulse.collect "${collect_args[@]}"
fi

command -v iperf3 >/dev/null || { echo 'iperf3 is required on the Wi-Fi Mac' >&2; exit 1; }
command -v caffeinate >/dev/null || { echo 'caffeinate is required on the Wi-Fi Mac' >&2; exit 1; }
rate_bps=$(python3 -c '
import sys, tomllib
with open(sys.argv[1], "rb") as stream:
    load = tomllib.load(stream)["load"]
rate = load[sys.argv[2] + "_target_bps"]
if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
    raise SystemExit("fixed target rate must be a positive integer")
print(rate)
' "$config" "$mode")

load_pid=''
wake_pid=''
cleanup() {
  if [[ -n $load_pid ]] && kill -0 "$load_pid" 2>/dev/null; then
    kill "$load_pid" 2>/dev/null || true
    wait "$load_pid" 2>/dev/null || true
  fi
  if [[ -n $wake_pid ]] && kill -0 "$wake_pid" 2>/dev/null; then
    kill "$wake_pid" 2>/dev/null || true
    wait "$wake_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

if [[ $mode == burst ]]; then
  launch_log=$(mktemp "$load_root/burst-${run_tag}-launch-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
  PYTHONPATH=src python3 -m netpulse.burst \
    --config "$config" --target "$server_ip" --seed "$seed" --output-root "$load_root" \
    > "$launch_log" 2>&1 &
  load_pid=$!
  caffeinate -i -w "$load_pid" &
  wake_pid=$!
  load_run_id=''
  for ((attempt=0; attempt<100; attempt++)); do
    load_run_id=$(sed -n 's/^Burst run \(burst-[^;]*\); logs:.*/\1/p' "$launch_log")
    [[ -n $load_run_id ]] && break
    if ! kill -0 "$load_pid" 2>/dev/null; then
      wait "$load_pid" || true
      printf 'Burst generator failed; inspect %s\n' "$launch_log" >&2
      exit 1
    fi
    sleep 0.1
  done
  [[ -n $load_run_id && -f $load_root/$load_run_id/run.json ]] || {
    printf 'Burst generator did not provide a run ID; inspect %s\n' "$launch_log" >&2
    exit 1
  }
  printf 'Burst load: %s/%s; launcher log: %s\n' "$load_root" "$load_run_id" "$launch_log"
  traffic_settings=$(python3 -c '
import json, sys
print(json.dumps({"load_run_id": sys.argv[1], "rate_policy": "fixed_sender_target",
                  "direction": "wifi_to_ethernet", "parallel_streams": 1,
                  "target_rate_bps": int(sys.argv[2]), "seed": int(sys.argv[3]),
                  "iperf_client_log": sys.argv[4]}))
' "$load_run_id" "$rate_bps" "$seed" "$load_root/$load_run_id/iperf.log")
  PYTHONPATH=src caffeinate -i python3 -m netpulse.collect "${collect_args[@]}" \
    --traffic-tool iperf3 --traffic-settings-json "$traffic_settings"
  wait "$load_pid"
  load_pid=''
  wait "$wake_pid" || true
  wake_pid=''
  python3 scripts/check_burst_overlap.py "$load_root/$load_run_id" "$raw_root"
  trap - EXIT INT TERM
  printf 'Completed burst; load log: %s/%s/iperf.log\n' "$load_root" "$load_run_id"
  exit 0
fi

run_dir=$(mktemp -d "$load_root/${mode}-${run_tag}-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
run_id=${run_dir##*/}
printf 'Logs: %s\n' "$run_dir"
direction=wifi_to_ethernet
reverse=false
iperf_args=(-c "$server_ip" -B "$wifi_ip" -P 1 -t 930 -b "$rate_bps" -i 1 \
  --get-server-output --logfile "$run_dir/iperf.log")
if [[ $mode == download ]]; then
  direction=ethernet_to_wifi
  reverse=true
  iperf_args+=(-R)
fi
traffic_settings=$(python3 -c '
import json, sys
print(json.dumps({"load_run_id": sys.argv[1], "rate_policy": "fixed_sender_target",
                  "direction": sys.argv[2], "reverse": sys.argv[3] == "true",
                  "parallel_streams": 1, "target_rate_bps": int(sys.argv[4]),
                  "iperf_duration_seconds": 930, "iperf_client_log": sys.argv[5]}))
' "$run_id" "$direction" "$reverse" "$rate_bps" "$run_dir/iperf.log")
iperf3 "${iperf_args[@]}" &
load_pid=$!
caffeinate -i -w "$load_pid" &
wake_pid=$!
sleep 3
if ! kill -0 "$load_pid" 2>/dev/null; then
  wait "$load_pid" || true
  echo 'iperf3 exited before the collector started; inspect the load log' >&2
  exit 1
fi
PYTHONPATH=src caffeinate -i python3 -m netpulse.collect "${collect_args[@]}" \
  --traffic-tool iperf3 --traffic-settings-json "$traffic_settings"
wait "$load_pid"
load_pid=''
wait "$wake_pid" || true
wake_pid=''
trap - EXIT INT TERM
printf 'Completed %s; load log: %s/iperf.log\n' "$mode" "$run_dir"
