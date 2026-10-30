"""Explicit forward allocation gate; estimates remain estimates, not measured peaks."""
import datetime,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from process_observation_v1 import proc_facts,group_facts,system_facts

def admit(stage,future_bytes,*,margin_bytes=536870912,estimate_basis):
    if type(stage) is not str or not stage or type(future_bytes) is not int or future_bytes<0 or type(margin_bytes) is not int or margin_bytes<536870912 or not estimate_basis:
        raise ValueError('explicit stage, nonnegative future allocation, >=512MiB margin and basis required')
    cap=int(os.environ['TASK44_TREE_CAP_BYTES']);floor=int(os.environ['TASK44_AVAILABLE_FLOOR_BYTES']);log=Path(os.environ['TASK44_STAGE_LOG'])
    members,errors=group_facts(os.getpgrp(),{})
    parent=proc_facts(int(os.environ['TASK44_SUPERVISOR_PID']))
    if parent['start_ticks']!=int(os.environ['TASK44_SUPERVISOR_START_TICKS']):raise RuntimeError('SUPERVISOR_IDENTITY_CHANGED')
    live=sum(x['rss'] for x in members)+(0 if any(x['pid']==parent['pid'] for x in members) else parent['rss'])
    system=system_facts(log.parent)
    facts={'stage':stage,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'live_tree_and_supervisor_bytes':live,'future_bytes':future_bytes,'margin_bytes':margin_bytes,'estimate_basis':estimate_basis,'effective_cap_bytes':cap,'system':system,'unreadable':errors,'task_swap_bytes':sum(x['swap'] for x in members)+parent['swap']}
    passed=not errors and facts['task_swap_bytes']==0 and system['swap_used']==0 and live+future_bytes+margin_bytes<=min(cap,10000000000) and system['available']>=floor+future_bytes+margin_bytes
    facts['passed']=passed
    with log.open('a') as f:f.write(json.dumps(facts,sort_keys=True,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())
    if not passed:raise RuntimeError('TASK44_STAGE_RESOURCE_ADMISSION_FAILED:'+stage)
    return facts
