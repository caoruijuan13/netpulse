#!/usr/bin/env bash
# Run from the newer Wi-Fi Mac. Start iperf3 -s on the older Ethernet Mac first.
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage:' \
    '  bash scripts/mac_mac_iperf3_trial.sh calibrate <SERVER_IP> <WIFI_IFACE>' \
    '  bash scripts/mac_mac_iperf3_trial.sh upload <SERVER_IP> <WIFI_IFACE> <CALIBRATION_SUMMARY_JSON>' \
    '  bash scripts/mac_mac_iperf3_trial.sh download <SERVER_IP> <WIFI_IFACE> <CALIBRATION_SUMMARY_JSON>' \
    '  bash scripts/mac_mac_iperf3_trial.sh burst <SERVER_IP> <WIFI_IFACE> <CALIBRATION_SUMMARY_JSON> [SEED]' \
    '' \
    'Pass the summary.json path printed by the calibration run.'
}

if [[ $# -eq 0 || ${1:-} == --help || ${1:-} == -h ]]; then
  usage
  exit 0
fi

mode=$1
if [[ $mode == calibrate ]]; then
  [[ $# -eq 3 ]] || { usage >&2; exit 2; }
elif [[ $mode == upload || $mode == download ]]; then
  [[ $# -eq 4 ]] || { usage >&2; exit 2; }
elif [[ $mode == burst ]]; then
  [[ $# -eq 4 || $# -eq 5 ]] || { usage >&2; exit 2; }
else
  usage >&2
  exit 2
fi

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
experiment_config=${NETPULSE_EXPERIMENT_CONFIG:-configs/mac-mac-iperf3-pilot-v1.toml}
slot_note=''
if [[ -n ${NETPULSE_SLOT_ID:-} ]]; then
  [[ $NETPULSE_SLOT_ID =~ ^D[1-4]-0[1-8]$ ]] || { echo 'Invalid formal slot ID' >&2; exit 2; }
  slot_note="; slot_id=$NETPULSE_SLOT_ID"
fi
command -v iperf3 >/dev/null || { echo 'iperf3 is required on the Wi-Fi Mac' >&2; exit 1; }
command -v caffeinate >/dev/null || { echo 'caffeinate is required on the Wi-Fi Mac' >&2; exit 1; }
server_ip=$2
wifi_iface=$3
wifi_ip=$(ipconfig getifaddr "$wifi_iface") || { echo "No IPv4 address on $wifi_iface" >&2; exit 1; }
route_iface=$(route -n get "$server_ip" | awk '/^[[:space:]]*interface:/ { print $2; exit }')
if [[ $route_iface != "$wifi_iface" ]]; then
  printf 'Route to %s uses %s, not %s. Fix the route before testing.\n' "$server_ip" "$route_iface" "$wifi_iface" >&2
  exit 1
fi
if [[ $mode != calibrate ]]; then
  calibration_summary=$4
  capacity_direction=$mode
  [[ $mode == burst ]] && capacity_direction=upload
  capacity_mbps=$(python3 scripts/summarize_iperf3_calibration.py --capacity "$capacity_direction" "$calibration_summary")
  calibration_run_id=$(basename "$(dirname "$calibration_summary")")
  if [[ $calibration_run_id != calibrate-* ]]; then
    echo 'Calibration summary must come from a calibrate-* run directory' >&2
    exit 1
  fi
fi
load_root=${NETPULSE_LOAD_ROOT:-data/load}
mkdir -p "$load_root"

if [[ $mode == calibrate ]]; then
  run_dir=$(mktemp -d "$load_root/calibrate-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
  printf 'Logs: %s\n' "$run_dir"
  for direction in upload download; do
    for trial in 1 2 3; do
      printf 'Calibration %s %d/3\n' "$direction" "$trial"
      if [[ $direction == download ]]; then
        iperf3 -c "$server_ip" -B "$wifi_ip" -P 1 -t 30 -O 5 -i 1 -J --get-server-output -R \
          > "$run_dir/$direction-$trial.json"
      else
        iperf3 -c "$server_ip" -B "$wifi_ip" -P 1 -t 30 -O 5 -i 1 -J --get-server-output \
          > "$run_dir/$direction-$trial.json"
      fi
    done
  done
  python3 scripts/summarize_iperf3_calibration.py "$run_dir" | tee "$run_dir/summary.json"
  printf 'Use %s/summary.json as the calibration argument for upload and download.\n' "$run_dir"
  exit 0
fi

rate_fraction=0.70
[[ $mode == burst ]] && rate_fraction=0.90
target_bps=$(python3 -c 'import math,sys; v=float(sys.argv[1]); f=float(sys.argv[2]); n=round(v * f * 1_000_000); assert math.isfinite(v) and n > 0; print(n)' "$capacity_mbps" "$rate_fraction")
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
  seed=${5:-42}
  if [[ ! $seed =~ ^[0-9]+$ ]]; then
    echo 'Burst seed must be a non-negative integer' >&2
    exit 2
  fi
  launch_log=$(mktemp "$load_root/burst-launch-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
  PYTHONPATH=src python3 -m netpulse.burst \
    --config "$experiment_config" \
    --target "$server_ip" --capacity-mbps "$capacity_mbps" --seed "$seed" \
    --output-root "$load_root" \
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
      printf 'Burst generator failed before starting; inspect %s\n' "$launch_log" >&2
      exit 1
    fi
    sleep 0.1
  done
  if [[ -z $load_run_id || ! -f $load_root/$load_run_id/run.json ]]; then
    printf 'Burst generator did not provide a run ID within 10 seconds; inspect %s\n' "$launch_log" >&2
    exit 1
  fi
  printf 'Burst load: %s/%s; launcher log: %s\n' "$load_root" "$load_run_id" "$launch_log"
  traffic_settings=$(printf '{"load_run_id":"%s","calibration_run_id":"%s","direction":"wifi_to_ethernet","parallel_streams":1,"capacity_mbps":%s,"target_rate_bps":%s,"seed":%s,"iperf_client_log":"%s/%s/iperf.log"}' \
    "$load_run_id" "$calibration_run_id" "$capacity_mbps" "$target_bps" "$seed" "$load_root" "$load_run_id")
  PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
    --config "$experiment_config" \
    --target "$server_ip" --scenario burst \
    --source-interface "$wifi_iface" --source-link wifi --target-link ethernet \
    --traffic-tool iperf3 --traffic-settings-json "$traffic_settings" \
    --environment-notes "Both MacBooks on power; VPN off; load_run_id=$load_run_id$slot_note"
  wait "$load_pid"
  load_pid=''
  wait "$wake_pid" || true
  wake_pid=''
  python3 scripts/check_burst_overlap.py "$load_root/$load_run_id" data/raw
  trap - EXIT INT TERM
  printf 'Completed burst; load log: %s/%s/iperf.log\n' "$load_root" "$load_run_id"
  exit 0
fi

run_dir=$(mktemp -d "$load_root/${mode}-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
run_id=${run_dir##*/}
printf 'Logs: %s\n' "$run_dir"
direction=wifi_to_ethernet
reverse=false
if [[ $mode == download ]]; then
  direction=ethernet_to_wifi
  reverse=true
fi
traffic_settings=$(printf '{"load_run_id":"%s","calibration_run_id":"%s","direction":"%s","reverse":%s,"parallel_streams":1,"capacity_mbps":%s,"target_rate_bps":%s,"iperf_duration_seconds":930,"iperf_client_log":"%s/iperf.log"}' \
  "$run_id" "$calibration_run_id" "$direction" "$reverse" "$capacity_mbps" "$target_bps" "$run_dir")

if [[ $mode == download ]]; then
  iperf3 -c "$server_ip" -B "$wifi_ip" -P 1 -t 930 -b "$target_bps" -i 1 \
    --get-server-output --logfile "$run_dir/iperf.log" -R &
else
  iperf3 -c "$server_ip" -B "$wifi_ip" -P 1 -t 930 -b "$target_bps" -i 1 \
    --get-server-output --logfile "$run_dir/iperf.log" &
fi
load_pid=$!
sleep 3
if ! kill -0 "$load_pid" 2>/dev/null; then
  wait "$load_pid" || true
  echo 'iperf3 load exited before the collector started; inspect the log' >&2
  exit 1
fi

PYTHONPATH=src caffeinate -i python3 -m netpulse.collect \
  --config "$experiment_config" \
  --target "$server_ip" --scenario "$mode" \
  --source-interface "$wifi_iface" --source-link wifi --target-link ethernet \
  --traffic-tool iperf3 --traffic-settings-json "$traffic_settings" \
  --environment-notes "Both MacBooks on power; VPN off; load_run_id=$run_id$slot_note"

wait "$load_pid"
load_pid=''
trap - EXIT INT TERM
printf 'Completed %s; load log: %s/iperf.log\n' "$mode" "$run_dir"
