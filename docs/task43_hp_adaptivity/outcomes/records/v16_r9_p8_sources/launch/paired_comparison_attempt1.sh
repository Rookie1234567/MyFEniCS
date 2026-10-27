#!/usr/bin/env bash
# V15 review section 9: one invocation consumes its slot, even before watchdog.
set -euo pipefail
repo=/home/fenics/Projects/NN-Lab-V2
prefix=/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v16_p8
contract=/home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v16_r9_p8_contract.json
stage=C
relative_root=support/paired_comparison_attempt1
work_stop=1740
whole_limit=1800
node_cap=8589934592
worker_argv=(
  python
  -u
  -m
  benchmarks.task43_hp_adaptivity.compare_round1_candidate
  --candidate-run-root
  /home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v16_p8/formal/R9_P8_attempt1/run
  --accepted-parent-selection-record
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json
  --attempt-id
  v16_r9_p8_paired_attempt1
  --paired-p8-contract
  /home/fenics/Projects/NN-Lab-V2/docs/task43_hp_adaptivity/outcomes/records/v16_r9_p8_contract.json
)

root="$prefix/$relative_root"
if [[ -e "$root" || -L "$root" ]]; then
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
# Only stdlib file reading/snapshots before watchdog; native ABI stays in worker.
python3 -I - "$repo" "$root" "$contract" "$stage" "$work_stop" "$whole_limit" "$node_cap" "${worker_argv[@]}" <<'SNAPSHOT'
import sys,pathlib,json,hashlib,shutil,datetime
repo,root,contract=map(pathlib.Path,sys.argv[1:4]);stage=sys.argv[4]
work,whole,cap=map(int,sys.argv[5:8]);argv=sys.argv[8:]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
c=json.loads(contract.read_text());prefix=pathlib.Path(c['artifact_prefix'])
if sha(contract) != '8305bc7bbef3dfc33145a9032a9ce7628b3648f43b4900a982c4b0528f38bc1b':raise RuntimeError('frozen V16 contract changed')
review=repo/c['authority']['review_path']
if sha(review)!=c['authority']['review_sha256']:raise RuntimeError('V15 review identity changed')
source=[]; inputs={}
def add(p,expected=None):
 p=pathlib.Path(p)
 if not p.is_absolute() or p.is_symlink() or not p.is_file():raise RuntimeError('noncanonical/missing input '+str(p))
 h=sha(p)
 if expected is not None and h!=expected:raise RuntimeError('input hash changed '+str(p))
 if str(p) in inputs and inputs[str(p)]['sha256']!=h:raise RuntimeError('input drift '+str(p))
 inputs[str(p)]={'path':str(p),'sha256':h,'size_bytes':p.stat().st_size}
 return h
pathsfile=prefix/'preparation/launch_source_paths.json'
if sha(pathsfile)!='5dd7cca16b018292b5302f6f7e15aced262b8b318d70f32b6a36abca59f52b4d':raise RuntimeError('source inventory changed')
for rel in json.loads(pathsfile.read_text()):
 p=repo/rel;out=root/'snapshots/source'/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
 h=add(p)
 if sha(out)!=h:raise RuntimeError('source copy mismatch '+rel)
 source.append({'path':rel,'sha256':h,'snapshot':str(out)})
for item in c['inputs']:add(repo/item['path'],item['sha256'])
add(contract);add(review);add(pathsfile)
record={'schema':'task43.v16.launch-input-manifest.v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'head':(root/'source_head.txt').read_text().strip(),'review_commit':c['authority']['review_commit'],
 'review_sha256':sha(review),'fixed_reviewed_head':'1290b4f283c01d81f23ba9e1a187458d24bde2af',
 'stage':stage,'contract_sha256':sha(contract),'launch_shell_sha256':sha(root/'snapshots/launch.sh'),
 'worker_argv':argv,'source':source,'formal_PDE_dispatch':stage=='F',
 'environment':{'activation':'scripts/activate_task40_phi90_pord64.sh','worker_only':{'HWLOC_COMPONENTS':'-x86','OMPI_MCA_pml':'ob1'},
 'cpu_affinity':[1],'mpi_size':1,'threads':dict.fromkeys(('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'),'1'),
 'PHYSICAL_NATIVE_CAPACITY':'task43_hp_adaptivity_resource_v1','PHYSICAL_NATIVE_NODE_CAP_BYTES':cap,
 'work_stop_seconds':work,'whole_limit_seconds':whole,'watchdog_interval_seconds':0.25},
 'cache_scope':'No --cache-path; no shared JIT/global cache claim','trace_boundary':'after taskset, worker plus descendants'}
if stage!='T':
 gate=prefix/'preparation/T_root_qualification.json';add(gate);q=json.loads(gate.read_text())
 if q.get('status')!='PASS_LIMITED_V16_SUPPORT' or q.get('contract_sha256')!=sha(contract):raise RuntimeError('T not root-qualified')
 if q.get('source_sha256')!={x['path']:x['sha256'] for x in source}:raise RuntimeError('current source differs from T frozen source')
 record['T_qualification']={'path':str(gate),'sha256':sha(gate)}
if stage in ('F','C'):
 record['space_source_id']='S_MAIN'
 sroot=prefix/c['phases']['S']['root'];joined_path=prefix/c['recovery_sources']['S_MAIN']['joined_terminal_path']
 add(joined_path);joined=json.loads(joined_path.read_text())
 if joined.get('status')!='S_COMPLETE_ROOT_VERIFIED' or joined.get('contract_sha256')!=sha(contract) or joined.get('space_source_id')!='S_MAIN':raise RuntimeError('S not root-qualified')
 for item in [*joined['products'].values(),joined['root_observation_record'],*[g['evidence'] for g in joined['gates'].values()]]:add(pathlib.Path(item['path']),item['sha256'])
 for name in ('snapshots/launch_manifest.json','watchdog/summary.json','launcher_exit_code.txt','watchdog_exit_code.txt','source_head.txt'):add(sroot/name)
 record['S_joined_terminal']={'path':str(joined_path),'sha256':sha(joined_path)}
if stage=='C':
 froot=prefix/c['phases']['F']['root'];joined_path=prefix/c['phases']['F']['joined_terminal_path']
 add(joined_path);joined=json.loads(joined_path.read_text())
 if joined.get('status')!='F_COMPLETE_ROOT_VERIFIED' or joined.get('contract_sha256')!=sha(contract):raise RuntimeError('F not root-qualified')
 for item in [*joined['products'].values(),joined['root_observation_record'],*[g['evidence'] for g in joined['gates'].values()]]:add(pathlib.Path(item['path']),item['sha256'])
 for name in ('snapshots/launch_manifest.json','watchdog/summary.json','launcher_exit_code.txt','watchdog_exit_code.txt','source_head.txt','run/candidate_plan.json','run/pre_validation_checkpoint.json','run/pre_validation_checkpoint.npz','run/solve/dtn_port_diffraction_orders_3d.json'):add(froot/name)
 record['F_joined_terminal']={'path':str(joined_path),'sha256':sha(joined_path)}
record['inputs']=list(inputs.values())
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
