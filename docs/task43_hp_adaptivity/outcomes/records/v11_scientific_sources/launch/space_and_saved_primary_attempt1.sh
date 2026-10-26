#!/usr/bin/env bash
# V11: one invocation consumes this slot, including all pre-watchdog failures.
set -euo pipefail
repo=/home/fenics/Projects/NN-Lab-V2
prefix="$repo/benchmarks/artifacts/task43/v11_science"
contract="$repo/docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
relative_root=support/space_and_saved_primary_attempt1
work_stop=840
whole_limit=900
node_cap=8589934592
worker_argv=(
  python
  -u
  -m
  benchmarks.task43_hp_adaptivity.round1_candidates
  --primary-diagnostic-contract
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json
  --accepted-parent-selection-record
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json
)

root="$prefix/$relative_root"
if [[ -e "$root" ]]; then
  printf 'REFUSED existing unique attempt root: %s; this invocation still consumes its slot.\n' "$root" >&2
  exit 90
fi
mkdir -p -- "$(dirname "$root")"
mkdir -- "$root"
record_exit() {
  code=$?
  trap - EXIT
  printf '%s\n' "$code" > "$root/launcher_exit_code.txt" || true
  date -u +%Y-%m-%dT%H:%M:%S.%NZ > "$root/launcher_finished_utc.txt" || true
  exit "$code"
}
trap record_exit EXIT
date -u +%Y-%m-%dT%H:%M:%S.%NZ > "$root/launcher_started_utc.txt"
cd "$repo"
mkdir -- "$root/snapshots" "$root/strace"
cp -- "${BASH_SOURCE[0]}" "$root/snapshots/launch.sh"
printf '%s\n' "bash ${BASH_SOURCE[0]}" > "$root/launch_command.txt"
git rev-parse HEAD > "$root/source_head.txt"
git status --porcelain=v1 --untracked-files=all > "$root/source_status.txt"
git diff --binary HEAD > "$root/source_diff.patch"
[[ "$(git branch --show-current)" == task43_hp_adaptivity ]]
[[ ! -s "$root/source_status.txt" ]]
export TASK43_V11_ATTEMPT_ROOT="$root"
export TASK43_V11_TRACE_PREFIX="$root/strace/sched"
# Only stdlib file snapshots are executed here. Native/ABI checks belong to worker.
python3 -I - "$repo" "$root" "$contract" "${worker_argv[@]}" <<'SNAPSHOT'
import sys,pathlib,json,hashlib,shutil,datetime
repo,root,contract=map(pathlib.Path,sys.argv[1:4]);argv=sys.argv[4:]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
c=json.loads(contract.read_text());source=[];inputs=[]
paths=json.loads((repo/'benchmarks/artifacts/task43/v11_science/preparation/launch_source_paths.json').read_text())
for rel in paths:
 p=repo/rel;out=root/'snapshots/source'/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
 h=sha(p)
 if sha(out)!=h:raise RuntimeError('source copy mismatch '+rel)
 source.append({'path':rel,'sha256':h,'snapshot':str(out)})
for item in c['inputs']:
 p=repo/item['path'];h=sha(p)
 if h!=item['sha256']:raise RuntimeError('input changed: '+str(p))
 inputs.append({'path':str(p),'sha256':h,'size_bytes':p.stat().st_size})
if '--candidate-plan' in argv:
 p=pathlib.Path(argv[argv.index('--candidate-plan')+1]);out=root/'snapshots/candidate_plan.json';shutil.copyfile(p,out)
 inputs.append({'path':str(p),'sha256':sha(p),'snapshot':str(out)})
record={'schema':'task43.v11.launch-input-manifest.v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':(root/'source_head.txt').read_text().strip(),'contract_sha256':sha(contract),'launch_shell_sha256':sha(root/'snapshots/launch.sh'),'worker_argv':argv,'source':source,'inputs':inputs,'cache_scope':'No --cache-path; no claim to audit or clean shared JIT/global caches','trace_boundary':'after taskset, worker plus descendants only'}
(root/'snapshots/launch_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
SNAPSHOT
source scripts/activate_task40_phi90_pord64.sh
export PHYSICAL_NATIVE_CAPACITY=task43_hp_adaptivity_resource_v1
export PHYSICAL_NATIVE_NODE_CAP_BYTES="$node_cap"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
{
 printf 'activation=%s\npython=%s\n' "${_MYFENICS_NATIVE_QUALIFIED_ACTIVATION:-}" "$(command -v python)"
 printf 'node_cap=%s\nwork_stop_seconds=%s\nwhole_limit_seconds=%s\n' "$node_cap" "$work_stop" "$whole_limit"
 printf '%s\n' 'worker-only HWLOC_COMPONENTS=-x86 OMPI_MCA_pml=ob1' 'CPU1 MPI1 numerical threads=1' 'cache not supplied; cache audit NOT_MEASURED'
 printf 'argv='; printf '%q ' "${worker_argv[@]}"; printf '\n'
} > "$root/launch_context.txt"
set +e
taskset -c 1 python -u -m benchmarks.subreaper_watchdog \
 --directory "$root/watchdog" --wall-seconds "$work_stop" --interval 0.25 \
 --phase-path "$root/watchdog/workflow_phase.json" \
 -- bash -c '
   set -euo pipefail
   cd /home/fenics/Projects/NN-Lab-V2
   export HWLOC_COMPONENTS=-x86 OMPI_MCA_pml=ob1
   source scripts/activate_task40_phi90_pord64.sh
   export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
   export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
   exec taskset -c 1 strace -D -ff -ttt -k \
     -e trace=sched_setaffinity,sched_getaffinity \
     -o "$TASK43_V11_TRACE_PREFIX" "$@"
 ' task43-v11-worker "${worker_argv[@]}" > "$root/watchdog_stdout.json" 2> "$root/watchdog_stderr.txt"
code=$?
set -e
printf '%s\n' "$code" > "$root/watchdog_exit_code.txt"
# Root independently checks whole/trace/resources/cleanup after all tracer exits.
exit "$code"
