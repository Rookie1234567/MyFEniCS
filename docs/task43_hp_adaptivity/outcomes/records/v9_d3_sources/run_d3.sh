#!/usr/bin/env bash
set -euo pipefail

repo=/home/fenics/Projects/NN-Lab-V2
run_root="$repo/benchmarks/artifacts/task43/v7_support/d3_pml_ob1_import_probe_attempt1"
watchdog_dir="$run_root/watchdog"
trace_prefix="$run_root/strace/sched"
driver_dir="$run_root/driver_snapshot"
source_dir="$run_root/source_snapshot"
driver_path=/tmp/task43_v7_d3_proposal/run_d3.sh
probe_path=/tmp/task43_v7_d3_proposal/probe_import_affinity.py
source_paths=(
  benchmarks/task43_hp_adaptivity/h100_anchor.py
  benchmarks/task43_hp_adaptivity/a2_native_p6_diagnostic.py
  benchmarks/task43_hp_adaptivity/candidate_checkpoints.py
  src/io/native_capacity_profile.py
  src/test/test_task43_v3_failure_safe_order.py
  benchmarks/subreaper_watchdog.py
  scripts/activate_task40_phi90_pord64.sh
  docs/task43_hp_adaptivity/outcomes/records/workspace_environment_v1.json
)

if [[ -e "$run_root" ]]; then
  printf 'Refusing existing D3 root: %s\n' "$run_root" >&2
  exit 90
fi
mkdir -p "$run_root" "$driver_dir" "$source_dir" "$(dirname "$trace_prefix")"
record_launcher_exit() {
  status=$?
  trap - EXIT
  printf '%s\n' "$status" > "$run_root/launcher_exit_code.txt" || true
  exit "$status"
}
trap record_launcher_exit EXIT

cd "$repo"
install -D "$driver_path" "$driver_dir/run_d3.sh"
install -D "$probe_path" "$driver_dir/probe_import_affinity.py"
for relative_path in "${source_paths[@]}"; do
  install -D "$repo/$relative_path" "$source_dir/$relative_path"
done
git rev-parse HEAD > "$run_root/source_head.txt"
git status --short > "$run_root/source_status.txt"
printf '%s\n' 'bash /tmp/task43_v7_d3_proposal/run_d3.sh' > "$run_root/launch_command.txt"
sha256sum "${source_paths[@]}" > "$run_root/source_sha256.txt"
: > "$run_root/source_snapshot_sha256.txt"
for relative_path in "${source_paths[@]}"; do
  sha256sum "$source_dir/$relative_path" >> "$run_root/source_snapshot_sha256.txt"
done
sha256sum "$driver_path" "$probe_path" > "$run_root/driver_sha256.txt"
sha256sum "$driver_dir/run_d3.sh" "$driver_dir/probe_import_affinity.py" \
  > "$run_root/driver_snapshot_sha256.txt"

source scripts/activate_task40_phi90_pord64.sh
{
  printf 'activation_marker=%s\n' "${_MYFENICS_NATIVE_QUALIFIED_ACTIVATION:-}"
  printf 'python=%s\n' "$(command -v python)"
  printf 'strace=%s\n' "$(command -v strace || true)"
  printf 'PHYSICAL_NATIVE_CAPACITY=%s\n' 'task43_hp_adaptivity_resource_v1'
  printf 'PHYSICAL_NATIVE_NODE_CAP_BYTES=%s\n' '8589934592'
  printf 'OMP_NUM_THREADS=%s\n' '1'
  printf 'OPENBLAS_NUM_THREADS=%s\n' '1'
  printf 'MKL_NUM_THREADS=%s\n' '1'
  printf 'BLIS_NUM_THREADS=%s\n' '1'
  printf 'NUMEXPR_NUM_THREADS=%s\n' '1'
  printf 'VECLIB_MAXIMUM_THREADS=%s\n' '1'
  printf 'HWLOC_COMPONENTS=%s\n' '-x86'
  printf 'HWLOC_COMPONENTS_SCOPE=%s\n' 'inner watchdog worker shell only'
  printf 'OMPI_MCA_pml=%s\n' 'ob1'
  printf 'OMPI_MCA_pml_SCOPE=%s\n' 'inner watchdog worker shell only'
  printf 'watchdog_wall_seconds=%s\n' '100'
  printf 'watchdog_phase_path=%s\n' "$watchdog_dir/workflow_phase.json"
} > "$run_root/launch_context.txt"

export PHYSICAL_NATIVE_CAPACITY=task43_hp_adaptivity_resource_v1
export PHYSICAL_NATIVE_NODE_CAP_BYTES=8589934592
export TASK43_V6_D2_ROOT="$run_root"
export TASK43_V6_D2_TRACE_PREFIX="$trace_prefix"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1

set +e
taskset -c 1 python -u -m benchmarks.subreaper_watchdog \
  --directory "$watchdog_dir" \
  --wall-seconds 100 \
  --interval 0.25 \
  --phase-path "$watchdog_dir/workflow_phase.json" \
  -- bash -lc '
    set -euo pipefail
    cd /home/fenics/Projects/NN-Lab-V2
    export HWLOC_COMPONENTS=-x86
    export OMPI_MCA_pml=ob1
    source scripts/activate_task40_phi90_pord64.sh
    export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
    export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
    exec taskset -c 1 strace -ff -ttt -k \
      -e trace=sched_setaffinity,sched_getaffinity \
      -o "$TASK43_V6_D2_TRACE_PREFIX" \
      python -u "$TASK43_V6_D2_ROOT/driver_snapshot/probe_import_affinity.py"
  '
watchdog_exit=$?
set -e
exit "$watchdog_exit"
