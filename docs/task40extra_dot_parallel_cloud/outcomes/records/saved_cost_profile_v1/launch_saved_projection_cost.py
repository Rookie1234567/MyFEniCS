"""One supervised saved-only representative cost profile; no FE/JIT/factors/PDE."""
import argparse,hashlib,json,pathlib,shutil,subprocess,sys,time,traceback,os
ROOT=pathlib.Path('/workspace/scratch/9c465670b46b/task40extra_cloud/repo')
assert pathlib.Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT))
from benchmarks.run_real_p4_probe import source_facts,environment_facts
from benchmarks.subreaper_watchdog import memory_envelope,supervise
from src.solvers.real_p4_probe import file_sha256
HEAD='c81e286bdf5cf9c78620854df2fb814cbf41e67a';BASE='17c0a656b44ed5b47351f6c2504579c8b3100f63'
OLD_SHA='ac7f73b51ce67e7a0655ab71af1136c56d70f86ca1c4e42a1634782b0672f925'
NEW_SHA='02a11ce42b8a075d0aa4508c659d5327110be37be6ce74dad9259f58ff11e0e0'
CHANGED='src/solvers/bounded_compact_q_projection.py'
ADDED={'src/test/test_exact_tile_support.py','src/solvers/fresh_projection_support_replay.py','src/test/test_fresh_projection_support_replay.py'}
STAGE=pathlib.Path(__file__).parent;RELATIVE_PYTHON='../complex_env_recovery/bin/python'
SAVED=ROOT/'benchmarks/artifacts/task40extra_dot_parallel_cloud/fresh_C1c_paired_allq_inverse_attempt1_20261004T17'
RUN=ROOT/'benchmarks/artifacts/task40extra_dot_parallel_cloud/saved_projection_cost_profile_attempt1'
CAP=3<<30;WALL=60;RESERVE=128<<20
REPORT_SHA='9fd8e2592382320f595807c17276b6f662193461ee64e0b105bd32df87dfe47d'
CHECKER_SHA='72e0428a0d8c78a7a55adc3199a2b2ab01cd00969a262f3e2c4ee717ed67b599'
WORKER_LIB_SHA='a63fd2e13c0f04db94ffb73847a85cc0de082025a5234b4f71122fcb108a5d9e'
CHECKER_LIB_SHA='b84c8f4bf7b88a717892502c29dd5f0dae70e6982e19bd31ae8efab7e9c7fa6a'
parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');parser.add_argument('--run',action='store_true');parser.add_argument('--child',action='store_true');args=parser.parse_args()
assert args.preflight != args.run
source=source_facts(HEAD);environment=environment_facts();script_sha=file_sha256(pathlib.Path(__file__))
parent=int(os.environ.get('PHYSICAL_WATCHDOG_PARENT_PID','0'))
if args.child:assert args.run and parent==os.getppid() and int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])==CAP

def gate(name,facts):
    rss=0
    if args.child:
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        sample=process_tree_snapshot(parent,name,None,pss_sampling_policy='disabled_by_profile')
        assert sample['all_status_readable'] and sample['identity_complete'] and sample['swap_bytes']==0
        rss=int(sample['rss_bytes'])
    payload=int(facts.get('matrix_payload_bytes',0));workspace=int(facts.get('workspace_bytes',0))
    if min(payload,workspace)<0 or rss+payload+workspace+RESERVE>=CAP:raise MemoryError('actual RSS plus declared new workspace exceeds3GiB reserve policy')

def bound_json(path,sha):
    assert file_sha256(path)==sha
    gate('bound_metadata_before_parse',{'workspace_bytes':6*path.stat().st_size+(1<<20)})
    return json.loads(path.read_text())
report=bound_json(SAVED/'probe_report.json',REPORT_SHA)
checked=bound_json(SAVED/'independent_checker.json',CHECKER_SHA)
assert report['source']['head']==BASE and report['status']=='FRESH_PAIRED_COMPACT_FULL3D_INVERSE_PASS'
assert checked['source']==report['source'] and checked['gate_pass'] and checked['evidence_valid'] and len(checked['checks'])==399 and all(x['passed'] for x in checked['checks'])
assert report['environment']==checked['environment']==environment
sector=report['raw_sector_receipts'][0]['sector_original_indices']
assert report['global_mode_keys'][sector[2]]==['top',-9,0,'s'] and all(report['global_mode_keys'][i][2]%4!=0 for i in sector[:2])
before,after=report['source']['files_sha256'],source['files_sha256']
assert before[CHANGED]==OLD_SHA and after[CHANGED]==NEW_SHA
assert {n for n,h in before.items() if after.get(n)!=h}=={CHANGED}
assert set(after)-set(before)==ADDED
assert source['branch']==report['source']['branch']=='task40extra_dot_parallel_cloud' and source['dirty']==report['source']['dirty']==''
for summary_path,sha,head,limit in ((SAVED/checked['worker_watchdog_receipt']['path'],checked['worker_watchdog_receipt']['sha256'],BASE,4500),(SAVED/checked['checker_watchdog_receipt']['path'],checked['checker_watchdog_receipt']['sha256'],BASE,4500)):
    summary=bound_json(summary_path,sha)
    assert summary['classification']=='COMPLETED' and summary['leader_exit_code']==0 and summary['source_state']==report['source']
    assert summary['descendants_cleared'] and summary['process_tree_all_status_readable'] and summary['process_tree_all_identity_complete']
    assert summary['sampled_process_tree_swap_peak_bytes']==0 and 0<summary['sampled_process_tree_rss_peak_bytes']<CAP and 0<=summary['elapsed_seconds']<=limit
worker_lib=bound_json(STAGE.parent/'paired_live_candidate/terminal_packet/library_full_roundtrip_receipt.json',WORKER_LIB_SHA)
checker_lib=bound_json(STAGE.parent/'paired_live_candidate/final_checker_packet/library_roundtrip_receipt.json',CHECKER_LIB_SHA)
assert worker_lib['status']=='LIBRARY_PAIRED_WORKER_PACKET_FULL_ROUNDTRIP_PASS' and worker_lib['metadata']['source_head']==BASE and worker_lib['NPYs_shape_dtype_numeric_hash_verified']==4199 and worker_lib['parts_verified']==6
assert checker_lib['status']=='FRESH_LIBRARY_READBACK_ALL_HASHES_PASS' and checker_lib['library_file_id']=='libfile_6cc685d92a688191944d130638f0df20'
assert checker_lib['metadata']['checker_sha256']==CHECKER_SHA and checker_lib['metadata']['worker_report_sha256']==REPORT_SHA
assert not RUN.exists() if not args.child else RUN.exists()
from src.solvers.fresh_projection_support_replay import load_verified_accumulator,BASELINE_GIT_BLOB,SCOPE
baseline_bytes=subprocess.check_output(['git','cat-file','blob',BASELINE_GIT_BLOB],cwd=ROOT)
old_class=load_verified_accumulator(baseline_bytes,expected_sha256=OLD_SHA,git_blob=BASELINE_GIT_BLOB)
new_class=load_verified_accumulator((ROOT/CHANGED).read_bytes(),expected_sha256=NEW_SHA)
CORE=STAGE/'profile_fresh_projection_cost.py'
CORE_SHA='29aa4c36502d70f84b423468dad74c372793363ae3ee51d01672428dc4b47e85'
assert file_sha256(CORE)==CORE_SHA
metadata={'scope':SCOPE,'source_git_head':HEAD,'candidate_source_sha256':NEW_SHA,'worker_report_sha256':REPORT_SHA,'independent_checker_sha256':CHECKER_SHA}
if not args.child:
    envelope=memory_envelope();assert envelope['launch_cap_bytes']>=CAP+RESERVE and shutil.disk_usage(ROOT).free>=2<<30
    child=subprocess.run([RELATIVE_PYTHON,'-c','import json; from benchmarks.run_real_p4_probe import environment_facts; print("ENV="+json.dumps(environment_facts()))'],cwd=ROOT,text=True,capture_output=True)
    rows=[x for x in child.stdout.splitlines() if x.startswith('ENV=')];assert child.returncode==0 and len(rows)==1 and json.loads(rows[0][4:])==environment
    pre={'source':source,'environment':environment,'script_sha256':script_sha,'saved_report_sha256':REPORT_SHA,'saved_checker_sha256':CHECKER_SHA,'changed_source':{'path':CHANGED,'old':OLD_SHA,'new':NEW_SHA},'added_files':sorted(ADDED),'Library_receipt_hashes':[WORKER_LIB_SHA,CHECKER_LIB_SHA],'memory_envelope':envelope,'scope':SCOPE,'status':'SOURCE_ABI_LIBRARY_AND_RESOURCE_PREFLIGHT_PASS','FE_JIT_factor_PDE':False,'profile_core_sha256':CORE_SHA,'wall_seconds':WALL,'optimization_qualification_claim':False}
    (STAGE/'preflight.json').write_text(json.dumps(pre,indent=2)+'\n')
    if args.preflight:print(json.dumps({'status':pre['status'],'launch_cap_bytes':envelope['launch_cap_bytes']}));raise SystemExit(0)
    summary=supervise([RELATIVE_PYTHON,str(pathlib.Path(__file__)),'--run','--child'],RUN,wall_seconds=WALL,interval=.25,grace_seconds=2,source_state=source,phase_path=RUN/'phase.json',tree_cap_bytes=CAP,hard_stop_immediate=True,timebase_guard=True,stop_on_global_swap=True,pss_sampling_policy='disabled_by_profile')
    assert source_facts(HEAD)==source and environment_facts()==environment and file_sha256(pathlib.Path(__file__))==script_sha and file_sha256(CORE)==CORE_SHA
    good=(summary['classification']=='COMPLETED' and summary['leader_exit_code']==0 and summary['sampled_process_tree_swap_peak_bytes']==0 and summary['descendants_cleared'] and summary['process_tree_all_status_readable'] and summary['process_tree_all_identity_complete'] and 0<summary['sampled_process_tree_rss_peak_bytes']<CAP and 0<=summary['elapsed_seconds']<=WALL)
    if (RUN/'profile_report.json').exists():
        result=json.loads((RUN/'profile_report.json').read_text());good=good and result.get('passed') is True
        result['watchdog_receipt']={'path':'summary.json','sha256':file_sha256(RUN/'summary.json')};result['resource_and_source_pass']=bool(good)
        (RUN/'profile_report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'classification':summary['classification'],'pass':bool(good),'seconds':summary['elapsed_seconds'],'RSS':summary['sampled_process_tree_rss_peak_bytes']}));raise SystemExit(0 if good else 2)
from src.solvers.fresh_paired_compact_checker import _Candidate
CORE=STAGE/'profile_fresh_projection_cost.py'
assert file_sha256(CORE)==CORE_SHA
sys.path.insert(0,str(STAGE))
from profile_fresh_projection_cost import profile_saved_projection_cost
read=_Candidate(SAVED,report,gate)
def event(record,encoded):
    with (RUN/'events.jsonl').open('ab') as f:f.write(encoded)
try:
    measured=profile_saved_projection_cost(report,accumulator_class=new_class,load_array=read.load,allocation_gate=gate,event=event,source_metadata=metadata,verify_if_wall_below_seconds=0)
    assert measured['integrity_passed'] and measured['status']=='SINGLE_RECIPE_COST_DIAGNOSTICS_COMPLETE' and len(measured['cases'])==4
    result={'passed':True,'status':'REPRESENTATIVE_COST_DIAGNOSTIC_COMPLETED','source':source,'environment':environment,'source_metadata':metadata,'profile':measured,'optimization_qualified':False,'no_target_scale_claim':True}
except BaseException as exc:
    result={'passed':False,'error_type':type(exc).__name__,'error':str(exc),'source':source,'environment':environment};traceback.print_exc()
(RUN/'profile_report.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');raise SystemExit(0 if result['passed'] else 2)
