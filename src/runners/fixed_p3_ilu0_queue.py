"""Finite S0/N/P0/P40/T/C queue; reference freeze is a separate phase."""
import json
import subprocess
import time
from pathlib import Path
from src.io import fixed_p3_ilu0 as io
from src.solvers import fixed_p3_ilu0_window as w
from src.runners.task042_shared import write_json,pressure,audit


FILES=dict(SETUP='capacity_setup',N='control_gpoly',P0='ilu0_gpoly',P40='ilu0_port_gpoly',
           T='transfer_gnn',C='zero_start',VERIFY='verify')


def cool():
    row=w.ledger()
    if row['reentries']>=2 or row['cooldown_seconds']>=1200:return False
    began=time.monotonic();stable=None;safe=False
    while time.monotonic()-began<min(600,1200-row['cooldown_seconds']):
        if w.snapshot()['heavy_remaining_seconds']<600:break
        psi=pressure();elapsed=time.monotonic()-began
        if elapsed>=120 and psi['full']['avg10']<.05:
            if stable is None:stable=time.monotonic()
            if time.monotonic()-stable>=60:
                try:
                    baseline=audit(observed_activity=True);write_json(w.TMP/f'reentry_{row["reentries"]}.json',baseline)
                    safe=True;break
                except RuntimeError as error:w.journal('reentry_admission_failed',reason=str(error));stable=None
        else:stable=None
        w.journal('bounded_cooldown',elapsed_seconds=elapsed,pressure=psi)
        time.sleep(5)
    row=w.ledger();row['cooldown_seconds']+=time.monotonic()-began
    if safe:row['reentries']+=1
    write_json(w.LEDGER_PATH,row);w.journal('resource_reentry_decision',allowed=safe)
    return safe


def run(name):
    attempt=0
    while True:
        if attempt:
            # Every resource retry has a separate explicit one-run input.
            path=w.TMP/f'v20_{name.lower()}_retry{attempt}.dat'
            original=io.ROOT/f'input/task042_neural_coarse_inverse/v20_{FILES[name]}.dat'
            if path.exists():raise ValueError('retry input already consumed')
            path.write_text(original.read_text().replace('run_id = "task042_v20_'+FILES[name]+'"',f'run_id = "task042_v20_{FILES[name]}_retry{attempt}"'))
        else:path=io.ROOT/f'input/task042_neural_coarse_inverse/v20_{FILES[name]}.dat'
        before=len(w.ledger()['runs']);w.journal('stage_dispatch',stage=name,input_path=str(path))
        code=subprocess.call(['bash','-c','set -e; export TASK042_CACHE_NAMESPACE=v20/fe; source scripts/activate_task042.sh fe; exec python scripts/run_case.py "$1"','task042-v20',str(path)])
        row=w.ledger()
        if len(row['runs'])==before:return dict(status='ADMISSION_BLOCKED',exit_code=code)
        item=row['runs'][-1]
        if item['classification']=='COMPLETED' and code==0:return io.read_result(name)[0]
        if item['classification']!='RESOURCE_CONTROLLED_STOP':return dict(status='RUN_FAILED',run=item)
        resources=Path(item['directory'])/'supervision/resources.jsonl'
        tail=resources.read_text().splitlines()[-8:]
        psi=any(json.loads(s).get('opt_in_health_check',{}).get('pressure_consecutive_samples',0)>=3 for s in tail)
        if not psi or item['swap_peak_bytes'] or item['rss_peak_bytes']>=16*2**30 or not cool():
            return dict(status='RESOURCE_ENVIRONMENT_BLOCKED',run=item)
        attempt+=1


def solve():
    setup,_=io.read_result('SETUP')
    result=run('N');w.journal('route_end',stage='N',status=result['status'])
    if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    if not setup['PC_qualified']:
        w.journal('PC_routes_not_run',reason=setup.get('PC_stop'));return
    choices=[]
    for name in ('P0','P40'):
        result=run(name);w.journal('route_end',stage=name,status=result['status'])
        if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
        if 'final' in result:
            choices.append(result)
            if result['first_pass_cycle'] is not None:break
    if not choices:return
    passing=[r for r in choices if r['first_pass_cycle'] is not None]
    if passing:
        selected=min(passing,key=lambda r:sum(c['cycle_action_counts']['S']+c['cycle_action_counts']['SH'] for c in r['cycles'][:r['first_pass_cycle']]))
    else:selected=min(choices,key=lambda r:(r['final']['original_equation_gate']['rho'],r['pc_kind']!='B0'))
    ratio=selected['start']['original_equation_gate']['rho']/selected['final']['original_equation_gate']['rho']
    choice=dict(pc_kind=selected['pc_kind'],admitted=bool(passing or ratio>=10),original_rho_improvement_factor=ratio,
                selection_rule='original equation pass/action count, otherwise rho; never reference',selected_state=selected['final']['state'])
    write_json(io.ARTIFACT_ROOT/'PC_CHOICE.json',choice);w.journal('PC_selected',**choice)
    if choice['admitted']:
        for name in ('T','C'):
            if w.snapshot()['heavy_remaining_seconds']<1200:w.journal('conditional_not_run',stage=name,reason='verification/time reserve');continue
            result=run(name);w.journal('route_end',stage=name,status=result['status'])
            if result['status'] in ('RESOURCE_ENVIRONMENT_BLOCKED','ADMISSION_BLOCKED'):return
    else:w.journal('conditional_not_run',stages=['T','C'],reason='original PC progress gate')


def freeze():
    root=io.ARTIFACT_ROOT
    if (root/'FROZEN.json').exists():return
    plan=json.loads(io.PLAN_PATH.read_text());items=[dict(v,name='V19-'+v['name'],legacy=True) for v in plan['initial_states'].values()]
    for name in ('N','P0','P40','T','C'):
        if not (root/(name+'.json')).exists():continue
        result,_=io.read_result(name)
        if 'final' in result:items.append(dict(result['final'],name=name+'-FINAL'))
        p=root/name/'FIRST_PASS.json'
        if p.exists():items.append(dict(json.loads(p.read_text()),name=name+'-FIRST_PASS'))
    unique={}
    for item in items:unique.setdefault(item['state']['z_sha256'],item)
    if not 1<=len(unique)<=12:raise ValueError('V20 frozen field state inventory')
    row=w.ledger();row['closed']=True;write_json(w.LEDGER_PATH,row)
    write_json(root/'FROZEN.json',dict(validation_inventory=list(unique.values()),source_queue_frozen=True,
                                     reference_not_yet_read=True,selection_uses_reference=False))
    w.journal('all_solver_choices_frozen',states=list(unique))


def main_queue(args):
    if args.preflight:
        result=run('SETUP');w.journal('S0_end',status=result['status'])
        return 0 if result['status']=='SETUP_COMPLETE' else 1
    if args.solve:solve()
    if args.verify:
        freeze();result=run('VERIFY');w.journal('V20_verify_end',status=result['status'])
        return 0 if result['status']=='FROZEN_VALIDATION_COMPLETE' else 1
    return 0
