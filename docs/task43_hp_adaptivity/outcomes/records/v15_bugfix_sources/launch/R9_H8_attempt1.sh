#!/usr/bin/env bash
# V11: one invocation consumes this slot, including all pre-watchdog failures.
set -euo pipefail
repo=/home/fenics/Projects/NN-Lab-V2
prefix="$repo/benchmarks/artifacts/task43/v11_science"
contract="$repo/docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
relative_root=formal/R9_H8_attempt1
work_stop=6900
whole_limit=7200
node_cap=34359738368
worker_argv=(
  python
  -u
  -m
  benchmarks.task43_hp_adaptivity.h100_anchor
  --case
  round1_candidate_mpi1
  --run-root
  /home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v11_science/formal/R9_H8_attempt1/run
  --candidate-plan
  /home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v11_science/recovery_v15/support/space_and_saved_primary_attempt1/plan_output/plans/v11_r9_h8.json
  --candidate-id
  v11_r9_h8
  --candidate-acceptance-contract
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json
  --candidate-parent-selection-record
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json
  --same-lu-solve-residual-correction
  --direct-factor-backend
  mumps
  --primary-diagnostic-contract
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json
  --primary-diagnostic-phase
  R9_H8
  --execution-recovery-manifest
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json
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
record={'schema':'task43.v11.launch-input-manifest.v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':(root/'source_head.txt').read_text().strip(),'contract_sha256':sha(contract),'launch_shell_sha256':sha(root/'snapshots/launch.sh'),'worker_argv':argv,'source':source,'inputs':inputs,'cache_scope':'No --cache-path; no claim to audit or clean shared JIT/global caches','trace_boundary':'after taskset, worker plus descendants only'}
recovery=repo/'docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json'
authorization=repo/'docs/task43_hp_adaptivity/outcomes/records/v15_user_bugfix_recovery_authorization.json'
if sha(authorization)!='2b39ca0a1b86e08dfee2f88ea12e85f0b0ec55d8be6c1540ce7e5dc13ddf40cc':raise RuntimeError('user authorization changed')
p2root=repo/'benchmarks/artifacts/task43/v11_science/recovery_v15/support/space_and_saved_primary_attempt1'
joined_path=p2root/'v12_p2_joined_terminal.json'
if sha(joined_path)!='925cfbeb9517dd2f08d4ebf43f7ef9003bfe4af944241373c31f1668e547f29b':raise RuntimeError('P2 root gate identity differs')
joined=json.loads(joined_path.read_text())
if joined['status']!='P2_COMPLETE_ROOT_VERIFIED':raise RuntimeError('P2 incomplete')
for x in [*joined['products'].values(),joined['root_observation_record'],*[v['evidence'] for v in joined['gates'].values()]]:
 if sha(pathlib.Path(x['path']))!=x['sha256']:raise RuntimeError('P2 bound evidence bytes changed: '+x['path'])
p2paths=[joined_path,pathlib.Path(joined['root_observation_record']['path'])]
p2paths += [pathlib.Path(v['path']) for v in joined['products'].values()]
p2paths += [pathlib.Path(v['evidence']['path']) for v in joined['gates'].values()]
p2paths += [p2root/x for x in ('snapshots/launch_manifest.json','snapshots/launch.sh','watchdog/summary.json','launcher_exit_code.txt','watchdog_exit_code.txt')]
for p in dict.fromkeys(p2paths):inputs.append({'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size})
record['recovery_manifest_sha256']=sha(recovery)
record['p2_source_id']='P2_BUGFIX'
record['current_review_sha']='37f3376be410657fbaec86b0412086745419c506'
a=json.loads(authorization.read_text());failure=repo/a['previous_failure']['path']
if sha(failure)!=a['previous_failure']['sha256']:raise RuntimeError('previous failed closeout changed')
if sha(recovery)!=a['old_recovery_manifest_sha256'] or sha(contract)!=a['old_contract_sha256']:raise RuntimeError('old frozen identities changed')
for p in (authorization,failure,recovery):inputs.append({'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size})
record['user_recovery_authorization']={'path':str(authorization),'sha256':sha(authorization)}
record['superseded_failure_closeout']={'path':str(failure),'sha256':sha(failure)}
if joined['p2_source_id']!='P2_BUGFIX' or joined['user_recovery_authorization']!=record['user_recovery_authorization'] or joined['superseded_failure_closeout']!=record['superseded_failure_closeout']:raise RuntimeError('P2 authorization binding differs')
qualification=repo/'benchmarks/artifacts/task43/v11_science/recovery_v15/preparation/A1_primary_recovery_validation_root_gate.json'
if sha(qualification)!='437669d385e67d0e161905ee8061f4297f4721950c4f8375ae7c39ea1c0dec88':raise RuntimeError('support qualification changed')
q=json.loads(qualification.read_text())
if {x['path']:x['sha256'] for x in source}!=q['source_sha256']:raise RuntimeError('source/test bytes differ from actual focused validation')
inputs.append({'path':str(qualification),'sha256':sha(qualification),'size_bytes':qualification.stat().st_size})
record['support_qualification']={'path':str(qualification),'sha256':sha(qualification),'scope':'current 14-node localized validation plus exact-byte reused raw node; unchanged P2 and comparison tests retain earlier scoped evidence'}
shutil.copyfile(authorization,root/'snapshots/user_recovery_authorization.json')
(root/'snapshots/diff_from_v14.patch').write_bytes(__import__('subprocess').check_output(['git','diff','--binary','12c7d4b2d35d033defead807e3e4c5d3407dc85f','HEAD']))

record['P2_root_joined_gate']={'path':str(joined_path),'sha256':sha(joined_path)}
record['environment']={'activation': 'scripts/activate_task40_phi90_pord64.sh', 'worker_only': {'HWLOC_COMPONENTS': '-x86', 'OMPI_MCA_pml': 'ob1'}, 'cpu_affinity': [1], 'mpi_size': 1, 'threads': {'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'BLIS_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1', 'VECLIB_MAXIMUM_THREADS': '1'}, 'work_stop_seconds': 6900, 'whole_limit_seconds': 7200, 'node_cap_bytes': 34359738368, 'watchdog_interval_seconds': 0.25}
p3gate=repo/'benchmarks/artifacts/task43/v11_science/recovery_v15/preparation/A1_saved_primary_joined_root_gate.json'
if sha(p3gate)!='a535f9ef91b2cc084115b9d7931eaf406bf6d274973e0c503b96daa124d671d3':raise RuntimeError('P3 qualified gate changed')
p3g=json.loads(p3gate.read_text())
if p3g['status']!='A1_SAVED_PRIMARY_Q_GATES_PASSED_ROOT_VERIFIED':raise RuntimeError('P3 q gates not passed')
inputs.append({'path':str(p3gate),'sha256':sha(p3gate),'size_bytes':p3gate.stat().st_size})
record['P3_root_gate']={'path':str(p3gate),'sha256':sha(p3gate)}
for key in ('original_failed_terminal','postprocess_terminal','postprocess_root_observations','raw_stdlib_recheck','original_failure_closeout'):
 item=p3g[key];p=pathlib.Path(item['path'])
 if sha(p)!=item['sha256']:raise RuntimeError('P3 joined evidence differs: '+key)
 inputs.append({'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size})
record['P3_recovered_scientific_gate_scope']='failed original A1 plus saved-primary postprocessing; original endpoint failure retained; user authorized bug recovery; no extra solve'

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
