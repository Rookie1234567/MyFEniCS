"""Separate metadata-only original AUTO inventory under the existing supervisor."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,sys,time,traceback
ROOT=pathlib.Path('/workspace/scratch/9c465670b46b/task40extra_cloud/repo');assert pathlib.Path.cwd().resolve()==ROOT
sys.path.insert(0,str(ROOT))
from benchmarks.run_real_p4_probe import source_facts,environment_facts
from benchmarks.subreaper_watchdog import memory_envelope,supervise
from src.solvers.real_p4_probe import file_sha256
HEAD='6dba8257053c6b2e474b7808b708a745f202733b';STAGE=pathlib.Path(__file__).parent
RUN=ROOT/'benchmarks/artifacts/task40extra_dot_parallel_cloud/target_AUTO_ordered_inventory_attempt1'
PY='../complex_env_recovery/bin/python';CAP=3<<30;RESERVE=128<<20;WALL=60
CORE=ROOT/'src/solvers/target_auto_surface_cost.py';CORE_SHA='748e925d42b0da1e27240b10d47bf586173ced8ee44a93cd78ea4368a6dbae24'
p=argparse.ArgumentParser();p.add_argument('--preflight',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--child',action='store_true');a=p.parse_args();assert a.preflight!=a.run
source=source_facts(HEAD);environment=environment_facts();script_sha=file_sha256(pathlib.Path(__file__));assert file_sha256(CORE)==CORE_SHA
parent=int(os.environ.get('PHYSICAL_WATCHDOG_PARENT_PID','0'))
if a.child:assert a.run and parent==os.getppid() and int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])==CAP
else:assert not RUN.exists()
def gate(label,facts):
    # Capsule total counts its explicitly declared predicted arrays/workspace.
    # Reference requested/live fields are not used in this metadata-only stage.
    assert 'predicted_total_bytes' in facts and int(facts['predicted_total_bytes'])>=0
    rss=0
    if a.child:
        from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
        q=process_tree_snapshot(parent,label,None,pss_sampling_policy='disabled_by_profile')
        assert q['all_status_readable'] and q['identity_complete'] and q['swap_bytes']==0
        rss=int(q['rss_bytes'])
    if rss+int(facts['predicted_total_bytes'])+RESERVE>=CAP:raise MemoryError('metadata RSS + predicted new arrays/workspace exceeds3GiB reserve policy')
    if a.child:event({'stage':'allocation_admitted','label':label,**facts,'measured_tree_RSS_bytes':rss})
def event(record):
    if a.child:
        with (RUN/'events.jsonl').open('a') as stream:stream.write(json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
if not a.child:
    envelope=memory_envelope();assert envelope['launch_cap_bytes']>=CAP+RESERVE and shutil.disk_usage(ROOT).free>=2<<30
    child=subprocess.run([PY,'-c','import json; from benchmarks.run_real_p4_probe import environment_facts; print("ENV="+json.dumps(environment_facts()))'],cwd=ROOT,text=True,capture_output=True)
    rows=[x for x in child.stdout.splitlines() if x.startswith('ENV=')];assert child.returncode==0 and len(rows)==1 and json.loads(rows[0][4:])==environment
    pre={'status':'SOURCE_ABI_METADATA_RESOURCE_PREFLIGHT_PASS','source':source,'environment':environment,'script_sha256':script_sha,'core_sha256':CORE_SHA,'memory_envelope':envelope,'stage':'metadata_only','mesh_form_JIT_factor_PDE_calls':0,'surface_launch_allowed':False}
    (STAGE/'inventory_preflight.json').write_text(json.dumps(pre,indent=2)+'\n')
    if a.preflight:print(json.dumps({'status':pre['status'],'launch_cap_bytes':envelope['launch_cap_bytes']}));raise SystemExit(0)
    summary=supervise([PY,str(pathlib.Path(__file__)),'--run','--child'],RUN,wall_seconds=WALL,interval=.25,grace_seconds=2,source_state=source,phase_path=RUN/'phase.json',tree_cap_bytes=CAP,hard_stop_immediate=True,timebase_guard=True,stop_on_global_swap=True,pss_sampling_policy='disabled_by_profile')
    assert source_facts(HEAD)==source and environment_facts()==environment and file_sha256(pathlib.Path(__file__))==script_sha and file_sha256(CORE)==CORE_SHA
    good=summary['classification']=='COMPLETED' and summary['leader_exit_code']==0 and summary['sampled_process_tree_swap_peak_bytes']==0 and summary['descendants_cleared'] and summary['process_tree_all_status_readable'] and summary['process_tree_all_identity_complete'] and 0<summary['sampled_process_tree_rss_peak_bytes']<CAP and 0<=summary['elapsed_seconds']<=WALL
    if (RUN/'metadata_result.json').exists():
        result=json.loads((RUN/'metadata_result.json').read_text());good=good and result['passed'];result['resource_and_source_pass']=bool(good);result['watchdog_receipt']={'path':'summary.json','sha256':file_sha256(RUN/'summary.json')};(RUN/'metadata_result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    else:good=False
    print(json.dumps({'classification':summary['classification'],'pass':bool(good),'seconds':summary['elapsed_seconds'],'RSS':summary['sampled_process_tree_rss_peak_bytes']}));raise SystemExit(0 if good else 2)
from src.solvers.target_auto_surface_cost import build_metadata_packet
try:
    m=build_metadata_packet(repo_root=ROOT,output_dir=RUN/'metadata',allocation_gate=gate,event=event)
    result={'passed':True,'status':m['packet']['status'],'metadata_packet':m['metadata_packet'],'source':source,'environment':environment,'scope':'full ordered original AUTO inventory only; no mesh/form/JIT/carrier/factor/PDE/output qualification'}
except BaseException as error:
    result={'passed':False,'error_type':type(error).__name__,'error':str(error),'source':source,'environment':environment};traceback.print_exc()
(RUN/'metadata_result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');raise SystemExit(0 if result['passed'] else 2)
