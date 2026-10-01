"""Finite P8/P8/L8/L8 then paired eight-boundary extension schedule."""
import json
from src.io import post_lsqr_polish as io
from src.solvers import post_lsqr_window as window
from src.runners.task042_shared import write_json


def configure(driver):
    driver.CURRENT_BATCH='v19';driver.TMP_ROOT=io.ROOT/'tmp/task042/v19'
    driver.ARTIFACT_ROOT=io.ARTIFACT_ROOT;driver.read_result=io.read_result
    for name in ('ledger','LEDGER_PATH','journal','snapshot','freeze_route_budget'):setattr(driver,name,getattr(window,name))


def last(stage):
    path=io.ARTIFACT_ROOT/stage/'last_cycle.json'
    return json.loads(path.read_text()) if path.exists() else None


def completed(family):
    return any((io.ARTIFACT_ROOT/('FIRST_PASS_'+a+'_'+family+'.json')).exists() for a in ('P','L'))


def solve_queue(driver):
    pre,_=io.read_result('PREFLIGHT');budget=window.freeze_route_budget()
    for target in range(8,65,8):
        for algorithm in ('P','L'):
            for family in ('GPOLY','GNN'):
                stage=algorithm+'_'+family;terminal=io.ARTIFACT_ROOT/(stage+'_terminal.json')
                if not pre['libraries'].get(family,{}).get('qualified') or completed(family) or terminal.exists():continue
                saved=last(stage)
                if saved and saved['cycle']>=target:continue
                if algorithm=='L':
                    p8=io.ARTIFACT_ROOT/('P_'+family)/'cycles/CYCLE_0008/commit.json'
                    if not p8.exists():
                        window.journal('stage_not_run',stage=stage,reason='P first8 incomplete');continue
                if target>8:
                    first=io.ARTIFACT_ROOT/stage/('cycles/CYCLE_'+str(target-16).zfill(4)+'/commit.json')
                    start=pre['libraries'][family]['original_equation_gate']['rho'] if target==16 else json.loads(first.read_text())['original_equation_gate']['rho'] if first.exists() else None
                    if not saved or saved['cycle']!=target-8 or start is None or 1-saved['original_equation_gate']['rho']/start<.05:
                        write_json(terminal,dict(status='SLOW_PROGRESS_BELOW_EXTENSION_RULE',target=target));continue
                quota=window.ledger()['routes'][stage]
                if quota['wall_seconds']>=budget['uniform_route_wall_seconds']-60 or quota['actions_upper']+320>19500:
                    write_json(terminal,dict(status='ROUTE_QUOTA_BOUNDARY',target=target));continue
                if window.snapshot()['heavy_remaining_seconds']<600:return 0
                result=driver.launch_with_reentry(stage,target,stage.lower()+'_'+str(target),family=family)
                window.journal('paired_path_result',stage=stage,target=target,status=result['status'])
                if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','RESOURCE_NON_PSI_BLOCKED'):return 0
                if result['status'] in ('RUN_FAILED','ADMISSION_BLOCKED'):
                    write_json(driver.TMP_ROOT/'queue_failure.json',dict(stage=stage,result=result,window=window.snapshot()))
                    return 1
                if result['status'] not in ('SLICE_COMPLETE','ORIGINAL_EQUATION_PASS'):
                    write_json(terminal,dict(status=result['status'],target=target))
    return 0


def freeze_queue():
    row=window.ledger()
    if row.get('active'):raise ValueError('active V19 worker cannot freeze')
    plan=json.loads(io.PLAN_PATH.read_text());inventory=[];selection={}
    for family in ('GPOLY','GNN'):
        inventory.append(dict(plan['initial_states'][family],name='V18-R-'+family,legacy=True))
        candidates=[]
        for algorithm in ('P','L'):
            stage=algorithm+'_'+family;item=last(stage)
            if item:inventory.append(dict(item,name=stage+'-FINAL'));candidates.append((stage,item))
            first=io.ARTIFACT_ROOT/('FIRST_PASS_'+stage+'.json')
            if first.exists():
                item=json.loads(first.read_text());inventory.append(dict(item,name=stage+'-FIRST-PASS'));candidates.append((stage,item))
        p8=io.ARTIFACT_ROOT/('P_'+family)/'cycles/CYCLE_0008/commit.json'
        if p8.exists():inventory.append(dict(json.loads(p8.read_text()),name='P_'+family+'-CYCLE8'))
        if candidates:
            stage,item=min(candidates,key=lambda pair:pair[1]['original_equation_gate']['rho'])
            selection[family]=dict(stage=stage,state=item['state'],rho=item['original_equation_gate']['rho'],rule='lowest original rho among complete endpoints/first pass; no reference')
    unique=[];seen=set()
    for item in inventory:
        if item['state']['z_sha256'] not in seen:seen.add(item['state']['z_sha256']);unique.append(item)
    if len(unique)>12:raise ValueError('V19 frozen state limit')
    row['closed']=True;write_json(window.LEDGER_PATH,row)
    write_json(io.ARTIFACT_ROOT/'FROZEN.json',dict(validation_inventory=unique,selection=selection,
        ledger_sha256=__import__('src.solvers.neural_fe_action_packet',fromlist=['file_hash']).file_hash(window.LEDGER_PATH),
        source_queue_frozen=True,reference_not_yet_read=True))
    window.journal('all_paths_frozen',inventory=[x['name'] for x in unique],selection=selection)


def main_queue(driver,args):
    if args.preflight:
        result=driver.run('PREFLIGHT',0,'preflight')
        window.journal('C0_complete',status=result['status'])
        return 0 if result['status']=='GMRES_PREFLIGHT_COMPLETE' and any(r['qualified'] for r in result['libraries'].values()) else 1
    if args.solve:return solve_queue(driver)
    if args.verify:
        if not (io.ARTIFACT_ROOT/'FROZEN.json').exists():freeze_queue()
        result=driver.run('VERIFY',0,'verify');window.journal('V19_verify_complete',status=result['status'])
        return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
    return 0
