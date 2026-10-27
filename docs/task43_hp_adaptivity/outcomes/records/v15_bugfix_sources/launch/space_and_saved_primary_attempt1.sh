#!/usr/bin/env bash
# V15 user-authorized bug recovery: every invocation and failure is counted.
set -euo pipefail
repo=/home/fenics/Projects/NN-Lab-V2
prefix="$repo/benchmarks/artifacts/task43/v11_science/recovery_v15"
contract="$repo/docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
relative_root=support/space_and_saved_primary_attempt1
work_stop=5400
whole_limit=5580
node_cap=8589934592
worker_argv=(
  python
  -u
  -m
  benchmarks.task43_hp_adaptivity.round1_candidates
  --primary-diagnostic-contract
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json
  --execution-recovery-manifest
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json
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
paths=json.loads((repo/'benchmarks/artifacts/task43/v11_science/recovery_v12/preparation/launch_source_paths.json').read_text())
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
recovery=repo/'docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json'
record={'p2_source_id':'P2_BUGFIX','recovery_manifest_sha256':sha(recovery),'schema':'task43.v11.launch-input-manifest.v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':(root/'source_head.txt').read_text().strip(),'contract_sha256':sha(contract),'launch_shell_sha256':sha(root/'snapshots/launch.sh'),'worker_argv':argv,'source':source,'inputs':inputs,'cache_scope':'No --cache-path; no claim to audit or clean shared JIT/global caches','trace_boundary':'after taskset, worker plus descendants only'}
authorization=repo/'docs/task43_hp_adaptivity/outcomes/records/v15_user_bugfix_recovery_authorization.json'
if sha(authorization)!='2b39ca0a1b86e08dfee2f88ea12e85f0b0ec55d8be6c1540ce7e5dc13ddf40cc':raise RuntimeError('user authorization bytes changed')
a=json.loads(authorization.read_text());failure=repo/a['previous_failure']['path']
if sha(failure)!=a['previous_failure']['sha256']:raise RuntimeError('previous failed closeout changed')
if str(root)!=str(repo/a['p2_source']['support_root']):raise RuntimeError('P2 recovery root differs')
if sha(contract)!=a['old_contract_sha256'] or sha(recovery)!=a['old_recovery_manifest_sha256']:raise RuntimeError('old contract/manifest changed')
for p in (authorization,failure):inputs.append({'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size})
record['current_review_sha']=a['review_sha']
record['user_recovery_authorization']={'path':str(authorization),'sha256':sha(authorization)}
record['superseded_failure_closeout']={'path':str(failure),'sha256':sha(failure)}
record['environment']={'activation':'scripts/activate_task40_phi90_pord64.sh','worker_only':{'HWLOC_COMPONENTS':'-x86','OMPI_MCA_pml':'ob1'},'cpu_affinity':[1],'mpi_size':1,'threads':dict.fromkeys(('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'),'1'),'PHYSICAL_NATIVE_CAPACITY':'task43_hp_adaptivity_resource_v1','PHYSICAL_NATIVE_NODE_CAP_BYTES':8589934592,'work_stop_seconds':5400,'whole_limit_seconds':5580,'watchdog_interval_seconds':0.25}
shutil.copyfile(authorization,root/'snapshots/user_recovery_authorization.json')
(root/'snapshots/diff_from_v14.patch').write_bytes(__import__('subprocess').check_output(['git','diff','--binary','12c7d4b2d35d033defead807e3e4c5d3407dc85f','HEAD']))
qualification=repo/'benchmarks/artifacts/task43/v11_science/recovery_v15/preparation/field_key_binding_root_gate.json'
if sha(qualification)!='3745caeed4964b3b07e533c24fda865bf5cdd7e8fa2238349e528b13d68e399a':raise RuntimeError('support qualification identity changed')
q=json.loads(qualification.read_text())
if q['status']!='PASS_LIMITED_SUPPORT_ENGINEERING':raise RuntimeError('support tests not qualified')
if {x['path']:x['sha256'] for x in source}!=q['source_sha256']:raise RuntimeError('source/test bytes changed since focused validation')
inputs.append({'path':str(qualification),'sha256':sha(qualification),'size_bytes':qualification.stat().st_size})
record['support_qualification']={'path':str(qualification),'sha256':sha(qualification)}
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
