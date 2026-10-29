#!/usr/bin/env bash
# Unattended first four slots of the frozen fixed-load v2 campaign.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo 'Usage: bash scripts/run_fixed_formal_v2_d1_01_04.sh <SERVER_IP> <WIFI_IFACE>' >&2
  exit 2
fi
server_ip=$1
wifi_iface=$2
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
export NETPULSE_FIXED_CONFIG="$repo_dir/configs/mac-mac-iperf3-fixed-v2.toml"
export NETPULSE_FIXED_RUN_TAG=formal-v2

# Existing v1 slots have a different experiment ID; only v2 attempts block a duplicate.
python3 - <<'PY'
import json
from pathlib import Path

for path in Path('data/raw').glob('*/session.json'):
    session = json.loads(path.read_text())
    if session.get('experiment_id') != 'mac-mac-iperf3-fixed-v2':
        continue
    notes = session.get('environment_notes') or ''
    if any(f'slot_id=D1-{number:02d}' in notes for number in range(1, 5)):
        raise SystemExit(f'Existing formal v2 D1-01..04 attempt: {path}; inspect before another batch')
PY

batch_dir=$(mktemp -d "data/load/fixed-formal-v2-d1-01-04-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
exec > >(tee "$batch_dir/batch.log") 2>&1
printf 'Batch log: %s/batch.log\n' "$batch_dir"
printf 'Experiment: mac-mac-iperf3-fixed-v2; targets: upload=360 download=300 burst=460 Mbps\n'

run_slot() {
  local slot_id=$1
  local mode=$2
  local seed=${3:-}
  export NETPULSE_SLOT_ID=$slot_id
  printf '\nStarting %s %s at %s\n' "$slot_id" "$mode" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ $mode == burst ]]; then
    bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh "$mode" "$server_ip" "$wifi_iface" "$seed"
  else
    bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh "$mode" "$server_ip" "$wifi_iface"
  fi
  printf 'Finished %s %s at %s\n' "$slot_id" "$mode" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

run_slot D1-01 idle
sleep 60
run_slot D1-02 upload
sleep 60
run_slot D1-03 download
sleep 60
run_slot D1-04 burst 101
printf '\nD1-01 through D1-04 completed at %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
