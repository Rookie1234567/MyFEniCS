from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,gzip,subprocess,time,shutil
ROOT=Path('/home/fenics/Projects/NN-Lab');TMP=ROOT/'tmp/task042/v28';ART=ROOT/'benchmarks/artifacts/task042/v28';REC=ROOT/'docs/task042_neural_coarse_inverse/outcomes/records';ART.mkdir(exist_ok=True)
SOURCE='4808fcab78bbf1b1284ffba1f3ff19b0033fb937';REVIEW='455d816f01a44cdb98c53c893f48898602aaf752'
def write(path,data):
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def ref(path):
 return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)
def sizes(path):return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())
aux=[];observations=[];rss=swap=0
for folder in sorted(TMP.glob('aux_*')):
 if not folder.is_dir():continue
 receipt=folder/'admission.json'
 if not receipt.exists():continue
 d=json.loads(receipt.read_text());target=REC/('admission_'+('accepted' if d['status']=='ADMITTED' else 'rejected')+'_v28.json.gz')
 target.write_bytes(gzip.compress(receipt.read_bytes(),mtime=0))
 recomputed=dict(CPU_SMT=d['gates']['CPU_SMT'],MEMORY='NOT_CHECKED',DISK='NOT_CHECKED',PSI='NOT_CHECKED')
 if d['gates']['MEMORY']!='NOT_CHECKED':
  m=d['memory'];reserve=max(128*2**30,int(.1*m['effective_total_bytes']));cap=min(16*2**30,m['effective_available_bytes']-reserve-128*2**30)
  assert reserve==m['system_reserve_bytes'] and cap==m['launch_cap_bytes']
  recomputed['MEMORY']='PASS' if cap>=16*2**30 else 'FAIL'
 if d['gates']['DISK']!='NOT_CHECKED':recomputed['DISK']='PASS' if d['disk_free_bytes']>=50*2**30 else 'FAIL'
 if d['gates']['PSI']!='NOT_CHECKED':recomputed['PSI']='PASS' if d['memory_pressure']['some']['avg10']<1. and d['memory_pressure']['full']['avg10']<.1 else 'FAIL'
 assert all(recomputed[k]==d['gates'][k] for k in recomputed)
 observations.append(dict(raw=ref(receipt),lossless_gzip=ref(target),raw_sha256=ref(receipt)['sha256'],status=d['status'],utc=d['utc'],monotonic=d['monotonic'],finished_monotonic=d['finished_monotonic'],observed_probe_seconds=d['finished_monotonic']-d['monotonic'],pid=d['pid'],process_start_ticks=d['process_start_ticks'],cwd=d['cwd'],exact_input=d['input_path'],candidate_cpus=d['candidate_cpus'],selected_cpu=d.get('selected_cpu'),gates=d['gates'],recomputed_gates=recomputed,not_zero_interference_proof=True))
 summary=folder/'summary.json'
 if summary.exists():
  s=json.loads(summary.read_text());rss=max(rss,s['sampled_process_tree_rss_peak_bytes']);swap=max(swap,s['sampled_process_tree_swap_peak_bytes'])
  aux.append(dict(summary=ref(summary),worker_log=ref(folder/'supervision/worker.log'),timeline=ref(folder/'supervision/resources.jsonl'),baseline=ref(folder/'baseline.json'),elapsed_seconds=s['elapsed_seconds'],rss_peak_bytes=s['sampled_process_tree_rss_peak_bytes'],swap_peak_bytes=s['sampled_process_tree_swap_peak_bytes'],descendants_cleared=s['descendants_cleared'],classification=s['classification'],CPU=d['selected_cpu']))
raw_logs=[]
for name in ('auxiliary_stdout.txt','auxiliary_stderr.txt','final_auxiliary_stdout.txt','final_auxiliary_stderr.txt'):
 p=TMP/name;target=REC/(name.replace('.txt','_v28.txt'));target.write_bytes(p.read_bytes());raw_logs.append(dict(original=ref(p),tracked=ref(target),raw_redirected_at_invocation=True,not_transcription=True))
replays=json.loads((TMP/'admission_replay.json').read_text())
write(REC/'admission_checker_v28.json',dict(schema='task042.admission-replay.v28',implementation_source=SOURCE,checker_entry=ref(ROOT/'benchmarks/task042_admission_receipt.py'),receipt_results=replays['rows'],observations=observations,no_reprobe=True,formal_admission_attempted=False,formal_actor_started=False))
plan=json.loads((ROOT/'input/task042_neural_coarse_inverse/return_block_direction_v28.json').read_text());book=json.loads((TMP/'ledger.json').read_text());oldbook=ROOT/'tmp/task042/v27/ledger.json'
assert book['closed'] and book['active'] is None and not book['runs'] and all(v==0 for v in book['charged'].values())
assert json.loads(oldbook.read_text())['closed']
newwall=sum(x['elapsed_seconds'] for x in aux);carry=12.366657367907465
cost=dict(record_generator=ref(Path(__file__)),schema='task042.resource-costs.v28',identity='shared-workstation',review=REVIEW,implementation_source=SOURCE,actual_numeric_source=None,
 V27_carried_supervised_auxiliary_seconds=carry,V28_supervised_auxiliary_seconds=newwall,cumulative_V27_V28_numeric_and_supervised_auxiliary_seconds=carry+newwall,cumulative_limit_seconds=600.,remaining_authorized_seconds=600.-carry-newwall,numeric_actor_seconds=0.,formal_actor_runs=0,formal_admission_attempts=0,
 auxiliary_admission_attempts=2,successful_auxiliary_runs=len(aux),auxiliary_admission_rejections=1,admission_probe_seconds_not_actor_cost=[x['observed_probe_seconds'] for x in observations],
 all_implementation_reading_and_publishing_cost='included in immutable total elapsed; independent phase split unknown',window=json.loads((TMP/'window.json').read_text()),clock_at_queue_close=book['clock_at_close'],V27_window_readonly=ref(ROOT/'tmp/task042/v27/window.json'),
 RSS=dict(sampled_simultaneous_process_tree_peak_bytes=rss,scope='one successful auxiliary only; no numeric actor',sampling_seconds=.5,warning_bytes=12*2**30,hard_bytes=16*2**30,cgroup_limit_claimed=False),own_swap_peak_bytes=swap,task_VRAM_bytes=0,OOC_bytes=0,
 actual_CPU=[x['CPU'] for x in aux],math_threads=1,MPI_size=1,DataLoader_workers=0,pure_environment=True,FE_JIT_Torch_loaded=False,auxiliary_runs=aux,
 real_numeric_counts=book['charged'],historical_formal_research_lower_bound_seconds=77161.55713859801,historical_auxiliary_and_full_N1_warm_lineage_seconds='unknown retained; not zero',
 nominal_actor_capacity_bytes=4807239744,capacity_identity='derived not allocated/RSS',neighbor_impact='INCONCLUSIVE; no zero-impact claim',neighbor_settings_changed=False,
 storage_at_observation=dict(V27_artifact_TMP_docs_bytes=sizes(ROOT/'benchmarks/artifacts/task042/v27')+sum(sizes(p) for p in (ROOT/'tmp/task042').glob('v27*'))+sum(p.stat().st_size for p in REC.glob('*v27*')),V28_artifact_TMP_bytes=sizes(ART)+sum(sizes(p) for p in (ROOT/'tmp/task042').glob('v28*')),all_task_artifact_bytes=sizes(ROOT/'benchmarks/artifacts/task042'),free_disk_bytes=shutil.disk_usage(ROOT).free,limits=dict(new_V27_V28_persistent_bytes=128*2**20,all_task_artifact_bytes=20*2**30,free_disk_min_bytes=50*2**30)))
write(ART/'minimum_cost.json',cost);write(REC/'resource_costs_v28.json',cost)
minimum=dict(status='NOT_RUN_AUXILIARY_CPU_ADMISSION',decision='NO_REAL_DIRECTION_CONCLUSION',implementation_source=SOURCE,actual_numeric_source=None,queue_closed=True,formal_admission_attempts=0,formal_runs=0,all_numeric_counts=book['charged'],actual_results=[dict(name=x['name'],parent_result=x['parent_result'],input_state=x['state'],historical_V26_eta9=[.9662055056183675,.9819684299899415][i],eta10=None,g10=None,new_direction_resolved=None,status='NOT_RUN') for i,x in enumerate(plan['states'])],reason='Final supervised auxiliary admission rejected all physical cores/SMT candidates; no repeat or formal launch after prerequisite resource Gate rejection',old_V27_remains_closed=True,original_size_qualification='NOT_QUALIFIED',neural_20percent_gain='NOT_DEMONSTRATED',new_official_physics=False)
write(ART/'minimum_result.json',minimum);write(REC/'failures_and_not_run_v28.json',minimum)
write(REC/'tests_v28.json',dict(status='LOCAL_FOCUSED_PASSED',tests_passed=100,pytest_seconds=5.28,scope=['test_task042_v28_cached_checker.py','test_task042_v27_return_direction.py','test_task042_v26_joint_direction.py','test_task042_v25_block_direction.py','test_task042_v26_inventory.py'],new_tests=33,old_tests=67,compileall='PASS',one_run_dat_validate='PASS',implementation_source=SOURCE,test_head_at_execution=REVIEW,source_committed_after_tests=True,delivered_numerical_implementation='restored to first 100-pass scope after removing unexecuted optional strengthening',second_auxiliary_tests='NOT_RUN_CPU_ADMISSION',worker_log=aux[0]['worker_log'],live_factor_action_or_QR_tests='NOT_RUN',CI='NOT_RUN',full_repository_pytest='NOT_RUN',Ruff='not installed',old_cross_task_registry_failures='unchanged; no all-green claim'))
files=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r',SOURCE],text=True).splitlines()
write(REC/'source_inventory_v28.json',dict(implementation_source=SOURCE,actual_numeric_source=None,initial_HEAD=REVIEW,base='ccd357885f7f9be84efe3be07868cc94f13d93fc',branch='task42_neural_coarse_inverse',common_git_directory='/home/fenics/Projects/Maxwell3D-Lab/task-repository.git',source_files=[ref(ROOT/p) for p in files],pure_activation=ref(ROOT/'scripts/activate_task042.sh'),input=ref(ROOT/'input/task042_neural_coarse_inverse/v28_return_direction_diagnostic.dat'),pre_registration=ref(ROOT/'input/task042_neural_coarse_inverse/return_block_direction_v28.json')))
write(REC/'run_index_v28.json',dict(record_generator=ref(Path(__file__)),status=minimum['status'],review_commit=REVIEW,implementation_source=SOURCE,actual_numeric_source=None,formal_runs=[],auxiliary_runs=aux,admission_observations=observations,raw_redirected_stdio=raw_logs,window=ref(TMP/'window.json'),closed_ledger=ref(TMP/'ledger.json'),journal=ref(TMP/'progress_journal.jsonl'),V27_closed_ledger=ref(oldbook),minimum_result=ref(ART/'minimum_result.json'),minimum_cost=ref(ART/'minimum_cost.json'),input_inventory=ref(REC/'input_inventory_v28.json'),checker_result=ref(REC/'return_direction_checker_v28.json'),parent_nulls_corrected_only_in_new_records=True,no_subagents=True,no_reset_card=True,no_other_branch_modified=True))
print(json.dumps(dict(new_auxiliary_seconds=newwall,cumulative_seconds=carry+newwall,RSS=rss,observations=[dict(status=x['status'],candidate_cpus=x['candidate_cpus'],probe_seconds=x['observed_probe_seconds']) for x in observations],storage=cost['storage_at_observation']),ensure_ascii=False))
