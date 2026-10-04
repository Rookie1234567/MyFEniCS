#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -ne 3 ]]; then
  echo "usage: $0 NATIVE_PREFIX NEW_RUN_DIRECTORY TOTAL_DEADLINE_UTC" >&2
  exit 64
fi
total_deadline_utc="$3"
if [[ ! "$total_deadline_utc" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
  echo "TOTAL_DEADLINE_UTC must be a fixed whole-second UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)" >&2
  exit 64
fi
if ! normalized_deadline="$(date -u -d "$total_deadline_utc" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" \
    || [[ "$normalized_deadline" != "$total_deadline_utc" ]]; then
  echo "TOTAL_DEADLINE_UTC is not a valid UTC timestamp" >&2
  exit 64
fi
control_smoke_arg=""
case "${TASK40_W0_NO_FE_CONTROL_SMOKE:-0}" in
  0) ;;
  1) control_smoke_arg="--control-smoke" ;;
  *) echo "TASK40_W0_NO_FE_CONTROL_SMOKE must be 0 or 1" >&2; exit 64 ;;
esac
prefix="$(realpath -e "$1")"
run_dir="$(realpath -m "$2")"
if [[ ! -x "$prefix/bin/python" ]]; then
  echo "native independent-prefix Python is missing: $prefix/bin/python" >&2
  exit 66
fi
if [[ -e "$run_dir" ]]; then
  echo "refusing to overwrite existing run directory: $run_dir" >&2
  exit 73
fi
mkdir -p "$(dirname "$run_dir")"
umask 077
mkdir "$run_dir"
mkdir -p "$run_dir/raw" "$run_dir/logs" "$run_dir/jit" "$run_dir/tmp" "$run_dir/supervision"
unset PYTHONPATH PYTHONHOME LD_PRELOAD LD_LIBRARY_PATH
receipt="$run_dir/abi_receipt.json"
export UCX_TLS=self
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
"$prefix/bin/python" "$repo/scripts/task40_fresh_c1/qualify_imports_only.py" --record "$receipt"
source "$repo/scripts/task40_fresh_c1/activate_native_complex.sh" "$prefix" "$receipt" "$run_dir/jit"
"$prefix/bin/python" -m benchmarks.run_fresh_c1_p6_component \
  --admission-only --output-dir "$run_dir" --abi-receipt "$receipt" \
  > "$run_dir/logs/native_admission.json"
systemctl --user show-environment >/dev/null
unit="task40freshc1_$(date -u +%Y%m%dT%H%M%SZ)_$$"
exec systemd-run --user --wait --collect --unit="$unit" --service-type=exec \
  --working-directory="$repo" --property=StandardOutput=journal --property=StandardError=journal \
  /bin/bash "$repo/scripts/task40_fresh_c1/native_service_entry.sh" \
  "$repo" "$prefix" "$receipt" "$run_dir" "$total_deadline_utc" "$control_smoke_arg"
