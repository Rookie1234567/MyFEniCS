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
args=("$@")
v29_contract=""
v29_selector=""
v29_contract_count=0
v29_selector_count=0
for ((index = 0; index < ${#args[@]}; index++)); do
    arg="${args[index]}"
    case "$arg" in
        --task40-v29-execution-contract)
            ((index + 1 < ${#args[@]})) || { echo "V29 contract flag needs a path" >&2; exit 2; }
            v29_contract="${args[index + 1]}"
            ((v29_contract_count += 1))
            ((index += 1))
            ;;
        --task40-v29-execution-contract=*)
            v29_contract="${arg#*=}"
            ((v29_contract_count += 1))
            ;;
        --task40-v29-factor-only-selector)
            ((index + 1 < ${#args[@]})) || { echo "V29 selector flag needs a path" >&2; exit 2; }
            v29_selector="${args[index + 1]}"
            ((v29_selector_count += 1))
            ((index += 1))
            ;;
        --task40-v29-factor-only-selector=*)
            v29_selector="${arg#*=}"
            ((v29_selector_count += 1))
            ;;
    esac
done
v29_campaign=0
if (( v29_contract_count != 0 || v29_selector_count != 0 )); then
    if (( v29_contract_count != 1 || v29_selector_count != 1 )); then
        echo "V29 requires exactly one execution contract and one factor-only selector" >&2
        exit 2
    fi
    [[ "$v29_contract" == /* ]] || v29_contract="$repo_root/$v29_contract"
    [[ "$v29_selector" == /* ]] || v29_selector="$repo_root/$v29_selector"
    if ! v29_values_text="$(cd -- "$repo_root" && python3 -m src.runners.task40_v29_contract \
        --launcher-values --contract "$v29_contract" --selector "$v29_selector")"; then
        exit 2
    fi
    mapfile -t v29_values <<< "$v29_values_text"
    if (( ${#v29_values[@]} != 7 )) || [[ "${v29_values[0]}" != "$repo_root" ]]; then
        echo "V29 contract validator returned an incomplete or foreign-root binding" >&2
        exit 2
    fi
    [[ "${v29_values[4]}" =~ ^[1-9][0-9]*$ ]] || {
        echo "V29 approved task memory cap is invalid" >&2
        exit 2
    }
    v29_campaign=1
fi
task40_campaign=0
for arg in "${args[@]}"; do
    case "$arg" in
        --task40-v10-campaign-window|--task40-v10-campaign-window=*)
            task40_campaign=1
            ;;
    esac
done
if (( v29_campaign )); then
    task40_campaign=1
fi
service_properties=(
    "--property=WorkingDirectory=$repo_root"
    "--property=StandardOutput=append:$log_dir/$unit.log"
    "--property=StandardError=append:$log_dir/$unit.log"
)
if (( v29_campaign )); then
    service_properties+=(
        "--property=MemoryMax=${v29_values[4]}"
        "--property=MemorySwapMax=0"
    )
elif (( task40_campaign )); then
    service_properties+=(
        "--property=MemoryMax=16G"
        "--property=MemorySwapMax=0"
    )
fi
systemd-run --user --expand-environment=no --unit="$unit" --service-type=exec \
    "${service_properties[@]}" \
    /usr/bin/bash -lc \
    'set -euo pipefail; cd -- "$1"; repo_root=$1; unit=$2; shift 2; args=("$@"); use_v10=0; use_v29=0; v29_contract=""; v29_selector=""; for ((i=0; i<${#args[@]}; i++)); do arg="${args[i]}"; case "$arg" in --task40-v10-campaign-window|--task40-v10-campaign-window=*) use_v10=1 ;; --task40-v29-execution-contract) v29_contract="${args[i+1]}"; ((i+=1)); use_v29=1 ;; --task40-v29-execution-contract=*) v29_contract="${arg#*=}"; use_v29=1 ;; --task40-v29-factor-only-selector) v29_selector="${args[i+1]}"; ((i+=1)); use_v29=1 ;; --task40-v29-factor-only-selector=*) v29_selector="${arg#*=}"; use_v29=1 ;; esac; done; if (( use_v29 )); then [[ "$v29_contract" == /* ]] || v29_contract="$repo_root/$v29_contract"; [[ "$v29_selector" == /* ]] || v29_selector="$repo_root/$v29_selector"; v29_values_text="$(python3 -m src.runners.task40_v29_contract --launcher-values --contract "$v29_contract" --selector "$v29_selector")"; mapfile -t v29_values <<< "$v29_values_text"; (( ${#v29_values[@]} == 7 )) && [[ "${v29_values[0]}" == "$repo_root" ]]; unset _MYFENICS_WSL_QUALIFIED_ACTIVATION; source scripts/task40_fresh_c1/activate_native_complex.sh "${v29_values[1]}" "${v29_values[2]}" "${v29_values[3]}" native_linux; export TASK40_V29_STRICT_FACTOR_ONLY=1; exec "${v29_values[1]}/bin/python" scripts/task40_v20_service_workflow.py run-service --unit "$unit" --runtime-prefix "${v29_values[1]}" --abi-receipt "${v29_values[2]}" --jit-cache "${v29_values[3]}" -- "${args[@]}"; fi; case "${args[0]}" in *nonseparable_e2_p6_reference_v20.dat|*target_original_ny8_resource_pilot_v20.dat|*target_original_ny8_operator_probe_v22.dat) exec benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix/bin/python -S scripts/task40_v20_service_workflow.py run-service --unit "$unit" --runtime-prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix --abi-receipt benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json --jit-cache benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit -- "${args[@]}" ;; esac; if (( use_v10 )); then source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit; else source scripts/activate_myfenics_wsl.sh; fi; exec python scripts/run_case.py "${args[@]}"' \
    myfenics-case "$repo_root" "$unit" "$@"
printf 'Unit: %s.service\nLog: %s/%s.log\n' "$unit" "$log_dir" "$unit"
