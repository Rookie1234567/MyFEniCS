"""Finite V21 queue; independent actors, bounded PSI reentry and early closeout."""
import json
import subprocess
import time
from pathlib import Path
from src.io import exact_action_recycling as io
from src.solvers import exact_recycle_window as w
from src.runners.task042_shared import write_json,pressure,audit


def cool():
    row=w.ledger()
    if row['reentries']>=2 or row['cooldown_seconds']>=1200:return False
    begin=time.monotonic();stable=None;safe=False
    while time.monotonic()-begin<min(600,1200-row['cooldown_seconds']):
        if w.snapshot()['heavy_remaining_seconds']<600:break
        psi=pressure();elapsed=time.monotonic()-begin
        if elapsed>=120 and psi['full']['avg10']<.05:
            if stable is None:stable=time.monotonic()
            if time.monotonic()-stable>=60:
                try:
                    baseline=audit(observed_activity=True);write_json(w.TMP/f'reentry_{row["reentries"]}.json',baseline)
                    safe=True;break
                except RuntimeError as error:w.journal('reentry_admission_failed',reason=str(error));stable=None
        else:stable=None
        w.journal('bounded_cooldown',elapsed_seconds=elapsed,pressure=psi);time.sleep(5)
    row=w.ledger();row['cooldown_seconds']+=time.monotonic()-begin
    if safe:row['reentries']+=1
    write_json(w.LEDGER_PATH,row);w.journal('resource_reentry_decision',allowed=safe)
    return safe


def run(name):
    attempt=0
    while True:
        w.require_live(heavy=True,margin=30)
        original=io.ROOT/f'input/task042_neural_coarse_inverse/v21_{io.FILES[name]}.dat'
        if attempt:
            path=w.TMP/f'v21_{name.lower()}_retry{attempt}.dat'
            if path.exists():raise ValueError('retry dat already consumed')
            path.write_text(original.read_text().replace('run_id = "task042_v21_'+io.FILES[name]+'"',
                f'run_id = "task042_v21_{io.FILES[name]}_retry{attempt}"'))
        else:path=original
        before=len(w.ledger()['runs']);w.journal('stage_dispatch',stage=name,input_path=str(path))
        mode='fe' if name=='VERIFY' else 'pure'
        code=subprocess.call(['bash','-c',f'set -e; export TASK042_CACHE_NAMESPACE=v21/{mode}; source scripts/activate_task042.sh {mode}; exec python scripts/run_case.py "$1"','task042-v21',str(path)])
        row=w.ledger()
        if len(row['runs'])==before:return dict(status='ADMISSION_BLOCKED',exit_code=code)
        item=row['runs'][-1]
        if item['classification']=='COMPLETED' and code==0:return io.read_result(name)[0]
        if item['classification']!='RESOURCE_CONTROLLED_STOP':return dict(status='RUN_FAILED',run=item)
        path=Path(item['directory'])/'supervision/resources.jsonl'
        with path.open('rb') as f:f.seek(max(0,path.stat().st_size-65536));tail=f.read().splitlines()[-8:]
        psi=any(json.loads(s).get('opt_in_health_check',{}).get('pressure_consecutive_samples',0)>=3 for s in tail)
        if not psi or item['swap_peak_bytes'] or item['rss_peak_bytes']>=16*2**30 or not cool():
            return dict(status='RESOURCE_ENVIRONMENT_BLOCKED',run=item)
        attempt+=1


def minimum_result_package():
    """Low-cost result/cost package produced at queue end, not last-minute prose."""
    row=w.ledger();results={}
    for name in io.STAGES:
        try:r,_=io.read_result(name)
        except (OSError,ValueError):continue
        results[name]=dict(status=r['status'],source_sha=r['source_sha'],
            final=r.get('final'),stop_reason=r.get('stop_reason'),first_pass_cycle=r.get('first_pass_cycle'),
            incremental_actions=r.get('all_incremental_equivalent_actions'),wall_seconds=r['worker_wall_seconds'])
    write_json(w.TMP/'minimum_result_package.json',dict(clock=w.snapshot(),results=results,ledger=row,
        formal_wall_seconds_lower_bound=sum(r['launch_wall_seconds'] for r in row['runs']),
        previous_formal_wall_lower_bound=67488.47412200551,history_auxiliary='unknown/lower-bound retained'))
    w.journal('minimum_result_cost_package_saved',stages=list(results))


def solve():
    if not (io.ARTIFACT_ROOT/'PREFLIGHT.json').exists():
        pre=run('PREFLIGHT')
        if pre['status']!='ACTION_QUALIFICATION_COMPLETE':
            w.journal('numerical_preflight_failed',status=pre['status']);return
    control=run('B');w.journal('route_end',stage='B',status=control['status'])
    if control['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    primary=run('C');w.journal('route_end',stage='C',status=primary['status'])
    if primary['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    if 'final' not in primary:
        w.journal('conditional_not_run',stages=['T','Z'],reason='primary numerical actor failed');return
    gain=primary['start']['original_equation_gate']['rho']/primary['final']['original_equation_gate']['rho']
    if primary['first_pass_cycle'] is not None or gain>=10:
        for name in ('T','Z'):
            if w.snapshot()['heavy_remaining_seconds']<1200:
                w.journal('conditional_not_run',stage=name,reason='global verification/delivery reserve');continue
            result=run(name);w.journal('route_end',stage=name,status=result['status'])
            if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    else:w.journal('conditional_not_run',stages=['T','Z'],reason='C not equation-qualified and original rho reduction less than tenfold',gain=gain)


def freeze():
    root=io.ARTIFACT_ROOT
    if (root/'FROZEN.json').exists():return
    plan=json.loads(io.PLAN_PATH.read_text());items=[dict(v,name='V19-'+v['name'],legacy=True) for v in plan['initial_states'].values()]
    for name in ('B','C','T','Z'):
        if not (root/(name+'.json')).exists():continue
        result,_=io.read_result(name)
        if 'final' in result:items.append(dict(result['final'],name=name+'-FINAL'))
        path=root/name/'FIRST_PASS.json'
        if path.exists():items.append(dict(json.loads(path.read_text()),name=name+'-FIRST_PASS'))
        if name in ('C','T'):
            path=root/name/'cycles'/'CALL_0032'/'compact_commit.json'
            if path.exists():items.append(dict(json.loads(path.read_text()),name=name+'-CALL32'))
    unique={}
    for item in items:unique.setdefault(item['state']['z_sha256'],item)
    if not 1<=len(unique)<=12:raise ValueError('V21 frozen field state inventory')
    row=w.ledger();row['closed']=True;write_json(w.LEDGER_PATH,row)
    write_json(root/'FROZEN.json',dict(validation_inventory=list(unique.values()),source_queue_frozen=True,
        reference_not_yet_read=True,selection_uses_reference=False))
    w.journal('all_solver_choices_frozen',states=list(unique))


def main_queue(args):
    try:
        if args.preflight:
            result=run('PREFLIGHT');w.journal('A_end',status=result['status'])
            return 0 if result['status']=='ACTION_QUALIFICATION_COMPLETE' else 1
        if args.solve:solve()
        if args.verify:
            freeze();result=run('VERIFY');w.journal('V21_verify_end',status=result['status'])
            return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
        return 0
    finally:minimum_result_package()
