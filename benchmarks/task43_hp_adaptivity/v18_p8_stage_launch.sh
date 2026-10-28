#!/usr/bin/env bash
# Launch exactly one separately bound V18 P8 phase; this file never advances phases.
set -euo pipefail

repo=/home/fenics/Projects/NN-Lab-V2
prefix="$repo/benchmarks/artifacts/task43/v16_p8"
contract="$repo/docs/task43_hp_adaptivity/outcomes/records/v16_r9_p8_contract.json"
binding="$prefix/preparation/v18_p8_execution_recovery_attempt3.json"
summary="$repo/docs/task43_hp_adaptivity/outcomes/records/v18_p8_execution_recovery_v3.json"
comparison_binding="$prefix/preparation/v18_p8_comparison_recovery_attempt1.json"
comparison_summary="$repo/docs/task43_hp_adaptivity/outcomes/records/v18_p8_comparison_recovery_v1.json"
script_path="$repo/benchmarks/task43_hp_adaptivity/v18_p8_stage_launch.sh"
mode=${1:-}
invocation_monotonic_ns=$(python3 -c 'import time; print(time.monotonic_ns())')

atomic_text() {
  local path=$1 value=$2 tmp="${1}.tmp.$$"
  printf '%s\n' "$value" > "$tmp"
  mv -f -- "$tmp" "$path"
}

proc_start_ticks() {
  python3 - "$1" <<'PY'
import pathlib, sys
fields = pathlib.Path(f"/proc/{sys.argv[1]}/stat").read_text().rsplit(")", 1)[1].split()
print(fields[19])
PY
}

same_process() {
  local pid=$1 ticks=$2 actual
  [[ -r "/proc/$pid/stat" ]] || return 1
  actual=$(proc_start_ticks "$pid") || return 1
  [[ "$actual" == "$ticks" ]]
}

wait_for_watchdog() {
  local stop_first=${1:-false}
  if [[ "$stop_first" == true && "${watchdog_waited:-0}" != 1 && -n "${watchdog_pid:-}" ]] && same_process "$watchdog_pid" "${watchdog_start_ticks:-}"; then
    kill -TERM "$watchdog_pid" 2>/dev/null || true
  fi
  if [[ "${watchdog_waited:-0}" != 1 && -n "${watchdog_pid:-}" ]]; then
    if wait "$watchdog_pid"; then watchdog_code=0; else watchdog_code=$?; fi
    watchdog_waited=1
    atomic_text "$stage_root/watchdog_exit_code.txt" "$watchdog_code" || return 1
  fi
}

write_lifecycle_terminal() {
  local exit_code=$1
  python3 - "$stage_root" "$phase" "$exit_code" "$watchdog_pid" \
    "${watchdog_start_ticks:-}" "${watchdog_code:-}" \
    "${received_signal:-}" "$start_monotonic_ns" "$whole_seconds" <<'PY'
import datetime, hashlib, json, os, pathlib, sys, time
root = pathlib.Path(sys.argv[1]); phase = sys.argv[2]; code = int(sys.argv[3])
watchdog_pid = int(sys.argv[4]) if sys.argv[4] else None
watchdog_ticks = sys.argv[5] or None
watchdog_code = int(sys.argv[6]) if sys.argv[6] else None
signal_name = sys.argv[7] or None
started_ns = int(sys.argv[8]); whole = int(sys.argv[9])
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()
finished_ns = time.monotonic_ns()
elapsed = (finished_ns - started_ns) / 1e9
watchdog_summary = root / 'watchdog/summary.json'
resources = root / 'watchdog/resources.jsonl'
traces = sorted((root / 'strace').glob('sched*'))
summary_error = None
try:
    summary = json.loads(watchdog_summary.read_text()) if watchdog_summary.is_file() else {}
except (OSError, json.JSONDecodeError) as exc:
    summary = {}
    summary_error = str(exc)
resource_summary = None
if resources.is_file():
    rows = []
    for line in resources.read_text(errors='replace').splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    resource_summary = {
        'path': str(resources.resolve()), 'sha256': sha(resources), 'row_count': len(rows),
        'first_row': rows[0] if rows else None,
        'last_row': rows[-1] if rows else None,
    }
summary_ok = (
    summary_error is None and watchdog_summary.is_file()
    and summary.get('classification') == 'COMPLETED'
    and summary.get('leader_exit_code') == 0
    and summary.get('descendants_cleared') is True
    and summary.get('remaining_child_pids') == []
)
cleanup_ok = (
    summary_error is None and watchdog_summary.is_file()
    and summary.get('descendants_cleared') is True
    and summary.get('remaining_child_pids') == []
)
whole_ok = elapsed <= whole
completed = code == 0 and watchdog_code == 0 and summary_ok and whole_ok
terminal = {
    'schema': 'task43.v18.p8.execution-stage-terminal.v1',
    'phase': phase, 'classification': 'COMPLETED' if completed else 'INCOMPLETE',
    'launcher_exit_code': code, 'watchdog_exit_code': watchdog_code,
    'watchdog_pid': watchdog_pid, 'watchdog_start_ticks': watchdog_ticks,
    'received_signal': signal_name, 'stage_started_monotonic_ns': started_ns,
    'stage_finished_monotonic_ns': finished_ns, 'whole_elapsed_seconds': elapsed,
    'whole_limit_seconds': whole, 'whole_limit_pass': elapsed <= whole,
    'watchdog_summary': ({'path': str(watchdog_summary.resolve()), 'sha256': sha(watchdog_summary),
                          'classification': summary.get('classification'),
                          'leader_exit_code': summary.get('leader_exit_code'),
                          'descendants_cleared': summary.get('descendants_cleared'),
                          'remaining_child_pids': summary.get('remaining_child_pids'),
                          'sampled_process_tree_rss_peak_bytes': summary.get('sampled_process_tree_rss_peak_bytes'),
                          'sampled_process_tree_swap_peak_bytes': summary.get('sampled_process_tree_swap_peak_bytes')}
                         if watchdog_summary.is_file() else None),
    'watchdog_summary_error': summary_error,
    'summary_pass': summary_ok, 'cleanup_pass': cleanup_ok, 'whole_pass': whole_ok,
    'resource_samples': resource_summary,
    'trace_files': [{'path': str(path.resolve()), 'sha256': sha(path), 'size_bytes': path.stat().st_size}
                    for path in traces],
}
if phase == 'T':
    runtime_identity_path = root / 'v18_runtime_identity.json'
    try:
        manifest = json.loads((root / 'snapshots/launch_manifest.json').read_text())
        terminal['manifest_sha256'] = manifest['execution_recovery_binding']['sha256']
        terminal['source_sha256'] = manifest['source_sha256']
        terminal['targeted_fixture'] = manifest['targeted_fixture']
        if not runtime_identity_path.is_file() or runtime_identity_path.is_symlink():
            raise ValueError('actual T runtime identity was not recorded by the worker')
        runtime_identity = json.loads(runtime_identity_path.read_text())
        if runtime_identity.get('schema') != 'task43.v18.p8.runtime-identity.v1':
            raise ValueError('actual T runtime identity schema differs')
        terminal['runtime_identity'] = {
            'path': str(runtime_identity_path.resolve()), 'sha256': sha(runtime_identity_path),
            'worker_pid': runtime_identity.get('v11_watchdog_worker_identity', {}).get('worker_pid'),
            'watchdog_pid': runtime_identity.get('v11_watchdog_worker_identity', {}).get('watchdog_pid'),
            'tracer_pid': runtime_identity.get('v11_watchdog_worker_identity', {}).get('tracer_pid'),
            'petsc_scalar_type': runtime_identity.get('runtime_envelope', {}).get('petsc_scalar_type'),
            'petsc_int_type': runtime_identity.get('runtime_envelope', {}).get('petsc_int_type'),
            'mpi_size': runtime_identity.get('runtime_envelope', {}).get('mpi_size'),
            'rank_affinity': runtime_identity.get('runtime_envelope', {}).get('rank_affinity'),
            'math_threads': runtime_identity.get('runtime_envelope', {}).get('v11_math_threads'),
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        terminal['manifest_error'] = str(exc)
        completed = False
    terminal['schema'] = 'task43.v18.p8.execution-test-terminal.v1'
    terminal['exit_code'] = code
    terminal['classification'] = 'PASS' if completed else 'FAILED'
for name, value in (("launcher_exit_code.txt", code), ("launcher_finished_utc.txt", datetime.datetime.now(datetime.timezone.utc).isoformat())):
    tmp = root / (name + '.tmp')
    tmp.write_text(str(value) + '\n')
    os.replace(tmp, root / name)
target = root / ('test_terminal.json' if phase == 'T' else 'stage_terminal.json')
tmp = target.with_suffix(target.suffix + '.tmp')
tmp.write_text(json.dumps(terminal, indent=2, allow_nan=False) + '\n')
os.replace(tmp, target)
exit_record = {
    'schema': 'task43.v18.p8.launcher-exit.v1', 'phase': phase,
    'supervisor_pid': os.getppid(), 'launcher_exit_code': code,
    'watchdog_exit_code': watchdog_code, 'received_signal': signal_name,
    'stage_started_monotonic_ns': started_ns, 'stage_finished_monotonic_ns': finished_ns,
    'whole_elapsed_seconds': elapsed, 'whole_limit_seconds': whole,
    'summary_pass': summary_ok, 'cleanup_pass': cleanup_ok, 'whole_pass': whole_ok,
    'classification': terminal['classification'],
}
exit_path = root / 'launcher_exit.json'; exit_tmp = exit_path.with_suffix('.json.tmp')
exit_tmp.write_text(json.dumps(exit_record, indent=2) + '\n')
os.replace(exit_tmp, exit_path)
if not completed:
    raise SystemExit(1)
PY
}

finalize_lifecycle() {
  local result=$?
  trap - EXIT
  local wait_status=0 terminal_status=0
  if wait_for_watchdog true; then :; else wait_status=$?; fi
  if [[ "$wait_status" -ne 0 && "$result" -eq 0 ]]; then result=98; fi
  if write_lifecycle_terminal "$result"; then :; else terminal_status=$?; fi
  if [[ "$terminal_status" -ne 0 ]]; then
    if [[ "$result" -eq 0 ]]; then result=97; fi
    write_lifecycle_terminal "$result" || true
  fi
  exit "$result"
}

on_signal() {
  local name=$1 number=$2
  local forward=$name
  received_signal=$name
  trap - TERM INT HUP
  atomic_text "$stage_root/received_signal.txt" "$name" || true
  [[ "$name" == HUP ]] && forward=TERM
  if [[ -n "${watchdog_pid:-}" ]] && same_process "$watchdog_pid" "${watchdog_start_ticks:-}"; then
    kill -s "$forward" "$watchdog_pid" || true
  fi
  wait_for_watchdog false || true
  exit $((128 + number))
}

if [[ "$mode" == --lifecycle-fixture ]]; then
  stage_root=${2:?fixture root required}
  fixture_mode=${3:?fixture mode required}
  case "$fixture_mode" in normal|term|int|hup|prewatchdog_nonzero|missing_summary) ;; *) exit 91 ;; esac
  mkdir -p -- "$stage_root/strace"
  phase=FIXTURE
  whole_seconds=60
  start_monotonic_ns=$invocation_monotonic_ns
  received_signal=
  watchdog_pid=
  watchdog_start_ticks=
  watchdog_code=
  watchdog_waited=0
  trap 'on_signal TERM 15' TERM
  trap 'on_signal INT 2' INT
  trap 'on_signal HUP 1' HUP
  trap finalize_lifecycle EXIT
  if [[ "$fixture_mode" == prewatchdog_nonzero ]]; then
    bash -c 'touch "$1"; while [[ ! -e "$2" ]]; do sleep 0.01; done; exit 23' _ \
      "$stage_root/prewatchdog_ready" "$stage_root/prewatchdog_release" \
      > "$stage_root/watchdog_stdout.json" 2> "$stage_root/watchdog_stderr.txt" &
  else
    command=(bash -c 'if [[ "$1" == normal || "$1" == missing_summary ]]; then sleep 0.2; else sleep 60; fi' _ "$fixture_mode")
    taskset -c 1 python -u -m benchmarks.subreaper_watchdog \
      --directory "$stage_root/watchdog" --wall-seconds 120 --interval 0.1 -- "${command[@]}" \
      > "$stage_root/watchdog_stdout.json" 2> "$stage_root/watchdog_stderr.txt" &
  fi
  watchdog_pid=$!
  watchdog_start_ticks=$(proc_start_ticks "$watchdog_pid")
  if [[ "$fixture_mode" != prewatchdog_nonzero ]]; then
    for _ in {1..100}; do
      [[ -s "$stage_root/watchdog/resources.jsonl" ]] && break
      sleep 0.05
    done
    [[ -s "$stage_root/watchdog/resources.jsonl" ]] || exit 93
  fi
  python3 - "$stage_root/fixture_ready.json" "$watchdog_pid" "$watchdog_start_ticks" <<'PY'
import json, os, pathlib, sys
p = pathlib.Path(sys.argv[1]); t = p.with_suffix('.tmp')
t.write_text(json.dumps({'watchdog_pid': int(sys.argv[2]), 'start_ticks': sys.argv[3]}) + '\n')
os.replace(t, p)
PY
  if [[ "$fixture_mode" == prewatchdog_nonzero ]]; then
    for _ in {1..100}; do
      [[ -e "$stage_root/prewatchdog_ready" ]] && break
      sleep 0.01
    done
    [[ -e "$stage_root/prewatchdog_ready" ]] || exit 94
    atomic_text "$stage_root/prewatchdog_release" ready
  fi
  if [[ "$fixture_mode" == term || "$fixture_mode" == int || "$fixture_mode" == hup ]]; then
    if wait "$watchdog_pid"; then watchdog_code=0; else watchdog_code=$?; fi
    watchdog_waited=1
    atomic_text "$stage_root/watchdog_exit_code.txt" "$watchdog_code"
  else
    if wait "$watchdog_pid"; then watchdog_code=0; else watchdog_code=$?; fi
    watchdog_waited=1
    atomic_text "$stage_root/watchdog_exit_code.txt" "$watchdog_code"
  fi
  if [[ "$fixture_mode" == missing_summary ]]; then rm -f -- "$stage_root/watchdog/summary.json"; fi
  exit
fi

if [[ "$mode" == --supervise ]]; then
  stage_mode=${2:?phase required}
  phase=$stage_mode
  [[ "$stage_mode" != C_RECOVERY ]] || phase=C
  stage_root=${3:?stage root required}
  start_monotonic_ns=${4:?monotonic start required}
  case "$stage_mode" in T|S|F|C|C_RECOVERY) ;; *) exit 92 ;; esac
  case "$stage_mode" in
    T) work_seconds=270; whole_seconds=300; node_cap=8589934592 ;;
    S) work_seconds=1740; whole_seconds=1800; node_cap=8589934592 ;;
    F) work_seconds=6900; whole_seconds=7200; node_cap=34359738368 ;;
    C) work_seconds=1740; whole_seconds=1800; node_cap=8589934592 ;;
    C_RECOVERY) work_seconds=1740; whole_seconds=1800; node_cap=8589934592 ;;
  esac
  received_signal=
  watchdog_pid=
  watchdog_start_ticks=
  watchdog_code=
  watchdog_waited=0
  trap 'on_signal TERM 15' TERM
  trap 'on_signal INT 2' INT
  trap 'on_signal HUP 1' HUP
  trap finalize_lifecycle EXIT
  supervisor_pid=$BASHPID
  supervisor_ticks=$(proc_start_ticks "$supervisor_pid")
  python3 - "$stage_root/supervisor_identity.json" "$supervisor_pid" "$supervisor_ticks" "$phase" "$start_monotonic_ns" <<'IDENTITY'
import json,os,pathlib,sys
p=pathlib.Path(sys.argv[1]); tmp=p.with_suffix('.json.tmp')
tmp.write_text(json.dumps({'schema':'task43.v18.p8.supervisor-identity.v1','pid':int(sys.argv[2]),'start_ticks':sys.argv[3],'phase':sys.argv[4],'stage_started_monotonic_ns':int(sys.argv[5])},indent=2)+'\n')
os.replace(tmp,p)
IDENTITY
  cd "$repo"
  mkdir -p -- "$stage_root/snapshots" "$stage_root/strace"
  [[ "$(git branch --show-current)" == task43_hp_adaptivity ]]
  git status --porcelain=v1 --untracked-files=all > "$stage_root/source_status.txt"
  git diff --binary HEAD > "$stage_root/source_diff.patch"
  [[ ! -s "$stage_root/source_status.txt" ]]
  git rev-parse HEAD > "$stage_root/source_head.txt"
  cp -- "$script_path" "$stage_root/snapshots/launch.sh"
  export TASK43_V11_ATTEMPT_ROOT="$stage_root"
  export TASK43_V11_TRACE_PREFIX="$stage_root/strace/sched"
  export PHYSICAL_NATIVE_CAPACITY=task43_hp_adaptivity_resource_v1
  export PHYSICAL_NATIVE_NODE_CAP_BYTES="$node_cap"
  export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
  export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
  python3 -I - "$repo" "$prefix" "$contract" "$binding" "$summary" "$phase" "$stage_root" \
    "$node_cap" "$work_seconds" "$whole_seconds" "$stage_mode" "$comparison_binding" "$comparison_summary" <<'SNAPSHOT'
import datetime,hashlib,json,pathlib,shutil,sys
repo,prefix,contract,binding,tracked,phase,root=map(pathlib.Path,sys.argv[1:8]); phase=str(sys.argv[6])
cap,work,whole=map(int,sys.argv[8:11])
stage_mode=str(sys.argv[11]); comparison_binding=pathlib.Path(sys.argv[12]); comparison_tracked=pathlib.Path(sys.argv[13])
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def add(p,expected=None):
 p=pathlib.Path(p)
 if not p.is_absolute() or p.is_symlink() or not p.is_file():raise RuntimeError('missing/noncanonical input '+str(p))
 digest=sha(p)
 if expected is not None and digest!=expected:raise RuntimeError('input hash changed '+str(p))
 if str(p) in inputs and inputs[str(p)]['sha256']!=digest:raise RuntimeError('input drift '+str(p))
 inputs[str(p)]={'path':str(p),'sha256':digest,'size_bytes':p.stat().st_size}
 return digest
c=json.loads(contract.read_text()); rec=json.loads(binding.read_text()); summary=json.loads(tracked.read_text())
if sha(contract)!='8305bc7bbef3dfc33145a9032a9ce7628b3648f43b4900a982c4b0528f38bc1b':raise RuntimeError('V16 contract identity changed')
if rec.get('schema')!='task43.v18.p8-execution-recovery.v1' or summary.get('execution_manifest')!={'path':str(binding.resolve()),'sha256':sha(binding)}:raise RuntimeError('V18 binding/summary mismatch')
expected_phases={
 'T':{'root':'support/v18_execution_validation_attempt3','work_seconds':270,'whole_seconds':300,'rss_cap_bytes':8589934592},
 'S':{'root':'support/v18_space_attempt1','work_seconds':1740,'whole_seconds':1800,'rss_cap_bytes':8589934592},
 'F':{'root':'formal/v18_R9_P8_attempt1','work_seconds':6900,'whole_seconds':7200,'rss_cap_bytes':34359738368},
 'C':{'root':'support/v18_paired_comparison_attempt1','work_seconds':1740,'whole_seconds':1800,'rss_cap_bytes':8589934592},
}
comparison=None
historical_sources=rec['source_binding']['current_source_sha256']
if stage_mode=='C_RECOVERY':
 comparison=json.loads(comparison_binding.read_text()); comparison_summary_record=json.loads(comparison_tracked.read_text())
 ref={'path':str(binding.resolve()),'sha256':sha(binding)}
 expected_delta={'benchmarks/task43_hp_adaptivity/round1_candidates.py','benchmarks/task43_hp_adaptivity/h100_anchor.py','benchmarks/task43_hp_adaptivity/compare_round1_candidate.py'}
 current=comparison.get('source_binding',{}).get('current_source_sha256',{})
 changed={name for name in current if current[name]!=historical_sources.get(name)}
 if comparison.get('schema')!='task43.v18.p8-comparison-recovery.v1' or comparison.get('authorization',{}).get('scope')!='C_only_same_model_comparison_recovery' or comparison.get('authorization',{}).get('phase')!='C' or comparison.get('authorization',{}).get('E_allowed') is not False:raise RuntimeError('C-only authorization differs')
 if comparison.get('contract_sha256')!=sha(contract) or comparison.get('original_execution_binding')!=ref or comparison_summary_record.get('execution_manifest')!={'path':str(comparison_binding.resolve()),'sha256':sha(comparison_binding)}:raise RuntimeError('C-only manifest/summary/contract binding differs')
 if comparison_summary_record.get('authorization')!=comparison.get('authorization') or comparison_summary_record.get('phases')!=comparison.get('phases') or comparison_summary_record.get('source_binding')!=comparison.get('source_binding'):raise RuntimeError('C-only tracked summary differs')
 phase_record=comparison.get('phases',{}).get('C',{})
 expected_recovery={'root':'support/v18_paired_comparison_recovery_attempt1','work_seconds':1740,'whole_seconds':1800,'rss_cap_bytes':8589934592}
 if phase_record!=expected_recovery or (prefix/phase_record['root']).resolve()!=root.resolve():raise RuntimeError('C-only root or budget differs')
 if comparison.get('historical_head')!='196571795199dc0f48fd8ad3daaac258ab3390cb' or comparison.get('source_binding',{}).get('historical_source_sha256')!=historical_sources:raise RuntimeError('C-only historical source generation differs')
 if comparison.get('source_binding',{}).get('allowed_delta_paths')!=sorted(expected_delta) or changed!=expected_delta or set(current)!=set(historical_sources):raise RuntimeError('C-only source delta exceeds the three-reader allowlist')
 stage_sources=current
 stage_cap,stage_work,stage_whole=phase_record['rss_cap_bytes'],phase_record['work_seconds'],phase_record['whole_seconds']
else:
 if any(rec.get('phases',{}).get(phase,{}).get(key)!=value for key,value in expected_phases[phase].items()):raise RuntimeError('phase root or budget differs from V18 authorization')
 if (prefix/rec['phases'][phase]['root']).resolve()!=root.resolve():raise RuntimeError('stage root differs from V18 binding')
 stage_sources=historical_sources
 stage_cap,stage_work,stage_whole=expected_phases[phase]['rss_cap_bytes'],expected_phases[phase]['work_seconds'],expected_phases[phase]['whole_seconds']
if (cap,work,whole)!=(stage_cap,stage_work,stage_whole):raise RuntimeError('shell budget differs from phase authorization')
if rec.get('authorization',{}).get('E_allowed') is not False:raise RuntimeError('E is not frozen off')
inputs={}; sources=[]
source_list=prefix/'preparation/launch_source_paths.json'
if sha(source_list)!='5dd7cca16b018292b5302f6f7e15aced262b8b318d70f32b6a36abca59f52b4d':raise RuntimeError('frozen source inventory changed')
expected=stage_sources
for rel in json.loads(source_list.read_text()):
 p=repo/rel; h=add(p,expected.get(rel)); out=root/'snapshots/source'/rel; out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,out)
 if sha(out)!=h:raise RuntimeError('source snapshot copy mismatch '+rel)
 sources.append({'path':rel,'sha256':h,'snapshot':str(out)})
if set(expected)!={row['path'] for row in sources}:raise RuntimeError('V18 source snapshot inventory differs')
for item in c['inputs']:add(repo/item['path'],item['sha256'])
add(contract); add(binding); add(tracked); add(source_list)
for ref in rec['frozen_protocol']['v17_failure_evidence'].values():add(repo/ref['path'],ref['sha256'])
add(repo/'docs/task43_hp_adaptivity/review_report_v16.md',rec['frozen_protocol']['authorization_review']['sha256'])
fixture=rec['source_binding']['targeted_fixture']
if comparison is None:
 add(repo/fixture['path'],fixture['sha256'])
 launcher=rec['source_binding']['launch_script']
 active_summary=summary
else:
 fixture=comparison['targeted_fixture']; add(repo/fixture['path'],fixture['sha256'])
 add(comparison_binding); add(comparison_tracked)
 for ref in comparison['prior_evidence'].values():add(pathlib.Path(ref['path']),ref['sha256'])
 historical=rec['source_binding']['targeted_fixture']
 import subprocess
 old=subprocess.run(['git','show','196571795199dc0f48fd8ad3daaac258ab3390cb:'+historical['path']],cwd=repo,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
 if hashlib.sha256(old).hexdigest()!=historical['sha256']:raise RuntimeError('historical T fixture bytes differ')
 archived_fixture=root/'snapshots/historical_T_fixture.py'; archived_fixture.write_bytes(old); add(archived_fixture,historical['sha256'])
 historical_launcher=prefix/rec['phases']['S']['root']/'snapshots/launch.sh'
 add(historical_launcher,rec['source_binding']['launch_script']['sha256'])
 launcher=comparison['launch_script']
 active_summary=comparison_summary_record
launcher_path=repo/'benchmarks/task43_hp_adaptivity/v18_p8_stage_launch.sh'
if launcher.get('path')!='benchmarks/task43_hp_adaptivity/v18_p8_stage_launch.sh' or active_summary.get('launch_script')!=launcher:raise RuntimeError('V18 launch script authorization differs')
launcher_sha=add(launcher_path,launcher['sha256'])
if sha(root/'snapshots/launch.sh')!=launcher_sha:raise RuntimeError('V18 launch script snapshot differs')
if phase in ('S','F','C'):
 tr=prefix/rec['phases']['T']['root']; tq=tr/'T_root_qualification.json'; tt=tr/'test_terminal.json'
 add(tq); add(tt); q=json.loads(tq.read_text()); terminal=json.loads(tt.read_text())
 if q.get('schema')!='task43.v18.p8.execution-test-root-qualification.v1' or q.get('status')!='PASS_LIMITED_V18_EXECUTION' or q.get('manifest_sha256')!=sha(binding) or terminal.get('classification')!='PASS' or terminal.get('exit_code')!=0:raise RuntimeError('V18 T has not been root-qualified')
 if set(q.get('gates',{}))!={'source','input','resource','trace','exit','cleanup','whole'} or not all(v is True for v in q['gates'].values()):raise RuntimeError('V18 T qualification gates incomplete')
 ro=q['root_observation_record']; add(pathlib.Path(ro['path']),ro['sha256'])
 runtime_ref=terminal['runtime_identity']; add(pathlib.Path(runtime_ref['path']),runtime_ref['sha256'])
 if q.get('source_sha256')!=historical_sources or terminal.get('source_sha256')!=historical_sources:raise RuntimeError('T source identity differs')
if phase in ('F','C'):
 sr=prefix/rec['phases']['S']['root']; sj=sr/'v18_p8_space_joined_terminal.json'; add(sj); joined=json.loads(sj.read_text())
 if joined.get('status')!='S_COMPLETE_ROOT_VERIFIED' or joined.get('contract_sha256')!=sha(contract) or joined.get('execution_recovery_binding')!={'path':str(binding.resolve()),'sha256':sha(binding),'phase':'S'}:raise RuntimeError('new S root is not qualified for F')
 refs=[*joined['products'].values(),joined['root_observation_record'],*[g['evidence'] for g in joined['gates'].values()]]
 for ref in refs:add(pathlib.Path(ref['path']),ref['sha256'])
 for name in ('snapshots/launch_manifest.json','watchdog/summary.json','launcher_exit_code.txt','watchdog_exit_code.txt','source_head.txt'):add(sr/name)
if phase=='C':
 fr=prefix/rec['phases']['F']['root']; fj=fr/'v18_p8_endpoint_joined_terminal.json'; add(fj); joined=json.loads(fj.read_text())
 if joined.get('status')!='F_COMPLETE_ROOT_VERIFIED' or joined.get('contract_sha256')!=sha(contract) or joined.get('execution_recovery_binding')!={'path':str(binding.resolve()),'sha256':sha(binding),'phase':'F'}:raise RuntimeError('new F root is not qualified for C')
 for ref in [*joined['products'].values(),joined['root_observation_record'],*[g['evidence'] for g in joined['gates'].values()]]:add(pathlib.Path(ref['path']),ref['sha256'])
 for name in ('snapshots/launch_manifest.json','watchdog/summary.json','launcher_exit_code.txt','watchdog_exit_code.txt','source_head.txt','run/candidate_plan.json','run/pre_validation_checkpoint.json','run/pre_validation_checkpoint.npz','run/solve/dtn_port_diffraction_orders_3d.json'):add(fr/name)
manifest={'schema':'task43.v18.p8.launch-input-manifest.v1','phase':stage_mode,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':(root/'source_head.txt').read_text().strip(),'contract_path':str(contract.resolve()),'contract_sha256':sha(contract),'review_commit':'f72e1c8d031de7acc374f0806ddac06099c461c4','space_source_id':'S_MAIN','execution_recovery_binding':{'path':str(binding.resolve()),'sha256':sha(binding),'phase':phase},'launch_script':{'path':str(launcher_path.resolve()),'sha256':launcher_sha},'source_sha256':expected,'source':[{'path':x['path'],'sha256':x['sha256'],'snapshot':x['snapshot']} for x in sources],'inputs':list(inputs.values()),'targeted_fixture':fixture,'environment':{'activation':'scripts/activate_task40_phi90_pord64.sh','cpu_affinity':[1],'mpi_size':1,'numerical_threads':dict.fromkeys(('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'),'1'),'task_swap_bytes_max':0,'PHYSICAL_NATIVE_CAPACITY':'task43_hp_adaptivity_resource_v1','node_rss_cap_bytes':cap,'work_seconds_max':work,'whole_seconds_max':whole}}
if comparison is not None:
 manifest['historical_head']=comparison['historical_head']; manifest['historical_source_sha256']=historical_sources
 manifest['comparison_recovery_binding']={'path':str(comparison_binding.resolve()),'sha256':sha(comparison_binding),'phase':'C'}
out=root/'snapshots/launch_manifest.json'; out.write_text(json.dumps(manifest,indent=2)+'\n')
SNAPSHOT
  source scripts/activate_task40_phi90_pord64.sh
  export PHYSICAL_NATIVE_CAPACITY=task43_hp_adaptivity_resource_v1
  export PHYSICAL_NATIVE_NODE_CAP_BYTES="$node_cap"
  local_elapsed=$(( ($(python3 -c 'import time; print(time.monotonic_ns())') - start_monotonic_ns) / 1000000000 ))
  remaining_work=$((work_seconds - local_elapsed))
  if (( remaining_work <= 0 )); then
    atomic_text "$stage_root/prewatchdog_failure.txt" "work_budget_exhausted_during_setup"
    exit 96
  fi
  case "$stage_mode" in
    T) worker_argv=(python -m pytest -v -rA --maxfail=1 --junitxml "$stage_root/tests.xml" --basetemp "$stage_root/fixtures" src/test/test_task43_p8_execution_recovery.py) ;;
    S) worker_argv=(python -u -m benchmarks.task43_hp_adaptivity.round1_candidates --paired-p8-contract "$contract" --p8-execution-recovery-binding "$binding") ;;
    F)
      sroot="$prefix/support/v18_space_attempt1"
      worker_argv=(python -u -m benchmarks.task43_hp_adaptivity.h100_anchor --case round1_candidate_mpi1 --run-root "$prefix/formal/v18_R9_P8_attempt1/run" --candidate-plan "$sroot/plan_output/plans/v16_r9_p8.json" --candidate-id v16_r9_p8 --candidate-acceptance-contract "$repo/docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json" --candidate-parent-selection-record "$repo/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json" --same-lu-solve-residual-correction --direct-factor-backend mumps --paired-p8-contract "$contract" --p8-execution-recovery-binding "$binding" --primary-diagnostic-phase R9_P8) ;;
    C) worker_argv=(python -u -m benchmarks.task43_hp_adaptivity.compare_round1_candidate --candidate-run-root "$prefix/formal/v18_R9_P8_attempt1/run" --accepted-parent-selection-record "$repo/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json" --attempt-id v16_r9_p8_paired_attempt1 --paired-p8-contract "$contract" --p8-execution-recovery-binding "$binding") ;;
    C_RECOVERY)
recovery_worker='import json,os,pathlib,sys
import pytest
from mpi4py import MPI
from benchmarks.task43_hp_adaptivity.h100_anchor import _check_v11_runtime_envelope

runtime=_check_v11_runtime_envelope(MPI.COMM_WORLD)
identity=runtime["v11_watchdog_worker_identity"]
attempt_root=pathlib.Path(os.environ["TASK43_V11_ATTEMPT_ROOT"])
runtime_path=attempt_root/"runtime_identity.json"
if runtime_path.exists() or runtime_path.is_symlink():
    raise FileExistsError(f"refusing to overwrite C recovery runtime identity: {runtime_path}")
runtime_record={"schema":"task43.v18.p8.comparison-recovery-runtime-identity.v1","phase":"C_RECOVERY","runtime_envelope":runtime,"v11_watchdog_worker_identity":identity,"identity_ledger":{"first_check":"_check_v11_runtime_envelope","worker_pid":os.getpid(),"worker_start_ticks":identity["worker_start_ticks"],"watchdog_pid":identity["watchdog_pid"],"tracer_pid":identity["tracer_pid"],"phase_path":identity["phase_path"]}}
runtime_tmp=runtime_path.with_suffix(".json.tmp")
runtime_tmp.write_text(json.dumps(runtime_record,indent=2,allow_nan=False)+"\n",encoding="utf-8")
os.replace(runtime_tmp,runtime_path)
repo,contract,execution_binding,comparison_binding,candidate_root,selection_record=sys.argv[1:]
test_file=pathlib.Path(repo)/"src/test/test_task43_p8_execution_recovery.py"
selectors=[
    "test_v18_p5_h8_candidate_label_allows_only_historical_alias",
    "test_v18_c_recovery_uses_actual_comparison_and_historical_f_readers",
    "test_v18_c_recovery_actual_reader_rejects_unapproved_source_delta",
    "test_v18_q8_recovery_reads_bound_archive_without_sampling_or_copying",
]
pytest_args=["-q","--maxfail=1","--junitxml",str(attempt_root/"recovery_tests.xml"),"--basetemp",str(attempt_root/"recovery_fixtures")]
pytest_args.extend(f"{test_file}::{selector}" for selector in selectors)
pytest_status=pytest.main(pytest_args)
if pytest_status != pytest.ExitCode.OK:
    raise SystemExit(int(pytest_status))
sys.argv=["compare_round1_candidate","--candidate-run-root",candidate_root,"--accepted-parent-selection-record",selection_record,"--attempt-id","v16_r9_p8_paired_attempt1","--paired-p8-contract",contract,"--p8-execution-recovery-binding",execution_binding,"--p8-comparison-recovery-binding",comparison_binding]
from benchmarks.task43_hp_adaptivity.compare_round1_candidate import main
raise SystemExit(main())'
      worker_argv=(python -u -c "$recovery_worker" \
        "$repo" "$contract" "$binding" "$comparison_binding" \
        "$prefix/formal/v18_R9_P8_attempt1/run" \
        "$repo/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json") ;;
  esac
  worker_wrapper_script='set -euo pipefail; cd /home/fenics/Projects/NN-Lab-V2; export HWLOC_COMPONENTS=-x86 OMPI_MCA_pml=ob1; source scripts/activate_task40_phi90_pord64.sh; export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1; exec taskset -c 1 strace -D -ff -ttt -k -e trace=sched_setaffinity,sched_getaffinity -o "$TASK43_V11_TRACE_PREFIX" "$@"'
  python3 - "$stage_root/snapshots/launch_manifest.json" "$worker_wrapper_script" "${worker_argv[@]}" <<'ARGV'
import json, os, pathlib, sys
path=pathlib.Path(sys.argv[1]); manifest=json.loads(path.read_text())
wrapper=sys.argv[2]; application=sys.argv[3:]
thread_names=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','BLIS_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS')
controlled_names=('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION','VIRTUAL_ENV','PATH','PYTHONPATH','LD_LIBRARY_PATH',*thread_names,'HWLOC_COMPONENTS','OMPI_MCA_pml','PHYSICAL_NATIVE_CAPACITY','PHYSICAL_NATIVE_NODE_CAP_BYTES','TASK43_V11_ATTEMPT_ROOT','TASK43_V11_TRACE_PREFIX')
manifest['worker_argv']=application
manifest['watchdog_command_argv']=['bash','-c',wrapper,'task43-v18-worker',*application]
manifest['worker_wrapper_script']=wrapper
manifest['controlled_environment_scope']='supervisor_environment_before_watchdog'
manifest['controlled_environment']={name:os.environ.get(name) for name in controlled_names}
manifest['worker_environment_overrides']={
    'HWLOC_COMPONENTS':'-x86', 'OMPI_MCA_pml':'ob1',
    **dict.fromkeys(thread_names, '1'),
}
manifest['controlled_environment']['cpu_affinity']=[1]
manifest['controlled_environment']['mpi_size']=1
manifest['controlled_environment']['watchdog_identity_fields']=['PHYSICAL_WATCHDOG_PARENT_PID','PHYSICAL_WATCHDOG_PHASE_PATH']
tmp=path.with_suffix('.json.tmp'); tmp.write_text(json.dumps(manifest,indent=2)+'\n'); os.replace(tmp,path)
ARGV
  {
    printf 'activation=%s\npython=%s\nphase=%s\n' "${_MYFENICS_NATIVE_QUALIFIED_ACTIVATION:-}" "$(command -v python)" "$phase"
    printf 'node_cap=%s\nwork_seconds_max=%s\nwhole_seconds=%s\nremaining_work_seconds=%s\n' "$node_cap" "$work_seconds" "$whole_seconds" "$remaining_work"
    printf '%s\n' 'CPU1 MPI1 numerical threads=1; task-tree swap maximum=0' 'worker-only HWLOC_COMPONENTS=-x86 OMPI_MCA_pml=ob1' 'no cache path; cache audit not measured'
    printf 'argv='; printf '%q ' "${worker_argv[@]}"; printf '\n'
  } > "$stage_root/launch_context.txt"
  export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
  export BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
  taskset -c 1 python -u -m benchmarks.subreaper_watchdog \
    --directory "$stage_root/watchdog" --wall-seconds "$remaining_work" --interval 0.25 \
    --phase-path "$stage_root/watchdog/workflow_phase.json" --grace-seconds 2 -- \
    bash -c "$worker_wrapper_script" task43-v18-worker "${worker_argv[@]}" \
    > "$stage_root/watchdog_stdout.json" 2> "$stage_root/watchdog_stderr.txt" &
  watchdog_pid=$!
  watchdog_start_ticks=$(proc_start_ticks "$watchdog_pid")
  set +e
  wait "$watchdog_pid"
  watchdog_code=$?
  set -e
  watchdog_waited=1
  atomic_text "$stage_root/watchdog_exit_code.txt" "$watchdog_code"
  exit "$watchdog_code"
fi

case "$mode" in T|S|F|C|C_RECOVERY) ;; *) printf 'usage: bash %s {T|S|F|C|C_RECOVERY}\n' "$script_path" >&2; exit 64 ;; esac
stage_mode=$mode
phase=$mode
if [[ "$mode" == C_RECOVERY ]]; then
  phase=C
  recovery_info=$(python3 - "$comparison_binding" "$comparison_summary" "$binding" <<'ROOTINFO' || exit 89
import hashlib,json,pathlib,sys
manifest,summary,execution=map(pathlib.Path,sys.argv[1:4])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if any(p.is_symlink() or not p.is_file() for p in (manifest,summary,execution)):raise SystemExit('missing or symlinked C recovery binding')
r=json.loads(manifest.read_text()); s=json.loads(summary.read_text())
if r.get('schema')!='task43.v18.p8-comparison-recovery.v1' or r.get('authorization',{}).get('phase')!='C' or r.get('authorization',{}).get('E_allowed') is not False:raise SystemExit('C recovery authority differs')
if r.get('original_execution_binding')!={'path':str(execution.resolve()),'sha256':sha(execution)} or s.get('execution_manifest')!={'path':str(manifest.resolve()),'sha256':sha(manifest)}:raise SystemExit('C recovery binding hashes differ')
p=r.get('phases',{}).get('C',{})
if p!={'root':'support/v18_paired_comparison_recovery_attempt1','work_seconds':1740,'whole_seconds':1800,'rss_cap_bytes':8589934592}:raise SystemExit('C recovery root or budget differs')
print(p['root'],p['work_seconds'],p['whole_seconds'],p['rss_cap_bytes'])
ROOTINFO
  )
  read -r relative_root work_seconds whole_seconds node_cap <<<"$recovery_info"
else
  case "$phase" in
    T) relative_root=support/v18_execution_validation_attempt3; work_seconds=270; whole_seconds=300; node_cap=8589934592 ;;
    S) relative_root=support/v18_space_attempt1; work_seconds=1740; whole_seconds=1800; node_cap=8589934592 ;;
    F) relative_root=formal/v18_R9_P8_attempt1; work_seconds=6900; whole_seconds=7200; node_cap=34359738368 ;;
    C) relative_root=support/v18_paired_comparison_attempt1; work_seconds=1740; whole_seconds=1800; node_cap=8589934592 ;;
  esac
fi
stage_root="$prefix/$relative_root"
if [[ "$stage_mode" == C_RECOVERY ]]; then
  for path in "$repo/benchmarks" "$repo/benchmarks/artifacts" \
    "$repo/benchmarks/artifacts/task43" "$prefix" "$prefix/support" "$stage_root"; do
    [[ ! -L "$path" ]] || { printf 'REFUSED symlinked C recovery root component: %s\n' "$path" >&2; exit 90; }
  done
fi
[[ ! -e "$stage_root" && ! -L "$stage_root" ]] || { printf 'REFUSED existing unique V18 root: %s\n' "$stage_root" >&2; exit 90; }
mkdir -p -- "$(dirname "$stage_root")"
mkdir -- "$stage_root"
start_monotonic_ns=$invocation_monotonic_ns
atomic_text "$stage_root/launcher_started_utc.txt" "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)"
nohup setsid env --default-signal=INT --default-signal=TERM --default-signal=HUP taskset -c 1 bash "$script_path" --supervise "$stage_mode" "$stage_root" "$start_monotonic_ns" \
  > "$stage_root/supervisor_stdout.log" 2>&1 < /dev/null &
for _ in {1..100}; do
  [[ -s "$stage_root/supervisor_identity.json" ]] && break
  sleep 0.02
done
if [[ -s "$stage_root/supervisor_identity.json" ]]; then
  cp -- "$stage_root/supervisor_identity.json" "$stage_root/launcher_identity.json"
  read -r launcher_pid launcher_ticks < <(python3 - "$stage_root/launcher_identity.json" <<'IDENTITY'
import json,sys
d=json.load(open(sys.argv[1])); print(d['pid'],d['start_ticks'])
IDENTITY
)
  printf 'V18 P8 %s detached supervisor PID=%s start_ticks=%s root=%s\n' "$stage_mode" "$launcher_pid" "$launcher_ticks" "$stage_root"
else
  printf 'V18 P8 %s supervisor did not publish identity within 2 seconds; root retained at %s\n' "$stage_mode" "$stage_root" >&2
  exit 95
fi
