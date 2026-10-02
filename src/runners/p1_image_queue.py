"""Finite V23 queue; tiny MR gain never blocks a safe zero-trace first block."""
import json,subprocess
from src.io import p1_image_minres as io
from src.solvers import p1_image_window as w
from src.runners.task042_shared import write_json
from src.runners.p1_trace_queue import cool

def run(name):
    attempt=0
    while True:
        w.require_live(margin=30);original=io.ROOT/f'input/task042_neural_coarse_inverse/v23_{io.FILES[name]}.dat';path=original
        if attempt:
            path=w.TMP/f'v23_{name.lower()}_retry{attempt}.dat'
            if path.exists():raise ValueError('consumed retry input')
            path.write_text(original.read_text().replace('run_id = "task042_v23_'+io.FILES[name]+'"',f'run_id = "task042_v23_{io.FILES[name]}_retry{attempt}"'))
        before=len(w.ledger()['runs']);w.journal('stage_dispatch',stage=name,input_path=str(path))
        mode='fe' if name=='VERIFY' else 'pure'
        code=subprocess.call(['bash','-c',f'set -e; export TASK042_CACHE_NAMESPACE=v23/{mode}; source scripts/activate_task042.sh {mode}; exec python scripts/run_case.py "$1"','task042-v23',str(path)])
        row=w.ledger()
        if len(row['runs'])==before:return dict(status='ADMISSION_BLOCKED',exit_code=code)
        item=row['runs'][-1]
        if item['classification']=='COMPLETED' and code==0:return io.read_result(name)[0]
        if item['classification']!='RESOURCE_CONTROLLED_STOP':return dict(status='RUN_FAILED',run=item)
        p=__import__('pathlib').Path(item['directory'])/'supervision/resources.jsonl'
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
        results[name]=dict(status=r['status'],source_sha=r['source_sha'],result_path=str(p),
            result_sha256=__import__('src.solvers.neural_fe_action_packet',fromlist=['file_hash']).file_hash(p),
            final_state=final.get('state'),final_gate=final.get('original_equation_gate'),
            stop_reason=r.get('stop_reason'),first_pass_cycle=r.get('first_pass_cycle'),
            image_qualified=r.get('image_qualified'),PC_qualified=r.get('PC_qualified'),
            counts=r.get('aux_counts'),actions=r.get('all_incremental_equivalent_actions'))
    write_json(w.TMP/'minimum_result_package.json',dict(clock=w.snapshot(),results=results,ledger=w.ledger(),
        previous_formal_lower_bound_seconds=74063.4870035164,historical_auxiliary='unknown retained'))
    # Preserve a readable response immediately on queue exit, before the
    # low-load final documentation.  This is local progress, not a final pass.
    text=['# V23 最小阶段回应', '', '数值资格仍以原审核和冻结后的独立场验证为准。', '']
    for name,row in results.items():
        text.append(f"- {name}: {row['status']}；source={row['source_sha']}；结果={row['result_path']}")
    target=w.TMP/'minimum_response.md';temporary=target.with_suffix('.md.partial')
    temporary.write_text('\n'.join(text)+'\n');temporary.replace(target)

def solve():
    setup=run('SETUP') if not (io.ARTIFACT_ROOT/'SETUP.json').exists() else io.read_result('SETUP')[0]
    if setup.get('status') in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    if not setup.get('image_qualified'):
        w.journal('conditional_not_run',stages=['COMPARE','M','Z'],reason='image/QR/R numerical Gate');return
    comparison=run('COMPARE');w.journal('route_end',stage='COMPARE',status=comparison['status'])
    if comparison['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    if comparison['status']!='COARSE_COMPARISON_COMPLETE':
        w.journal('conditional_not_run',stages=['M','Z'],reason='D identity/physical-MR numerical Gate requires localized repair');return
    if not setup['PC_qualified']:
        w.journal('conditional_not_run',stages=['M','Z'],reason='Dsmall/full-space PC numerical Gate');return
    for name in ('M','Z'):
        result=run(name);w.journal('route_end',stage=name,status=result['status'])
        if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return

def freeze():
    if (io.ARTIFACT_ROOT/'FROZEN.json').exists():return
    plan=json.loads(io.PLAN_PATH.read_text());items=[dict(plan['initial_states']['GPOLY'],name='V21-C-FINAL',legacy=True)]
    if (io.ARTIFACT_ROOT/'COMPARE.json').exists():
        r,_=io.read_result('COMPARE');items.extend(r.get('warm_corrections',{}).values())
    for name in ('M','Z'):
        if not (io.ARTIFACT_ROOT/(name+'.json')).exists():continue
        r,_=io.read_result(name)
        if 'final' in r:items.append(dict(r['final'],name=name+'-FINAL'))
        if len(r.get('cycles',[]))>=4:items.append(dict(r['cycles'][3],name=name+'-CYCLE4'))
        p=io.ARTIFACT_ROOT/name/'FIRST_EQUATION_PASS.json'
        if p.exists():items.append(dict(json.loads(p.read_text()),name=name+'-FIRST_PASS'))
    unique={}
    for item in items:unique.setdefault(item['state']['z_sha256'],item)
    if not 1<=len(unique)<=10:raise ValueError('V23 frozen field capacity')
    row=w.ledger()
    if row['active'] is not None:raise ValueError('V23 actor must exit before freeze')
    row['closed']=True;write_json(w.LEDGER_PATH,row)
    write_json(io.ARTIFACT_ROOT/'FROZEN.json',dict(validation_inventory=list(unique.values()),source_queue_frozen=True,
        reference_not_yet_read=True,selection_uses_reference=False));w.journal('all_choices_frozen',states=len(unique))

def main_queue(args):
    try:
        if args.preflight:
            result=run('SETUP');return 0 if result['status']=='IMAGE_SETUP_COMPLETE' else 1
        if args.solve:solve()
        if args.verify:
            freeze();result=run('VERIFY');return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
        return 0
    finally:minimum_package()
