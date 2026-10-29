#!/usr/bin/env bash
# One unattended, sequential high-load contrast trial. Stop on the first failure.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo 'Usage: bash scripts/run_fixed_high_pilot_v2.sh <SERVER_IP> <WIFI_IFACE>' >&2
  exit 2
fi
server_ip=$1
wifi_iface=$2
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

batch_dir=$(mktemp -d "data/load/fixed-high-v2-batch-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
exec > >(tee "$batch_dir/batch.log") 2>&1
printf 'Batch log: %s/batch.log\n' "$batch_dir"
printf 'Calibration reference: data/load/calibrate-20261023T093136Z-xltSS7/summary.json\n'
printf 'Fixed targets: upload=360 Mbps download=380 Mbps burst=460 Mbps; burst seed=42\n'

export NETPULSE_FIXED_CONFIG="$repo_dir/configs/mac-mac-iperf3-fixed-high-pilot-v2.toml"
export NETPULSE_FIXED_RUN_TAG=high-v2

for mode in idle upload download burst; do
  printf '\nStarting %s at %s\n' "$mode" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [[ $mode == burst ]]; then
    bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh "$mode" "$server_ip" "$wifi_iface" 42
  else
    bash scripts/mac_mac_iperf3_fixed_pilot_v2.sh "$mode" "$server_ip" "$wifi_iface"
  fi
  printf 'Finished %s at %s\n' "$mode" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
printf '\nHigh-load contrast batch completed at %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
