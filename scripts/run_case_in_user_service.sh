#!/usr/bin/env bash
# Start one case immediately, with its existing watchdog owned by user systemd.
# No timer is created; closing a Codex task cannot remove the case's parent.
set -euo pipefail
if (( $# == 0 )); then
    echo "Usage: bash scripts/run_case_in_user_service.sh CASE.dat [run_case options]" >&2
    exit 2
fi
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
log_dir="$repo_root/benchmarks/artifacts/user_services"
mkdir -p "$log_dir"
service_unit_override=""
raw_args=("$@")
args=()
for ((index = 0; index < ${#raw_args[@]}; index++)); do
    arg="${raw_args[index]}"
    case "$arg" in
        --service-unit)
            ((index + 1 < ${#raw_args[@]})) || { echo "--service-unit needs a value" >&2; exit 2; }
            [[ -z "$service_unit_override" ]] || { echo "--service-unit may appear only once" >&2; exit 2; }
            service_unit_override="${raw_args[index + 1]}"
            ((index += 1))
            ;;
        --service-unit=*)
            [[ -z "$service_unit_override" ]] || { echo "--service-unit may appear only once" >&2; exit 2; }
            service_unit_override="${arg#*=}"
            ;;
        *)
            args+=("$arg")
            ;;
    esac
done
if (( ${#args[@]} == 0 )); then
    echo "Usage: bash scripts/run_case_in_user_service.sh CASE.dat [run_case options]" >&2
    exit 2
fi
if [[ -n "$service_unit_override" && ! "$service_unit_override" =~ ^[A-Za-z0-9_.@:-]+$ ]]; then
    echo "--service-unit must be a valid systemd unit name" >&2
    exit 2
fi
unit="${service_unit_override:-myfenics-case-$(date -u +%Y%m%dT%H%M%S)-$$}"
v29_contract=""
v29_selector=""
v29_contract_count=0
v29_selector_count=0
v30_contract=""
v30_contract_count=0
v31_contract=""
v31_contract_count=0
task41_contract=""
task41_contract_count=0
task41_saved_output_continuation=0
task41_saved_output_checker_only=0
task41_saved_b0_evidence_audit=0
task41_saved_b0_v9_star_screen=0
task41_saved_b0_v9_failed_terminal_audit=0
task41_saved_b0_y_g_comparison=0
task41_saved_b0_v14_candidate=0
task41_saved_b0_v16_analysis=0
task41_v17_selected_two_cell=0
task41_v17_selected_two_cell_count=0
task41_v18_saved_jz=0
task41_v18_saved_jz_count=0
task41_v19_native_rank1=0
task41_v19_native_rank1_count=0
task41_v19_checker_only=0
task41_v19_checker_only_count=0
task41_v19_receipt_sha_count=0
task41_v19_receipt_sha=""
task41_v19_receipt_path_count=0
task41_v19_receipt_path=""
task41_v15_full_acceptance=0
task41_v15_full_acceptance_count=0
task41_saved_b0_v16_analysis_count=0
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
        --task40-v30-execution-contract)
            ((index + 1 < ${#args[@]})) || { echo "V30 contract flag needs a path" >&2; exit 2; }
            v30_contract="${args[index + 1]}"
            ((v30_contract_count += 1))
            ((index += 1))
            ;;
        --task40-v30-execution-contract=*)
            v30_contract="${arg#*=}"
            ((v30_contract_count += 1))
            ;;
        --task40-v31-execution-contract)
            ((index + 1 < ${#args[@]})) || { echo "V31 contract flag needs a path" >&2; exit 2; }
            v31_contract="${args[index + 1]}"
            ((v31_contract_count += 1))
            ((index += 1))
            ;;
        --task40-v31-execution-contract=*)
            v31_contract="${arg#*=}"
            ((v31_contract_count += 1))
            ;;
        --task40-v32-execution-contract)
            ((index + 1 < ${#args[@]})) || { echo "V32 contract flag needs a path" >&2; exit 2; }
            v31_contract="${args[index + 1]}"
            ((v31_contract_count += 1))
            ((index += 1))
            ;;
        --task40-v32-execution-contract=*)
            v31_contract="${arg#*=}"
            ((v31_contract_count += 1))
            ;;
        --task40-v33-execution-contract)
            ((index + 1 < ${#args[@]})) || { echo "V33 contract flag needs a path" >&2; exit 2; }
            v31_contract="${args[index + 1]}"
            ((v31_contract_count += 1))
            ((index += 1))
            ;;
        --task40-v33-execution-contract=*)
            v31_contract="${arg#*=}"
            ((v31_contract_count += 1))
            ;;
        --task41-p0-execution-contract)
            ((index + 1 < ${#args[@]})) || { echo "Task41 contract flag needs a path" >&2; exit 2; }
            task41_contract="${args[index + 1]}"
            ((task41_contract_count += 1))
            ((index += 1))
            ;;
        --task41-p0-execution-contract=*)
            task41_contract="${arg#*=}"
            ((task41_contract_count += 1))
            ;;
        --task41-p0-saved-output-continuation)
            task41_saved_output_continuation=1
            ;;
        --task41-p0-saved-output-checker-only)
            task41_saved_output_checker_only=1
            ;;
        --task41-p0-saved-b0-evidence-audit|--task41-p0-saved-b0-volume-only-attribution|--task41-p0-saved-b0-selected-trace-star-audit)
            task41_saved_b0_evidence_audit=1
            ;;
        --task41-p0-saved-b0-v9-star-screen)
            task41_saved_b0_v9_star_screen=1
            ;;
        --task41-p0-saved-b0-v9-failed-terminal-audit)
            task41_saved_b0_v9_failed_terminal_audit=1
            ;;
        --task41-p0-saved-b0-y-g-comparison)
            task41_saved_b0_y_g_comparison=1
            ;;
        --task41-p0-saved-b0-v16-vector-analysis)
            task41_saved_b0_v16_analysis=1
            ((task41_saved_b0_v16_analysis_count += 1))
            ;;
        --v14-saved-rhs-candidate)
            task41_saved_b0_v14_candidate=1
            ;;
        --task41-p0-b0-v15-full-acceptance)
            task41_v15_full_acceptance=1
            ((task41_v15_full_acceptance_count += 1))
            ;;
        --task41-p0-b0-v17-selected-two-cell-replay)
            task41_v17_selected_two_cell=1
            ((task41_v17_selected_two_cell_count += 1))
            ;;
        --task41-p0-b0-v18-saved-jz-candidate)
            task41_v18_saved_jz=1
            ((task41_v18_saved_jz_count += 1))
            ;;
        --task41-p0-b0-v19-native-rank1)
            task41_v19_native_rank1=1
            ((task41_v19_native_rank1_count += 1))
            ;;
        --task41-p0-b0-v19-checker-only)
            task41_v19_checker_only=1
            ((task41_v19_checker_only_count += 1))
            ;;
        --v19-receipt-sha256)
            ((index + 1 < ${#args[@]})) || { echo "V19 receipt SHA flag needs one value" >&2; exit 2; }
            task41_v19_receipt_sha="${args[index + 1]}"
            ((task41_v19_receipt_sha_count += 1))
            ((index += 1))
            ;;
        --v19-receipt-sha256=*)
            task41_v19_receipt_sha="${arg#*=}"
            ((task41_v19_receipt_sha_count += 1))
            ;;
        --v19-receipt-path)
            ((index + 1 < ${#args[@]})) || { echo "V19 receipt path flag needs one value" >&2; exit 2; }
            task41_v19_receipt_path="${args[index + 1]}"
            ((task41_v19_receipt_path_count += 1))
            ((index += 1))
            ;;
        --v19-receipt-path=*)
            task41_v19_receipt_path="${arg#*=}"
            ((task41_v19_receipt_path_count += 1))
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
v30_campaign=0
if (( v30_contract_count != 0 )); then
    if (( v30_contract_count != 1 || v29_campaign || v31_contract_count )); then
        echo "V30 requires exactly one execution contract and cannot be combined with V29 or V31" >&2
        exit 2
    fi
    [[ "$v30_contract" == /* ]] || v30_contract="$repo_root/$v30_contract"
    if ! v30_values_text="$(cd -- "$repo_root" && python3 -m src.runners.task40_v30_contract \
        --launcher-values --contract "$v30_contract")"; then
        exit 2
    fi
    mapfile -t v30_values <<< "$v30_values_text"
    if (( ${#v30_values[@]} != 10 )) || [[ "${v30_values[0]}" != "$repo_root" ]]; then
        echo "V30 contract validator returned an incomplete or foreign-root binding" >&2
        exit 2
    fi
    [[ "${v30_values[4]}" =~ ^[1-9][0-9]*$ && "${v30_values[8]}" =~ ^[1-9][0-9]*$ && "${v30_values[9]}" == 0 ]] || {
        echo "V30 approved resource limits are invalid" >&2
        exit 2
    }
    v30_campaign=1
fi
v31_campaign=0
if (( v31_contract_count != 0 )); then
    if (( v31_contract_count != 1 || v29_campaign || v30_campaign )); then
        echo "V31/V32/V33 requires exactly one execution contract and cannot be combined with V29 or V30" >&2
        exit 2
    fi
    [[ "$v31_contract" == /* ]] || v31_contract="$repo_root/$v31_contract"
    if ! v31_values_text="$(cd -- "$repo_root" && python3 -m src.runners.task40_v31_contract \
        --launcher-values --contract "$v31_contract")"; then
        exit 2
    fi
    mapfile -t v31_values <<< "$v31_values_text"
    if (( ${#v31_values[@]} != 10 )) || [[ "${v31_values[0]}" != "$repo_root" ]]; then
        echo "V31 contract validator returned an incomplete or foreign-root binding" >&2
        exit 2
    fi
    [[ "${v31_values[4]}" =~ ^[1-9][0-9]*$ && "${v31_values[8]}" =~ ^[1-9][0-9]*$ && "${v31_values[9]}" == 0 ]] || {
        echo "V31 approved resource limits are invalid" >&2
        exit 2
    }
    v31_campaign=1
fi
task41_campaign=0
task41_values=()
if (( task41_saved_output_continuation && task41_saved_output_checker_only )); then
    echo "Task41 saved-output continuation and checker-only modes cannot be combined" >&2
    exit 2
fi
if (( task41_saved_b0_evidence_audit && (task41_saved_output_continuation || task41_saved_output_checker_only) )); then
    echo "Task41 B0 saved evidence audit cannot be combined with saved-output modes" >&2
    exit 2
fi
if (( task41_saved_b0_v9_star_screen && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison) )); then
    echo "Task41 V9 saved-star screen cannot be combined with another Task41 saved mode" >&2
    exit 2
fi
if (( task41_saved_b0_v9_failed_terminal_audit && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_y_g_comparison) )); then
    echo "Task41 V9 failed-terminal audit cannot be combined with another Task41 saved mode" >&2
    exit 2
fi
if (( task41_saved_b0_y_g_comparison && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit) )); then
    echo "Task41 saved y/g comparison cannot be combined with another Task41 saved mode" >&2
    exit 2
fi
if (( task41_saved_b0_v16_analysis_count > 1 )); then
    echo "Task41 V16 saved analysis selector may appear only once" >&2
    exit 2
fi
if (( task41_v17_selected_two_cell_count > 1 )); then
    echo "Task41 V17 selected two-cell selector may appear only once" >&2
    exit 2
fi
if (( task41_v18_saved_jz_count > 1 )); then
    echo "Task41 V18 saved-Jz selector may appear only once" >&2
    exit 2
fi
if (( task41_v19_native_rank1_count > 1 )); then
    echo "Task41 V19 native-rank1 selector may appear only once" >&2
    exit 2
fi
if (( task41_v19_checker_only_count > 1 || task41_v19_receipt_sha_count > 1 || task41_v19_receipt_path_count > 1 )); then
    echo "Task41 V19 checker-only selector, receipt path, and SHA may appear only once" >&2
    exit 2
fi
if (( task41_v19_checker_only != (task41_v19_receipt_sha_count == 1 && task41_v19_receipt_path_count == 1) )); then
    echo "Task41 V19 checker-only mode requires externally supplied receipt path and SHA" >&2
    exit 2
fi
if (( task41_v19_checker_only && !task41_v19_native_rank1 )); then
    echo "Task41 V19 checker-only mode requires the V19 native-rank1 selector" >&2
    exit 2
fi
if (( task41_v19_receipt_sha_count == 1 )) && [[ ! "$task41_v19_receipt_sha" =~ ^[0-9a-f]{64}$ ]]; then
    echo "Task41 V19 receipt SHA must be 64 lowercase hexadecimal characters" >&2
    exit 2
fi
if (( task41_v19_receipt_path_count == 1 )) && [[ "$task41_v19_receipt_path" != /* ]]; then
    echo "Task41 V19 receipt path must be absolute" >&2
    exit 2
fi
if (( task41_v19_native_rank1 && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_v9_star_screen || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis || task41_v15_full_acceptance || task41_v17_selected_two_cell || task41_v18_saved_jz) )); then
    echo "Task41 V19 native-rank1 route cannot be combined with another Task41 execution route" >&2
    exit 2
fi
if (( task41_v18_saved_jz && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_v9_star_screen || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis || task41_v15_full_acceptance || task41_v17_selected_two_cell) )); then
    echo "Task41 V18 saved-Jz candidate cannot be combined with another Task41 execution route" >&2
    exit 2
fi
if (( task41_v17_selected_two_cell && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_v9_star_screen || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis || task41_v15_full_acceptance) )); then
    echo "Task41 V17 selected replay cannot be combined with another Task41 execution route" >&2
    exit 2
fi
if (( task41_saved_b0_v16_analysis && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_v9_star_screen || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_v15_full_acceptance) )); then
    echo "Task41 V16 saved analysis cannot be combined with another Task41 execution route" >&2
    exit 2
fi
if (( task41_v15_full_acceptance_count > 1 )); then
    echo "Task41 V15 full-acceptance selector may appear only once" >&2
    exit 2
fi
if (( task41_v15_full_acceptance && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_v9_star_screen || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis) )); then
    echo "Task41 V15 full acceptance cannot be combined with saved-output routes" >&2
    exit 2
fi
if (( task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_evidence_audit || task41_saved_b0_v9_star_screen || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis || task41_v15_full_acceptance || task41_v17_selected_two_cell || task41_v18_saved_jz || task41_v19_native_rank1 )) && (( task41_contract_count != 1 )); then
    echo "Task41 saved audit/output modes require exactly one Task41 P0 execution contract" >&2
    exit 2
fi
if (( task41_saved_b0_v14_candidate && !task41_saved_b0_evidence_audit )); then
    echo "V14 saved RHS candidate requires the existing saved B0 evidence-audit service route" >&2
    exit 2
fi
if (( task41_contract_count != 0 )); then
    if (( task41_contract_count != 1 || v29_contract_count || v29_selector_count || v30_contract_count || v31_contract_count )); then
        echo "Task41 P0 requires exactly one contract and cannot be combined with Task40 contracts" >&2
        exit 2
    fi
    [[ "$task41_contract" == /* ]] || task41_contract="$repo_root/$task41_contract"
    if (( task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis || task41_v15_full_acceptance || task41_v17_selected_two_cell || task41_v18_saved_jz || task41_v19_native_rank1 )); then
        if ! task41_values_text="$(cd -- "$repo_root" && python3 -m src.runners.task41_p0_contract \
            --launcher-values --contract "$task41_contract" --saved-output-continuation)"; then
            exit 2
        fi
    elif ! task41_values_text="$(cd -- "$repo_root" && python3 -m src.runners.task41_p0_contract \
        --launcher-values --contract "$task41_contract")"; then
        exit 2
    fi
    mapfile -t task41_values <<< "$task41_values_text"
    if (( ${#task41_values[@]} != 12 )) || [[ "${task41_values[0]}" != "$repo_root" ]]; then
        echo "Task41 contract validator returned an incomplete or foreign-root binding" >&2
        exit 2
    fi
    [[ "${task41_values[7]}" =~ ^[1-9][0-9]*$ && "${task41_values[8]}" =~ ^[1-9][0-9]*$ && "${task41_values[9]}" == 0 ]] || {
        echo "Task41 approved resource limits are invalid" >&2
        exit 2
    }
    task41_campaign=1
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
if (( v30_campaign )); then
    task40_campaign=1
fi
if (( v31_campaign )); then
    task40_campaign=1
fi
service_properties=(
    "--property=WorkingDirectory=$repo_root"
    "--property=StandardOutput=append:$log_dir/$unit.log"
    "--property=StandardError=append:$log_dir/$unit.log"
)
if (( v31_campaign )); then
    service_properties+=(
        "--property=MemoryMax=${v31_values[4]}"
        "--property=MemorySwapMax=${v31_values[9]}"
    )
elif (( v30_campaign )); then
    service_properties+=(
        "--property=MemoryMax=${v30_values[4]}"
        "--property=MemorySwapMax=${v30_values[9]}"
    )
elif (( v29_campaign )); then
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
if (( task41_campaign )); then
    service_properties+=(
        "--property=MemoryMax=${task41_values[7]}"
        "--property=MemorySwapMax=${task41_values[9]}"
    )
fi
if (( task41_campaign )); then
    systemd-run --user --expand-environment=no --unit="$unit" --service-type=exec \
        "${service_properties[@]}" \
        /usr/bin/bash -lc '
set -euo pipefail
cd -- "$1"
repo_root=$1
unit=$2
task41_contract=$3
shift 3
args=("$@")
[[ "$task41_contract" == /* ]] || task41_contract="$repo_root/$task41_contract"
task41_saved_output_continuation=0
task41_saved_output_checker_only=0
task41_saved_b0_v9_failed_terminal_audit=0
task41_saved_b0_y_g_comparison=0
task41_saved_b0_v14_candidate=0
task41_saved_b0_v16_analysis=0
task41_v15_full_acceptance=0
task41_v17_selected_two_cell=0
task41_v18_saved_jz=0
task41_v19_native_rank1=0
for arg in "${args[@]}"; do
    if [[ "$arg" == --task41-p0-saved-output-continuation ]]; then
        task41_saved_output_continuation=1
    elif [[ "$arg" == --task41-p0-saved-output-checker-only ]]; then
        task41_saved_output_checker_only=1
    elif [[ "$arg" == --task41-p0-saved-b0-v9-failed-terminal-audit ]]; then
        task41_saved_b0_v9_failed_terminal_audit=1
    elif [[ "$arg" == --task41-p0-saved-b0-y-g-comparison ]]; then
        task41_saved_b0_y_g_comparison=1
    elif [[ "$arg" == --task41-p0-saved-b0-v16-vector-analysis ]]; then
        task41_saved_b0_v16_analysis=1
    elif [[ "$arg" == --v14-saved-rhs-candidate ]]; then
        task41_saved_b0_v14_candidate=1
    elif [[ "$arg" == --task41-p0-b0-v15-full-acceptance ]]; then
        task41_v15_full_acceptance=1
    elif [[ "$arg" == --task41-p0-b0-v17-selected-two-cell-replay ]]; then
        task41_v17_selected_two_cell=1
    elif [[ "$arg" == --task41-p0-b0-v18-saved-jz-candidate ]]; then
        task41_v18_saved_jz=1
    elif [[ "$arg" == --task41-p0-b0-v19-native-rank1 ]]; then
        task41_v19_native_rank1=1
    fi
done
if (( task41_v15_full_acceptance && (task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis) )); then
    echo "Task41 V15 full acceptance cannot be combined with saved-output routes" >&2
    exit 2
fi
unset TASK41_P0_V15_FULL_ACCEPTANCE TASK41_P0_V15_OUTPUT_DIRECTORY TASK41_P0_V17_SELECTED_TWO_CELL_REPLAY TASK41_P0_V18_SAVED_JZ_CANDIDATE TASK41_P0_V19_NATIVE_RANK1 TASK41_P0_V19_OUTPUT_DIRECTORY TASK41_P0_V19_CHECKER_ONLY TASK41_P0_V19_RECEIPT_SHA256 TASK41_P0_V19_RECEIPT_PATH
if (( task41_saved_output_continuation || task41_saved_output_checker_only || task41_saved_b0_v9_failed_terminal_audit || task41_saved_b0_y_g_comparison || task41_saved_b0_v14_candidate || task41_saved_b0_v16_analysis || task41_v15_full_acceptance || task41_v17_selected_two_cell || task41_v18_saved_jz || task41_v19_native_rank1 )); then
    mapfile -t values < <(python3 -m src.runners.task41_p0_contract \
        --launcher-values --contract "$task41_contract" --saved-output-continuation)
else
    mapfile -t values < <(python3 -m src.runners.task41_p0_contract \
        --launcher-values --contract "$task41_contract")
fi
(( ${#values[@]} == 12 )) && [[ "${values[0]}" == "$repo_root" ]]
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
source scripts/task40_fresh_c1/activate_native_complex.sh \
    "${values[1]}" "${values[2]}" "${values[3]}" native_linux
export TASK41_P0_STRICT_EXECUTION=1
export TASK41_P0_CONTRACT_PATH="$task41_contract"
export TASK41_P0_CONTRACT_SHA256="${values[4]}"
export TASK41_P0_EXECUTION_WINDOW_PATH="${values[5]}"
export TASK41_P0_EXECUTION_WINDOW_SHA256="${values[6]}"
export TASK41_P0_TASK_MEMORY_MAX_BYTES="${values[7]}"
export TASK41_P0_HOST_RESERVE_BYTES="${values[8]}"
export TASK41_P0_MEMORY_SWAP_MAX_BYTES="${values[9]}"
export TASK41_P0_EXPECTED_SOURCE_SHA="${values[11]}"
if (( task41_v15_full_acceptance )); then
    export TASK41_P0_V15_FULL_ACCEPTANCE=1
fi
if (( task41_v17_selected_two_cell )); then
    export TASK41_P0_V17_SELECTED_TWO_CELL_REPLAY=1
fi
if (( task41_v18_saved_jz )); then
    export TASK41_P0_V18_SAVED_JZ_CANDIDATE=1
fi
if (( task41_v19_native_rank1 )); then
    export TASK41_P0_V19_NATIVE_RANK1=1
fi
if (( task41_v19_checker_only )); then
    export TASK41_P0_V19_CHECKER_ONLY=1
    export TASK41_P0_V19_RECEIPT_SHA256="$task41_v19_receipt_sha"
    export TASK41_P0_V19_RECEIPT_PATH="$task41_v19_receipt_path"
fi
exec "${values[1]}/bin/python" scripts/task40_v20_service_workflow.py run-service \
    --unit "$unit" --runtime-prefix "${values[1]}" \
    --abi-receipt "${values[2]}" --jit-cache "${values[3]}" -- "${args[@]}"' \
        task41-p0 "$repo_root" "$unit" "$task41_contract" "${args[@]}"
    printf 'Unit: %s.service\nLog: %s/%s.log\n' "$unit" "$log_dir" "$unit"
    exit 0
fi
if (( v31_campaign )); then
    systemd-run --user --expand-environment=no --unit="$unit" --service-type=exec \
        "${service_properties[@]}" \
        /usr/bin/bash -lc \
        'set -euo pipefail
cd -- "$1"
repo_root=$1
unit=$2
v31_contract=$3
shift 3
args=("$@")
[[ "$v31_contract" == /* ]] || v31_contract="$repo_root/$v31_contract"
v31_values_text="$(python3 -m src.runners.task40_v31_contract --launcher-values --contract "$v31_contract")"
mapfile -t v31_values <<< "$v31_values_text"
(( ${#v31_values[@]} == 10 )) && [[ "${v31_values[0]}" == "$repo_root" ]]
unset _MYFENICS_WSL_QUALIFIED_ACTIVATION
source scripts/task40_fresh_c1/activate_native_complex.sh \
    "${v31_values[1]}" "${v31_values[2]}" "${v31_values[3]}" native_linux
export TASK40_V31_STRICT_EXECUTION=1
export TASK40_V31_CONTRACT_PATH="$v31_contract"
export TASK40_V31_CONTRACT_SHA256="${v31_values[5]}"
export TASK40_V31_EXECUTION_WINDOW_PATH="${v31_values[6]}"
export TASK40_V31_EXECUTION_WINDOW_SHA256="${v31_values[7]}"
export TASK40_V31_TASK_MEMORY_MAX_BYTES="${v31_values[4]}"
export TASK40_V31_HOST_RESERVE_BYTES="${v31_values[8]}"
export TASK40_V31_MEMORY_SWAP_MAX_BYTES="${v31_values[9]}"
exec "${v31_values[1]}/bin/python" scripts/task40_v20_service_workflow.py run-service \
    --unit "$unit" --runtime-prefix "${v31_values[1]}" \
    --abi-receipt "${v31_values[2]}" --jit-cache "${v31_values[3]}" -- "${args[@]}"' \
        task40-v31 "$repo_root" "$unit" "$v31_contract" "${args[@]}"
    printf 'Unit: %s.service\nLog: %s/%s.log\n' "$unit" "$log_dir" "$unit"
    exit 0
fi
systemd-run --user --expand-environment=no --unit="$unit" --service-type=exec \
    "${service_properties[@]}" \
    /usr/bin/bash -lc \
    'set -euo pipefail; cd -- "$1"; repo_root=$1; unit=$2; shift 2; args=("$@"); use_v10=0; use_v29=0; use_v30=0; v29_contract=""; v29_selector=""; v30_contract=""; for ((i=0; i<${#args[@]}; i++)); do arg="${args[i]}"; case "$arg" in --task40-v10-campaign-window|--task40-v10-campaign-window=*) use_v10=1 ;; --task40-v29-execution-contract) v29_contract="${args[i+1]}"; ((i+=1)); use_v29=1 ;; --task40-v29-execution-contract=*) v29_contract="${arg#*=}"; use_v29=1 ;; --task40-v29-factor-only-selector) v29_selector="${args[i+1]}"; ((i+=1)); use_v29=1 ;; --task40-v29-factor-only-selector=*) v29_selector="${arg#*=}"; use_v29=1 ;; --task40-v30-execution-contract) v30_contract="${args[i+1]}"; ((i+=1)); use_v30=1 ;; --task40-v30-execution-contract=*) v30_contract="${arg#*=}"; use_v30=1 ;; esac; done; if (( use_v30 )); then [[ "$v30_contract" == /* ]] || v30_contract="$repo_root/$v30_contract"; v30_values_text="$(python3 -m src.runners.task40_v30_contract --launcher-values --contract "$v30_contract")"; mapfile -t v30_values <<< "$v30_values_text"; (( ${#v30_values[@]} == 10 )) && [[ "${v30_values[0]}" == "$repo_root" ]]; unset _MYFENICS_WSL_QUALIFIED_ACTIVATION; source scripts/task40_fresh_c1/activate_native_complex.sh "${v30_values[1]}" "${v30_values[2]}" "${v30_values[3]}" native_linux; export TASK40_V30_STRICT_EXECUTION=1; export TASK40_V30_CONTRACT_PATH="$v30_contract"; export TASK40_V30_CONTRACT_SHA256="${v30_values[5]}"; export TASK40_V30_EXECUTION_WINDOW_PATH="${v30_values[6]}"; export TASK40_V30_EXECUTION_WINDOW_SHA256="${v30_values[7]}"; export TASK40_V30_TASK_MEMORY_MAX_BYTES="${v30_values[4]}"; export TASK40_V30_HOST_RESERVE_BYTES="${v30_values[8]}"; export TASK40_V30_MEMORY_SWAP_MAX_BYTES="${v30_values[9]}"; exec "${v30_values[1]}/bin/python" scripts/task40_v20_service_workflow.py run-service --unit "$unit" --runtime-prefix "${v30_values[1]}" --abi-receipt "${v30_values[2]}" --jit-cache "${v30_values[3]}" -- "${args[@]}"; fi; if (( use_v29 )); then [[ "$v29_contract" == /* ]] || v29_contract="$repo_root/$v29_contract"; [[ "$v29_selector" == /* ]] || v29_selector="$repo_root/$v29_selector"; v29_values_text="$(python3 -m src.runners.task40_v29_contract --launcher-values --contract "$v29_contract" --selector "$v29_selector")"; mapfile -t v29_values <<< "$v29_values_text"; (( ${#v29_values[@]} == 7 )) && [[ "${v29_values[0]}" == "$repo_root" ]]; unset _MYFENICS_WSL_QUALIFIED_ACTIVATION; source scripts/task40_fresh_c1/activate_native_complex.sh "${v29_values[1]}" "${v29_values[2]}" "${v29_values[3]}" native_linux; export TASK40_V29_STRICT_FACTOR_ONLY=1; exec "${v29_values[1]}/bin/python" scripts/task40_v20_service_workflow.py run-service --unit "$unit" --runtime-prefix "${v29_values[1]}" --abi-receipt "${v29_values[2]}" --jit-cache "${v29_values[3]}" -- "${args[@]}"; fi; case "${args[0]}" in *nonseparable_e2_p6_reference_v20.dat|*target_original_ny8_resource_pilot_v20.dat|*target_original_ny8_operator_probe_v22.dat) exec benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix/bin/python -S scripts/task40_v20_service_workflow.py run-service --unit "$unit" --runtime-prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix --abi-receipt benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json --jit-cache benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit -- "${args[@]}" ;; esac; if (( use_v10 )); then source scripts/task40_fresh_c1/activate_local_wsl_complex.sh benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/runtime_prefix benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4/abi_receipt.json benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl/window_qualification_jit; else source scripts/activate_myfenics_wsl.sh; fi; exec python scripts/run_case.py "${args[@]}"' \
    myfenics-case "$repo_root" "$unit" "${args[@]}"
printf 'Unit: %s.service\nLog: %s/%s.log\n' "$unit" "$log_dir" "$unit"
