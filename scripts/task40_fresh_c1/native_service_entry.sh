#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 5 || $# -gt 7 ]]; then
  echo "usage: native_service_entry.sh REPO PREFIX ABI_RECEIPT RUN_DIRECTORY TOTAL_DEADLINE_UTC [RUNTIME_PROFILE] [--control-smoke]" >&2
  exit 64
fi
repo="$1"
prefix="$2"
receipt="$3"
run_dir="$4"
total_deadline_utc="$5"
runtime_profile="native_linux"
control_smoke_arg=""
if [[ $# -ge 6 ]]; then
  if [[ "$6" == "--control-smoke" ]]; then
    # Preserve the original six-argument native service form.
    control_smoke_arg="$6"
  else
    runtime_profile="$6"
    control_smoke_arg="${7:-}"
  fi
fi
if [[ "$runtime_profile" != "native_linux" && "$runtime_profile" != "local_wsl2_authorized" ]]; then
  echo "unsupported Task40 runtime profile: $runtime_profile" >&2
  exit 64
fi
if [[ -n "$control_smoke_arg" && "$control_smoke_arg" != "--control-smoke" ]]; then
  echo "unsupported Task40 service mode: $control_smoke_arg" >&2
  exit 64
fi
unset PYTHONPATH PYTHONHOME LD_PRELOAD LD_LIBRARY_PATH
case "$runtime_profile" in
  native_linux)
    source "$repo/scripts/task40_fresh_c1/activate_native_complex.sh" "$prefix" "$receipt" "$run_dir/jit"
    ;;
  local_wsl2_authorized)
    source "$repo/scripts/task40_fresh_c1/activate_local_wsl_complex.sh" "$prefix" "$receipt" "$run_dir/jit"
    ;;
esac
export TMPDIR="$run_dir/tmp" TMP="$run_dir/tmp" TEMP="$run_dir/tmp"
exec "$prefix/bin/python" -m benchmarks.run_fresh_c1_p6_component \
  --supervised --output-dir "$run_dir" --abi-receipt "$receipt" \
  --total-deadline-utc "$total_deadline_utc" ${control_smoke_arg:+"$control_smoke_arg"}
