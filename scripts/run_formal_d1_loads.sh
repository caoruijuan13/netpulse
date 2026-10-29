#!/usr/bin/env bash
# One unattended, fail-fast D1-02 upload -> D1-03 download -> D1-04 burst batch.
# Start a persistent iperf3 -s on the Ethernet Mac before invoking this script.
set -euo pipefail

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo 'Usage: bash scripts/run_formal_d1_loads.sh <SERVER_IP> <WIFI_IFACE> <CALIBRATION_SUMMARY_JSON> [D1_IDLE_SESSION_ID]' >&2
  exit 2
fi

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
server_ip=$1
wifi_iface=$2
calibration_summary=$3
anchor_args=()
if [[ $# -eq 4 ]]; then
  anchor_args=(--anchor-session-id "$4")
fi

python3 scripts/check_formal_d1_batch.py preflight "$calibration_summary" "${anchor_args[@]}"
batch_dir=$(mktemp -d "data/load/formal-d1-batch-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
printf 'Batch log: %s/batch.log\n' "$batch_dir"

wake_pid=''
cleanup() {
  if [[ -n $wake_pid ]] && kill -0 "$wake_pid" 2>/dev/null; then
    kill "$wake_pid" 2>/dev/null || true
    wait "$wake_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM
caffeinate -i -w "$$" &
wake_pid=$!

run_slot() {
  local slot_id=$1
  local mode=$2
  shift 2
  printf '\n%s Starting %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$slot_id" "$mode" | tee -a "$batch_dir/batch.log"
  bash scripts/mac_mac_iperf3_formal.sh "$slot_id" "$mode" "$server_ip" "$wifi_iface" "$calibration_summary" "$@" \
    2>&1 | tee -a "$batch_dir/batch.log"
  python3 scripts/check_formal_d1_batch.py verify "$slot_id" "${anchor_args[@]}" 2>&1 | tee -a "$batch_dir/batch.log"
  printf '%s Completed and checked %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$slot_id" | tee -a "$batch_dir/batch.log"
}

run_slot D1-02 upload
printf 'Cooling down for 60 seconds before download\n' | tee -a "$batch_dir/batch.log"
sleep 60
run_slot D1-03 download
printf 'Cooling down for 60 seconds before burst\n' | tee -a "$batch_dir/batch.log"
sleep 60
run_slot D1-04 burst 101
printf '\nD1-02 through D1-04 completed; inspect %s/batch.log and the old Mac server log.\n' "$batch_dir" | tee -a "$batch_dir/batch.log"
