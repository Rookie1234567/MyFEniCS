#!/usr/bin/env bash
# Run saved-field comparison and its independent checker under the existing
# user-service parent; the Python entrypoint starts the established subreaper.
set -euo pipefail

if (( $# == 0 )); then
    echo "Usage: bash scripts/run_task40_v5_postprocess_in_user_service.sh CASE_ROOT [--implementation-bug-evidence PATH]" >&2
    exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == "service" ]]; then
    shift
    cd -- "$repo_root"
    source scripts/activate_myfenics_wsl.sh
    exec python -u -m benchmarks.run_task40_v5_postprocess_service "$@"
fi

case_root="$(realpath -e -- "$1")"
shift
unit="myfenics-task40-v5-postprocess-$(date -u +%Y%m%dT%H%M%S)-$$"
log_dir="$repo_root/benchmarks/artifacts/user_services"
mkdir -p "$log_dir"
systemd-run --user --unit="$unit" --service-type=exec \
    --property="WorkingDirectory=$repo_root" \
    --property="StandardOutput=append:$log_dir/$unit.log" \
    --property="StandardError=append:$log_dir/$unit.log" \
    /usr/bin/bash -lc \
    'set -e; cd -- "$1"; shift; source scripts/activate_myfenics_wsl.sh; exec python -u -m benchmarks.run_task40_v5_postprocess_service "$@"' \
    task40-v5-postprocess "$repo_root" --case-root "$case_root" "$@"
printf 'Unit: %s.service\nLog: %s/%s.log\n' "$unit" "$log_dir" "$unit"
