"""Finite V22 dispatch: cold is independent of warm numerical success."""
import json,subprocess,time
from pathlib import Path
from src.io import p1_trace_galerkin as io
from src.solvers import p1_trace_window as w
from src.runners.task042_shared import write_json


def cool():
    # Reuse the original finite PSI policy, with this campaign's own ledger.
    from src.runners.task042_shared import pressure,audit
    row=w.ledger()
    if row['reentries']>=2 or row['cooldown_seconds']>=1200:return False
    begin=time.monotonic();stable=None;safe=False
    while time.monotonic()-begin<min(600,1200-row['cooldown_seconds']):
        if w.snapshot()['heavy_remaining_seconds']<600:break
        psi=pressure();elapsed=time.monotonic()-begin
        if elapsed>=120 and psi['full']['avg10']<.05:
            if stable is None:stable=time.monotonic()
            if time.monotonic()-stable>=60:
                try:write_json(w.TMP/f'reentry_{row["reentries"]}.json',audit(observed_activity=True));safe=True;break
                except RuntimeError as error:w.journal('reentry_admission_failed',reason=str(error));stable=None
        else:stable=None
        w.journal('bounded_cooldown',elapsed_seconds=elapsed,pressure=psi);time.sleep(5)
    row=w.ledger();row['cooldown_seconds']+=time.monotonic()-begin
    if safe:row['reentries']+=1
    write_json(w.LEDGER_PATH,row);w.journal('resource_reentry_decision',allowed=safe);return safe


def run(name):
    attempt=0
    while True:
        w.require_live(margin=30);original=io.ROOT/f'input/task042_neural_coarse_inverse/v22_{io.FILES[name]}.dat'
        path=original
        if attempt:
            path=w.TMP/f'v22_{name.lower()}_retry{attempt}.dat'
            if path.exists():raise ValueError('consumed retry input')
            path.write_text(original.read_text().replace('run_id = "task042_v22_'+io.FILES[name]+'"',f'run_id = "task042_v22_{io.FILES[name]}_retry{attempt}"'))
        before=len(w.ledger()['runs']);w.journal('stage_dispatch',stage=name,input_path=str(path))
        mode='fe' if name in ('SETUP','VERIFY') else 'pure'
        code=subprocess.call(['bash','-c',f'set -e; export TASK042_CACHE_NAMESPACE=v22/{mode}; source scripts/activate_task042.sh {mode}; exec python scripts/run_case.py "$1"','task042-v22',str(path)])
        row=w.ledger()
        if len(row['runs'])==before:return dict(status='ADMISSION_BLOCKED',exit_code=code)
        item=row['runs'][-1]
        if item['classification']=='COMPLETED' and code==0:return io.read_result(name)[0]
        if item['classification']!='RESOURCE_CONTROLLED_STOP':return dict(status='RUN_FAILED',run=item)
        p=Path(item['directory'])/'supervision/resources.jsonl'
        with p.open('rb') as f:f.seek(max(0,p.stat().st_size-65536));tail=f.read().splitlines()[-8:]
        psi=any(json.loads(s).get('opt_in_health_check',{}).get('pressure_consecutive_samples',0)>=3 for s in tail)
        if not psi or item['swap_peak_bytes'] or item['rss_peak_bytes']>=16*2**30 or not cool():return dict(status='RESOURCE_ENVIRONMENT_BLOCKED',run=item)
        attempt+=1


def minimum_package():
    results={}
    for name in io.STAGES:
        try:r,_=io.read_result(name)
        except (OSError,ValueError):continue
        results[name]=dict(status=r['status'],source_sha=r['source_sha'],final=r.get('final'),
            stop_reason=r.get('stop_reason'),first_pass_cycle=r.get('first_pass_cycle'),PC_qualified=r.get('PC_qualified'),
            counts=r.get('aux_counts'),actions=r.get('all_incremental_equivalent_actions'))
    write_json(w.TMP/'minimum_result_package.json',dict(clock=w.snapshot(),results=results,ledger=w.ledger(),
        previous_formal_lower_bound_seconds=70970.59978457249,historical_auxiliary='unknown retained'))


def solve():
    if not (io.ARTIFACT_ROOT/'SETUP.json').exists():run('SETUP')
    setup,_=io.read_result('SETUP')
    if setup.get('warm',{}).get('qualified'):
        control=run('N');w.journal('route_end',stage='N',status=control['status'])
        if control['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    if not setup.get('PC_qualified'):
        w.journal('conditional_not_run',stages=['P','Z','T'],reason='fixed transfer/coarse/PC gate unqualified');return
    primary=run('P');w.journal('route_end',stage='P',status=primary['status'])
    if primary['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    # Cold first block requires S only, regardless of ordinary P negative result.
    cold=run('Z');w.journal('route_end',stage='Z',status=cold['status'])
    if cold['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    if 'final' in primary and (primary['first_pass_cycle'] is not None or primary['start']['original_equation_gate']['rho']/primary['final']['original_equation_gate']['rho']>=5):
        if w.snapshot()['heavy_remaining_seconds']>=1200:
            result=run('T');w.journal('route_end',stage='T',status=result['status'])
        else:w.journal('conditional_not_run',stage='T',reason='verification/delivery reserve')
    else:w.journal('conditional_not_run',stage='T',reason='P neither original equation pass nor fivefold reduction')


def freeze():
    if (io.ARTIFACT_ROOT/'FROZEN.json').exists():return
    plan=json.loads(io.PLAN_PATH.read_text());items=[dict(plan['initial_states']['GPOLY'],name='V21-C-FINAL',legacy=True)]
    for name in ('N','P','Z','T'):
        if not (io.ARTIFACT_ROOT/(name+'.json')).exists():continue
        result,_=io.read_result(name)
        if 'final' in result:items.append(dict(result['final'],name=name+'-FINAL'))
        p=io.ARTIFACT_ROOT/name/'FIRST_EQUATION_PASS.json'
        if p.exists():items.append(dict(json.loads(p.read_text()),name=name+'-FIRST_PASS'))
    unique={}
    for item in items:unique.setdefault(item['state']['z_sha256'],item)
    if not 1<=len(unique)<=12:raise ValueError('V22 frozen field capacity')
    row=w.ledger();row['closed']=True;write_json(w.LEDGER_PATH,row)
    write_json(io.ARTIFACT_ROOT/'FROZEN.json',dict(validation_inventory=list(unique.values()),source_queue_frozen=True,
        reference_not_yet_read=True,selection_uses_reference=False));w.journal('all_choices_frozen',states=len(unique))


def main_queue(args):
    try:
        if args.preflight:
            result=run('SETUP');return 0 if result['status']=='P1_TRACE_SETUP_COMPLETE' else 1
        if args.solve:solve()
        if args.verify:
            freeze();result=run('VERIFY');return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
        return 0
    finally:minimum_package()
