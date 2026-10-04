#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 5 || $# -gt 6 ]]; then
  echo "usage: native_service_entry.sh REPO PREFIX ABI_RECEIPT RUN_DIRECTORY TOTAL_DEADLINE_UTC [--control-smoke]" >&2
  exit 64
fi
repo="$1"
prefix="$2"
receipt="$3"
run_dir="$4"
total_deadline_utc="$5"
control_smoke_arg="${6:-}"
if [[ -n "$control_smoke_arg" ]]; then
  if [[ "$control_smoke_arg" != "--control-smoke" ]]; then
    echo "unsupported native service mode: $6" >&2
    exit 64
  fi
fi
unset PYTHONPATH PYTHONHOME LD_PRELOAD LD_LIBRARY_PATH
source "$repo/scripts/task40_fresh_c1/activate_native_complex.sh" "$prefix" "$receipt" "$run_dir/jit"
export TMPDIR="$run_dir/tmp" TMP="$run_dir/tmp" TEMP="$run_dir/tmp"
exec "$prefix/bin/python" -m benchmarks.run_fresh_c1_p6_component \
  --supervised --output-dir "$run_dir" --abi-receipt "$receipt" \
  --total-deadline-utc "$total_deadline_utc" ${control_smoke_arg:+"$control_smoke_arg"}
