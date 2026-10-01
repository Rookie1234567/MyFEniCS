"""Finite foreground V17 milestone queue. No workstation-wide control."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from src.io.resumable_trace_campaign import ARTIFACT_ROOT,ROOT,read_result
from src.runners.task042_shared import write_json,pressure,audit
from src.solvers.resumable_trace_window import ledger,LEDGER_PATH,journal,snapshot,freeze_route_budget

TMP_ROOT=ROOT/'tmp/task042/v17'
CURRENT_BATCH='v17'


def dat(stage,target,label):
    directory=TMP_ROOT/'inputs';directory.mkdir(exist_ok=True)
    path=directory/(label+'.dat')
    if CURRENT_BATCH=='v18':
        from src.io.gmres_residual_completion import write_input
        return write_input(path,stage,target,'task042_v18_'+label)
    if path.exists():raise ValueError('one-run input already consumed '+str(path))
    path.write_text(f'''schema_version = 1
[task042_v17]
stage = "{stage}"
run_id = "task042_v17_{label}"
material_table_id = "SI_OPTICAL_CONSTANTS_USER_20260929_V1"
decoder_family = "RESUMABLE_FULL_TRACE_CAMPAIGN"
target_iteration = {target}
''')
    return path


def run(stage,target,label):
    label=label+'_run'+str(len(ledger()['runs']))
    path=dat(stage,target,label);mode='fe' if stage=='VERIFY' else 'pure'
    journal('one_run_dispatch',stage=stage,target=target,input_path=str(path))
    before=len(ledger()['runs'])
    p=subprocess.run(['bash','-c',f'set -e;source scripts/activate_task042.sh {mode};exec python scripts/run_case.py "$1"','task042-v17',str(path)])
    latest=ledger()['runs'][-1] if ledger()['runs'] else {}
    if len(ledger()['runs'])<=before or latest.get('stage')!=stage:
        return dict(status='ADMISSION_BLOCKED',exit_code=p.returncode)
    if latest['classification']=='COMPLETED' and p.returncode==0:
        result,_=read_result(stage);return result
    if latest['classification']=='RESOURCE_CONTROLLED_STOP':return dict(status='RESOURCE_STOP',run=latest)
    return dict(status='RUN_FAILED',run=latest,exit_code=p.returncode)


def cool(family):
    row=ledger()
    if row['reentries']>=3 or row['routes'][family]['reentries']>=2 or row['cooldown_seconds']>=1800:
        journal('resource_reentry_limit',library=family);return False
    begin=time.monotonic();stable=None;safe=False
    while time.monotonic()-begin<min(600,1800-row['cooldown_seconds']):
        elapsed=time.monotonic()-begin
        psi=pressure();good=psi['full']['avg10']<.05 and psi['some']['avg10']<1.
        if elapsed>=120 and good:
            if stable is None:stable=time.monotonic()
            if time.monotonic()-stable>=60:
                try:
                    baseline=audit(observed_activity=True)
                    write_json(TMP_ROOT/('reentry_'+str(row['reentries'])+'.json'),baseline)
                    safe=True;break
                except RuntimeError as error:journal('reentry_admission_failed',reason=str(error));stable=None
        else:stable=None
        journal('resource_cooldown_sample',library=family,wait_seconds=elapsed,memory_pressure=psi)
        time.sleep(min(5.,max(0.,snapshot()['heavy_remaining_seconds'])))
        if snapshot()['heavy_remaining_seconds']<=60:break
    waited=time.monotonic()-begin;row=ledger();row['cooldown_seconds']+=waited
    if safe:row['reentries']+=1;row['routes'][family]['reentries']+=1
    write_json(LEDGER_PATH,row);journal('resource_reentry_decision',library=family,wait_seconds=waited,allowed=safe)
    return safe


def set_status(family,status):
    row=ledger();row['routes'][family]['status']=status;write_json(LEDGER_PATH,row)
    journal('library_dispatch_status',library=family,status=status)


def launch_with_reentry(stage,target,label,*,family=None):
    family=family or stage.removeprefix('GMRES_');attempt=0
    while True:
        result=run(stage,target,label+'_a'+str(attempt))
        if result['status']!='RESOURCE_STOP':return result
        runrow=result['run']
        if runrow.get('swap_peak_bytes',0) or runrow.get('rss_peak_bytes',0)>=16*2**30:
            return dict(result,status='RESOURCE_NON_PSI_BLOCKED')
        summary=json.loads((Path(runrow['directory'])/'run_summary.json').read_text())
        health=summary.get('external_health',summary.get('health',{}))
        # Only the original PSI trigger can authorize automatic reentry.
        rows=[json.loads(s) for s in (Path(runrow['directory'])/'supervision/resources.jsonl').read_text().splitlines()[-8:]]
        psi_stop=any(r.get('opt_in_health_check',{}).get('pressure_consecutive_samples',0)>=3 for r in rows)
        if not psi_stop:
            journal('resource_stop_not_PSI_reentry_disallowed',library=family,health=health)
            return dict(result,status='RESOURCE_NON_PSI_BLOCKED')
        if not cool(family):return dict(result,status='RESOURCE_ENVIRONMENT_BLOCKED')
        attempt+=1


def solve_queue():
    pre,_=read_result('PREFLIGHT');budget=freeze_route_budget()
    if budget['uniform_route_wall_seconds']<900:
        journal('paired_queue_insufficient_window');return
    for family in ('GPOLY','GNN'):
        if not pre['libraries'].get(family,{}).get('qualified'):set_status(family,'LIBRARY_INTERFACE_BLOCKED')
    for target in (512,1024,2048,2560,3072,3584,4096,4608,5120,5632,6144,6656,7168,7680,8192):
        for family in ('GPOLY','GNN'):
            row=ledger()['routes'][family]
            if row['status'] not in ('READY','SLICE_COMPLETE'):continue
            latest=ARTIFACT_ROOT/family/'last_audit.json'
            if latest.exists():
                saved=json.loads(latest.read_text())
                if saved['original_equation_gate']['status']=='ORIGINAL_EQUATION_PASS':
                    set_status(family,'ORIGINAL_EQUATION_PASS');continue
                if saved['logical_iteration']>=target:
                    journal('completed_milestone_reused_no_replay',library=family,target=target);continue
            if snapshot()['heavy_remaining_seconds']<600:set_status(family,'TOTAL_WINDOW_STOP');continue
            if row['wall_seconds']>=budget['uniform_route_wall_seconds']-budget['GMRES_reserved_seconds']-60:
                set_status(family,'LSQR_RESERVED_G_BOUNDARY');continue
            if target>4096:
                history_path=ARTIFACT_ROOT/family/'audit_history.jsonl'
                unique={r['logical_iteration']:r for r in map(json.loads,history_path.read_text().splitlines()) if not r['audit_pending']}
                end=target-512;start=end-512
                drop=1-unique[end]['original_equation_gate']['rho']/unique[start]['original_equation_gate']['rho'] if end in unique and start in unique else 0
                if drop<.1 or budget['uniform_route_wall_seconds']-row['wall_seconds']<600:
                    set_status(family,'LSQR_EXTENSION_PROGRESS_STOP');continue
            result=launch_with_reentry(family,target,family.lower()+'_'+str(target))
            set_status(family,result['status'])
            if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','RESOURCE_NON_PSI_BLOCKED'):
                # System pressure/hard stop cannot be bypassed by another heavy.
                return
    for family in ('GPOLY','GNN'):
        row=ledger()['routes'][family];status=row['status']
        if status not in ('LSQR_STAGNATION','BREAKDOWN_NOT_SOLVED','LSQR_EXTENSION_PROGRESS_STOP','SLICE_COMPLETE','LSQR_RESERVED_G_BOUNDARY','NEW_GK_BUDGET_STOP'):
            journal('GMRES_not_run',library=family,reason=status);continue
        if row['wall_seconds']>=budget['uniform_route_wall_seconds']-60 or snapshot()['heavy_remaining_seconds']<600:
            journal('GMRES_not_run',library=family,reason='time_reserve_exhausted');continue
        result=launch_with_reentry('GMRES_'+family,0,'gmres_'+family.lower());set_status(family,result['status'])
        if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','RESOURCE_NON_PSI_BLOCKED'):return


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preflight',action='store_true');parser.add_argument('--solve',action='store_true');parser.add_argument('--verify',action='store_true')
    parser.add_argument('--batch',choices=('v17','v18'),default='v17')
    args=parser.parse_args()
    if args.batch=='v18':
        from src.runners.residual_completion_queue import configure,main_queue
        configure(sys.modules[__name__])
        return main_queue(sys.modules[__name__],args)
    if args.preflight:
        result=run('PREFLIGHT',0,'preflight');journal('R1_complete',status=result['status'])
        return 0 if result['status']=='RESUME_QUALIFICATION_COMPLETE' else 1
    if args.solve:solve_queue()
    if args.verify:
        row=ledger();row['closed']=True;write_json(LEDGER_PATH,row)
        write_json(ARTIFACT_ROOT/'FROZEN.json',dict(ledger=row,source_queue_frozen=True,reference_not_yet_read=True))
        result=run('VERIFY',0,'verify');journal('V17_verify_complete',status=result['status'])
        return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
    return 0


if __name__=='__main__':raise SystemExit(main())
