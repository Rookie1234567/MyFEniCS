"""V18 finite paired schedule using the existing foreground one-run driver."""
import json
from pathlib import Path

from src.io import gmres_residual_completion as io
from src.solvers import residual_completion_window as window
from src.runners.task042_shared import write_json


def configure(driver):
    driver.CURRENT_BATCH='v18';driver.TMP_ROOT=io.ROOT/'tmp/task042/v18'
    driver.ARTIFACT_ROOT=io.ARTIFACT_ROOT;driver.read_result=io.read_result
    for name in ('ledger','LEDGER_PATH','journal','snapshot','freeze_route_budget'):setattr(driver,name,getattr(window,name))


def last_row(algorithm,family):
    path=io.ARTIFACT_ROOT/(family+'/last_audit.json' if algorithm=='R' else algorithm+'_'+family+'/last_cycle.json')
    return json.loads(path.read_text()) if path.exists() else None


def completed(family):return (io.ARTIFACT_ROOT/('FIRST_PASS_'+family+'.json')).exists()


def terminal(stage):
    path=io.ARTIFACT_ROOT/(stage+'_terminal.json')
    return json.loads(path.read_text()) if path.exists() else None


def execute(driver,stage,target,label,family):
    if window.snapshot()['heavy_remaining_seconds']<600:
        window.journal('stage_not_run',stage=stage,reason='immutable heavy margin');return dict(status='TOTAL_WINDOW_STOP')
    result=driver.launch_with_reentry(stage,target,label,family=family)
    window.journal('paired_path_result',stage=stage,target=target,status=result['status'])
    stops=('GMRES_TWO_CYCLE_INCREASE','GMRES_WALL_BOUNDARY','GMRES_ARNOLDI_BUDGET_STOP',
           'GMRES_NO_EXTENSION_PROGRESS','LSQR_STAGNATION','BREAKDOWN_NOT_SOLVED',
           'R_WALL_BOUNDARY','NEW_GK_BUDGET_STOP')
    if result['status'] in stops:
        write_json(io.ARTIFACT_ROOT/(stage+'_terminal.json'),dict(status=result['status'],target=target,window=window.snapshot()))
    if result['status'] in ('RUN_FAILED','ADMISSION_BLOCKED'):
        # Stop a possibly common broken interface before copying it to the
        # second library. Root can make an authorized bounded repair/resume.
        write_json(driver.TMP_ROOT/'queue_failure.json',dict(stage=stage,result=result,window=window.snapshot()))
        return dict(result,common_failure_pending_diagnosis=True)
    return result


def solve_queue(driver):
    pre,_=io.read_result('PREFLIGHT');budget=window.freeze_route_budget();blocked=set()
    for family in ('GPOLY','GNN'):
        if not pre['libraries'].get(family,{}).get('qualified'):
            blocked.add(family);window.journal('library_interface_blocked',library=family)
    for algorithm,targets in (('G64',(8,16)),('G256',(4,8))):
        basic=targets[0]
        for target in targets:
            for family in ('GPOLY','GNN'):
                if family in blocked or completed(family):continue
                if terminal(algorithm+'_'+family):continue
                saved=last_row(algorithm,family)
                if saved and saved['cycle']>=target:continue
                if algorithm=='G256' and last_row('G64',family) is None:
                    window.journal('stage_not_run',stage=algorithm+'_'+family,reason='G64 has no trustworthy cycle');continue
                if target>basic:
                    if saved is None or saved['cycle']<basic or 1-saved['original_equation_gate']['rho']/saved['start_rho']<.1:
                        window.journal('stage_not_run',stage=algorithm+'_'+family,target=target,reason='extension progress <10%');continue
                route=window.ledger()['routes'][family]
                if route['G_wall_seconds']>=budget['GMRES_total_ceiling_seconds']-60 or route['wall_seconds']>=budget['uniform_route_wall_seconds']-60:
                    window.journal('stage_not_run',stage=algorithm+'_'+family,reason='G/library wall exhausted');continue
                result=execute(driver,algorithm+'_'+family,target,algorithm.lower()+'_'+family.lower()+'_'+str(target),family)
                if result.get('common_failure_pending_diagnosis'):return 1
                if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','RESOURCE_NON_PSI_BLOCKED'):return 0
    for target in (7168,8192,9216,10240,11264,12288,13312,14336,15360,16384):
        for family in ('GPOLY','GNN'):
            if family in blocked or completed(family):continue
            if terminal('R_'+family):continue
            route=window.ledger()['routes'][family];saved=last_row('R',family)
            if saved and saved['logical_iteration']>=target:continue
            if route['wall_seconds']>=budget['uniform_route_wall_seconds']-60 or route['new_updates']>=10300:
                blocked.add(family);window.journal('R_library_budget_boundary',library=family);continue
            if target>8192:
                path=io.ARTIFACT_ROOT/family/'audit_history.jsonl'
                history={r['logical_iteration']:r for r in map(json.loads,path.read_text().splitlines()) if not r['audit_pending']} if path.exists() else {}
                end=target-1024;begin=end-1024
                if end not in history or begin not in history or 1-history[end]['original_equation_gate']['rho']/history[begin]['original_equation_gate']['rho']<.1:
                    blocked.add(family);window.journal('R_extension_progress_stop',library=family,target=target);continue
            result=execute(driver,'R_'+family,target,'r_'+family.lower()+'_'+str(target),family)
            if result.get('common_failure_pending_diagnosis'):return 1
            if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','RESOURCE_NON_PSI_BLOCKED'):return 0
            if result['status']!='SLICE_COMPLETE':blocked.add(family)
    return 0


def freeze_queue():
    row=window.ledger()
    if row.get('active'):raise ValueError('cannot freeze an active V18 worker')
    inventory=[];selection={};plan=json.loads(io.PLAN_PATH.read_text())
    for family in ('GPOLY','GNN'):
        initial=dict(plan['initial_states'][family],name='V17-'+family,legacy=True);inventory.append(initial)
        candidates=[]
        for algorithm in ('G64','G256','R'):
            item=last_row(algorithm,family)
            if item:inventory.append(dict(item,name=family+'-'+algorithm+'-FINAL',legacy=False));candidates.append((algorithm,item))
        first=io.ARTIFACT_ROOT/('FIRST_PASS_'+family+'.json')
        if first.exists():
            item=json.loads(first.read_text());inventory.append(dict(item,name=family+'-FIRST-PASS',legacy=False));candidates.append(('FIRST-PASS',item))
        if candidates:
            algorithm,item=min(candidates,key=lambda pair:pair[1]['original_equation_gate']['rho'])
            selection[family]=dict(algorithm=algorithm,state=item['state'],rho=item['original_equation_gate']['rho'],selection_rule='lowest original rho among frozen complete endpoints/first-pass; no REF7')
            inventory.append(dict(item,name=family+'-SELECTED',legacy=False))
    seen=set();unique=[]
    for item in inventory:
        if item['state']['z_sha256'] not in seen:seen.add(item['state']['z_sha256']);unique.append(item)
    if len(unique)>12:raise ValueError('V18 field-state cap exceeded')
    row['closed']=True;write_json(window.LEDGER_PATH,row)
    write_json(io.ARTIFACT_ROOT/'FROZEN.json',dict(ledger=row,validation_inventory=unique,selection=selection,source_queue_frozen=True,reference_not_yet_read=True))
    window.journal('all_paths_frozen',inventory=[i['name'] for i in unique],selection=selection)


def main_queue(driver,args):
    if args.preflight:
        result=driver.run('PREFLIGHT',0,'preflight');window.journal('F0_complete',status=result['status'])
        return 0 if result['status']=='GMRES_PREFLIGHT_COMPLETE' and any(r['qualified'] for r in result['libraries'].values()) else 1
    if args.solve:return solve_queue(driver)
    if args.verify:
        if not (io.ARTIFACT_ROOT/'FROZEN.json').exists():freeze_queue()
        result=driver.run('VERIFY',0,'verify');window.journal('V18_verify_complete',status=result['status'])
        return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
    return 0
