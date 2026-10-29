#!/usr/bin/env bash
# First four frozen fixed-load v2 D2 slots; fail fast and preserve all attempts.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo 'Usage: bash scripts/run_fixed_formal_v2_d2_01_04.sh <SERVER_IP> <WIFI_IFACE>' >&2
  exit 2
fi
server_ip=$1
wifi_iface=$2
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
export NETPULSE_FIXED_CONFIG="$repo_dir/configs/mac-mac-iperf3-fixed-v2.toml"
export NETPULSE_FIXED_RUN_TAG=formal-v2-d2a

python3 - <<'PY'
import json
from pathlib import Path

selection = json.loads(Path('data/load/fixed-formal-v2-d1-05-08-20261024T050624Z-XcWQ7h/selection.json').read_text())
if selection.get('experiment_id') != 'mac-mac-iperf3-fixed-v2' or selection.get('status') != 'accepted_after_audit':
    raise SystemExit('D1 selection is not accepted')
if set(selection['selected_sessions']) != {f'D1-{number:02d}' for number in range(1, 9)}:
    raise SystemExit('D1 selection is incomplete')
for path in Path('data/raw').glob('*/session.json'):
    session = json.loads(path.read_text())
    if session.get('experiment_id') != 'mac-mac-iperf3-fixed-v2':
        continue
    if session.get('run_status') == 'running':
        raise SystemExit(f'Another formal v2 session is running: {path}')
    notes = session.get('environment_notes') or ''
    if any(f'slot_id=D2-{number:02d}' in notes for number in range(1, 5)):
        raise SystemExit(f'Existing formal v2 D2-01..04 attempt: {path}; inspect before rerunning')
PY

batch_dir=$(mktemp -d "data/load/fixed-formal-v2-d2-01-04-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
exec > >(tee "$batch_dir/batch.log") 2>&1
printf 'Batch log: %s/batch.log\n' "$batch_dir"
printf 'Experiment: mac-mac-iperf3-fixed-v2; slots D2-01..04; targets upload=360 burst=460 download=300 Mbps\n'

run_slot() {
  local slot_id=$1
  local mode=$2
  local seed=${3:-}
  local slot_log="$batch_dir/$slot_id.log"
  local session_path
  export NETPULSE_SLOT_ID=$slot_id
  printf '\nStarting %s %s at %s\n' "$slot_id" "$mode" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ $mode == burst ]]; then
    bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh "$mode" "$server_ip" "$wifi_iface" "$seed" 2>&1 | tee "$slot_log"
  else
    bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh "$mode" "$server_ip" "$wifi_iface" 2>&1 | tee "$slot_log"
  fi
  session_path=$(sed -n 's@^Session completed and saved to \(data/raw/[^ ]*\)$@\1@p' "$slot_log" | tail -1)
  [[ -n $session_path ]] || { echo "$slot_id has no completed session path" >&2; exit 1; }
  python3 scripts/check_fixed_formal_v2_slot.py "$session_path" "$slot_id" "$mode"
  printf 'Finished and checked %s %s: %s at %s\n' "$slot_id" "$mode" "$session_path" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

run_slot D2-01 upload
sleep 60
run_slot D2-02 burst 103
sleep 60
run_slot D2-03 idle
sleep 60
run_slot D2-04 download
printf '\nD2-01 through D2-04 completed at %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
