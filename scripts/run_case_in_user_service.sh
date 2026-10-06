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
task40_campaign=0
for arg in "$@"; do
    case "$arg" in
        --task40-v10-campaign-window|--task40-v10-campaign-window=*)
            task40_campaign=1
            ;;
    esac
done
service_properties=(
    "--property=WorkingDirectory=$repo_root"
    "--property=StandardOutput=append:$log_dir/$unit.log"
    "--property=StandardError=append:$log_dir/$unit.log"
)
if (( task40_campaign )); then
    service_properties+=(
        "--property=MemoryMax=16G"
        "--property=MemorySwapMax=0"
    )
fi
systemd-run --user --expand-environment=no --unit="$unit" --service-type=exec \
    "${service_properties[@]}" \
    /usr/bin/bash -lc \
    'set -e; cd -- "$1"; shift; args=("$@"); use_v10=0; for arg in "${args[@]}"; do case "$arg" in --task40-v10-campaign-window|--task40-v10-campaign-window=*) use_v10=1 ;; esac; done; if (( use_v10 )); then source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit; else source scripts/activate_myfenics_wsl.sh; fi; exec python scripts/run_case.py "${args[@]}"' \
    myfenics-case "$repo_root" "$@"
printf 'Unit: %s.service\nLog: %s/%s.log\n' "$unit" "$log_dir" "$unit"
