#!/usr/bin/env bash
# Start one case immediately, with its existing watchdog owned by user systemd.
# No timer is created; closing a Codex task cannot remove the case's parent.
set -euo pipefail
if (( $# == 0 )); then
    echo "Usage: bash scripts/run_case_in_user_service.sh CASE.dat [run_case options]" >&2
    exit 2
fi
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
unit="myfenics-case-$(date -u +%Y%m%dT%H%M%S)-$$"
log_dir="$repo_root/benchmarks/artifacts/user_services"
mkdir -p "$log_dir"
systemd-run --user --unit="$unit" --service-type=exec \
    --property="WorkingDirectory=$repo_root" \
    --property="StandardOutput=append:$log_dir/$unit.log" \
    --property="StandardError=append:$log_dir/$unit.log" \
    /usr/bin/bash -lc \
    'set -e; cd -- "$1"; shift; source scripts/activate_myfenics_wsl.sh; exec python scripts/run_case.py "$@"' \
    myfenics-case "$repo_root" "$@"
printf 'Unit: %s.service\nLog: %s/%s.log\n' "$unit" "$log_dir" "$unit"
