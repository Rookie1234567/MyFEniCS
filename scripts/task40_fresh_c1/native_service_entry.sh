#!/usr/bin/env bash
set -euo pipefail
repo="$1"
prefix="$2"
receipt="$3"
run_dir="$4"
unset PYTHONPATH PYTHONHOME LD_PRELOAD LD_LIBRARY_PATH
source "$repo/scripts/task40_fresh_c1/activate_native_complex.sh" "$prefix" "$receipt" "$run_dir/jit"
export TMPDIR="$run_dir/tmp" TMP="$run_dir/tmp" TEMP="$run_dir/tmp"
exec "$prefix/bin/python" -m benchmarks.run_fresh_c1_p6_component \
  --supervised --output-dir "$run_dir" --abi-receipt "$receipt" \
  --total-deadline-utc 2026-10-04T06:41:49Z
