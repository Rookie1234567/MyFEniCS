"""Finite paired slices, independent starts, and a frozen-reference barrier."""
import json,subprocess
from pathlib import Path
from src.io import local_block_pair as io
from src.solvers import local_block_window as w
from src.runners.task042_shared import write_json
from src.runners.p1_trace_queue import cool
from src.solvers.neural_fe_action_packet import file_hash

ORDER=('LW','LCW','LZ','LCZ')


def run(name,target=4):
    attempt=0
    while True:
        w.require_live(margin=30)
        original=io.ROOT/f'input/task042_neural_coarse_inverse/v24_{io.FILES[name]}.dat';path=original
        if target!=4 and name not in ('SETUP','VERIFY') or attempt:
            path=w.TMP/f'v24_{name.lower()}_{target}_retry{attempt}.dat'
            if path.exists():raise ValueError('consumed slice input')
            text=original.read_text().replace('target_cycles = 4',f'target_cycles = {target}').replace(
                f'run_id = "task042_v24_{io.FILES[name]}"',f'run_id = "task042_v24_{io.FILES[name]}_{target}_retry{attempt}"')
            path.write_text(text)
        before=len(w.ledger()['runs']);w.journal('stage_dispatch',stage=name,target_cycles=target,input_path=str(path))
        mode='fe' if name=='VERIFY' else 'pure'
        code=subprocess.call(['bash','-c',f'set -e; export TASK042_CACHE_NAMESPACE=v24/{mode}; source scripts/activate_task042.sh {mode}; exec python scripts/run_case.py "$1"','task042-v24',str(path)])
        row=w.ledger()
        if len(row['runs'])==before:return dict(status='ADMISSION_BLOCKED',exit_code=code)
        item=row['runs'][-1]
        if item['classification']=='COMPLETED' and code==0:return io.read_result(name)[0]
        if item['classification']!='RESOURCE_CONTROLLED_STOP':return dict(status='RUN_FAILED',run=item)
        p=Path(item['directory'])/'supervision/resources.jsonl'
        with p.open('rb') as f:f.seek(max(0,p.stat().st_size-65536));tail=f.read().splitlines()[-8:]
        psi=any(json.loads(s).get('opt_in_health_check',{}).get('pressure_consecutive_samples',0)>=3 for s in tail)
        if not psi or item['swap_peak_bytes'] or item['rss_peak_bytes']>=16*2**30 or not cool(window_module=w):return dict(status='RESOURCE_ENVIRONMENT_BLOCKED',run=item)
        attempt+=1


def minimum_package():
    results={}
    for name in io.STAGES:
        try:r,p=io.read_result(name)
        except (OSError,ValueError):continue
        final=r.get('final',{})
        results[name]=dict(status=r['status'],source_sha=r['source_sha'],result_path=str(p),result_sha256=file_hash(p),
            final_state=final.get('state'),final_gate=final.get('original_equation_gate'),stop_reason=r.get('stop_reason'),
            first_pass_cycle=r.get('first_pass_cycle'),local_qualified=r.get('local_qualified'),composite_qualified=r.get('composite_qualified'),
            counts=r.get('aux_counts'),actions=r.get('all_incremental_equivalent_actions'))
    write_json(w.TMP/'minimum_result_package.json',dict(clock=w.snapshot(),results=results,ledger=w.ledger(),
        previous_formal_lower_bound_seconds=75124.91759302444,historical_auxiliary='unknown retained'))
    lines=['# V24 最小阶段回应','','原方程与全部物理审核决定资格；本记录不是通过声明。','']
    lines.extend(f"- {name}: {row['status']}; source={row['source_sha']}; {row['result_path']}" for name,row in results.items())
    p=w.TMP/'minimum_response.md';tmp=p.with_suffix('.partial');tmp.write_text('\n'.join(lines)+'\n');tmp.replace(p)


def solve():
    setup=run('SETUP') if not (io.ARTIFACT_ROOT/'SETUP.json').exists() else io.read_result('SETUP')[0]
    if not setup.get('local_qualified'):w.journal('dependent_not_run',reason='local block numerical Gate');return
    active=[]
    for name in ORDER:
        if name.startswith('LC') and not setup.get('composite_qualified'):
            w.journal('conditional_not_run',stage=name,reason='D_L/composite numerical Gate or upstream unavailable');continue
        result=run(name);w.journal('route_end',stage=name,status=result['status'])
        if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
        if result.get('stop_reason')=='SLICE_TARGET_COMPLETE':active.append(name)
    while active:
        again=[]
        for name in active:
            row=w.ledger()
            # Explicit Review21 bound: <=5 independent readonly factor actors,
            # not unbounded process relaunches disguised as free resumes.
            if row['charged']['factor_readers']>=w.CAPS['factor_readers']:
                w.journal('conditional_not_run',stage=name,reason='five independent factor-reader cap reached');continue
            w.require_live(margin=600);prior,_=io.read_result(name);target=len(prior['cycles'])+4
            result=run(name,target);w.journal('route_end',stage=name,status=result['status'])
            if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
            if result.get('stop_reason')=='SLICE_TARGET_COMPLETE':again.append(name)
        active=again


def freeze():
    if (io.ARTIFACT_ROOT/'FROZEN.json').exists():return
    plan=json.loads(io.PLAN_PATH.read_text());items=[]
    for name in ORDER:
        if not (io.ARTIFACT_ROOT/(name+'.json')).exists():continue
        result,_=io.read_result(name)
        p=io.ARTIFACT_ROOT/name/'FIRST_EQUATION_PASS.json'
        if p.exists():items.append(dict(json.loads(p.read_text()),name=name+'-FIRST_PASS'))
        if 'final' in result:items.append(dict(result['final'],name=name+'-FINAL'))
    items.append(dict(plan['initial_states']['GPOLY'],name='V21-C-FINAL',legacy=True))
    for name in ('LZ','LCZ'):
        if (io.ARTIFACT_ROOT/(name+'.json')).exists():
            r,_=io.read_result(name)
            if len(r.get('cycles',[]))>=4:items.append(dict(r['cycles'][3],name=name+'-CYCLE4'))
    unique={}
    for item in items:unique.setdefault(item['state']['z_sha256'],item)
    if not 1<=len(unique)<=12:raise ValueError('V24 field capacity')
    row=w.ledger()
    if row['active'] is not None:raise ValueError('actor must exit before REF7 freeze')
    row['closed']=True;write_json(w.LEDGER_PATH,row)
    write_json(io.ARTIFACT_ROOT/'FROZEN.json',dict(validation_inventory=list(unique.values()),source_queue_frozen=True,
        reference_not_yet_read=True,selection_uses_reference=False));w.journal('all_choices_frozen',states=len(unique))


def main_queue(args):
    try:
        if args.solve:solve()
        if args.verify:
            freeze();result=run('VERIFY');return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
        return 0
    finally:minimum_package()
